#!/usr/bin/env python3
"""Standalone test script for Harvest Right API and MQTT.

Tests the full workflow without Home Assistant:
  1. REST API login
  2. Fetch freeze dryer list
  3. MQTT WebSocket connection + telemetry subscription
  4. Print incoming messages until Ctrl+C

Usage:
  python scripts/test_standalone.py --email you@example.com --password yourpass

Or via Docker:
  docker compose run test --email you@example.com --password yourpass
"""

import argparse
import asyncio
import json
import logging
import signal
import ssl
import sys
import time
import uuid

import aiohttp
import paho.mqtt.client as mqtt

API_BASE = "https://prod.harvestrightapp.com"
MQTT_BROKER = "mqtt.harvestrightapp.com"
MQTT_PORT = 8084
MQTT_KEEPALIVE = 150

SCREEN_STATES = {
    0: "Ready to Start", 1: "Load Trays", 2: "Rotate Trays",
    3: "Warming Trays", 4: "Freezing", 5: "Drying (Heating)", 6: "Drying (Max Temp)",
    7: "Extra Dry Time", 8: "Batch Complete", 9: "Remove Trays",
    10: "Defrosting", 11: "Defrosted", 12: "System Setup", 13: "Time Setup",
    14: "Factory Setup", 15: "Testing", 16: "Settings", 17: "Restarting",
    18: "Preparing", 19: "Setup", 20: "Welcome", 21: "Authorizing",
    22: "Recipe Creation", 23: "Unable to Achieve Vacuum",
    24: "Freeze Dryer Not Cooling", 25: "Not Detecting Heat", 26: "Time Expired",
}

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("harvest_right_test")

# Quiet down noisy libraries
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("paho").setLevel(logging.WARNING)


# ── REST API ─────────────────────────────────────────────────────────────────


async def api_login(session: aiohttp.ClientSession, email: str, password: str) -> dict:
    """Login and return the auth response."""
    log.info("Logging in as %s ...", email)
    async with session.post(
        f"{API_BASE}/auth/v1",
        json={"username": email, "password": password, "rememberme": True},
    ) as resp:
        if resp.status == 401:
            log.error("Login failed: invalid credentials")
            sys.exit(1)
        if resp.status != 200:
            text = await resp.text()
            log.error("Login failed (HTTP %s): %s", resp.status, text)
            sys.exit(1)
        data = await resp.json()
        if data.get("error"):
            log.error("Login error: %s", data["error"])
            sys.exit(1)
    log.info(
        "Logged in — customerId=%s, userId=%s, token expires at %s",
        data["customerId"],
        data["userId"],
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data["accessExpire"])),
    )
    return data


async def api_get_dryers(session: aiohttp.ClientSession, token: str) -> list[dict]:
    """Fetch registered freeze dryers."""
    log.info("Fetching freeze dryer list ...")
    async with session.get(
        f"{API_BASE}/freeze-dryer/v1",
        headers={"Authorization": f"Bearer {token}"},
    ) as resp:
        if resp.status != 200:
            text = await resp.text()
            log.error("Failed to fetch dryers (HTTP %s): %s", resp.status, text)
            sys.exit(1)
        dryers = await resp.json()
    log.info("Found %d dryer(s)", len(dryers))
    for d in dryers:
        log.info(
            "  %-20s  model=%-8s serial=%s  id=%s",
            d.get("dryer_name", "?"),
            d.get("model", "?"),
            d.get("serial", "?"),
            d.get("id", "?"),
        )
    return dryers


async def api_refresh_token(session: aiohttp.ClientSession, refresh_token: str) -> dict:
    """Refresh the access token. Tries multiple approaches."""
    # Approach 1: Bearer token in Authorization header (per spec)
    log.info("Refreshing token (approach 1: Authorization header) ...")
    async with session.post(
        f"{API_BASE}/auth/v1/refresh-token",
        headers={
            "Authorization": f"Bearer {refresh_token}",
            "Content-Type": "application/json",
        },
    ) as resp:
        if resp.status == 200:
            data = await resp.json()
            log.info("Token refreshed (approach 1), new expiry: %s",
                     time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data["accessExpire"])))
            return data
        text = await resp.text()
        log.warning("Approach 1 failed (HTTP %s): %s", resp.status, text[:200])

    # Approach 2: refresh token in JSON body
    log.info("Refreshing token (approach 2: JSON body) ...")
    async with session.post(
        f"{API_BASE}/auth/v1/refresh-token",
        json={"refreshToken": refresh_token},
    ) as resp:
        if resp.status == 200:
            data = await resp.json()
            log.info("Token refreshed (approach 2), new expiry: %s",
                     time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data["accessExpire"])))
            return data
        text = await resp.text()
        log.warning("Approach 2 failed (HTTP %s): %s", resp.status, text[:200])

    log.error("All token refresh approaches failed")
    return None


# ── MQTT ─────────────────────────────────────────────────────────────────────


MQTT_AUTH_APPROACHES = []  # populated dynamically in start_mqtt_attempts


def try_mqtt(
    label: str,
    customer_id: int,
    dryers: list[dict],
    username: str | None,
    password: str | None,
    ws_headers: dict | None = None,
    ws_path: str = "/mqtt",
) -> tuple[mqtt.Client, asyncio.Event, asyncio.Event]:
    """Try a single MQTT auth approach."""
    suffix = uuid.uuid4().hex[:8]
    client_id = f"ha-test-{customer_id}-{suffix}"
    log.info("[%s] client_id=%s user=%s pass=%s ws_headers=%s",
             label, client_id,
             (username[:20] + "...") if username and len(username) > 20 else username,
             "set" if password else "none",
             "set" if ws_headers else "none")

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        transport="websockets",
        protocol=mqtt.MQTTv5,
    )
    client.ws_set_options(path=ws_path, headers=ws_headers)
    client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
    if username or password:
        client.username_pw_set(username, password)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    connected = asyncio.Event()
    failed = asyncio.Event()

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            log.info("[%s] CONNECTED!", label)
            for d in dryers:
                did = d["id"]
                for msg_type in ("telemetry", "system", "name-update", "batch-summary"):
                    topic = f"act/{customer_id}/ed/{did}/m/{msg_type}"
                    client.subscribe(topic, qos=0)
                    log.debug("  subscribed: %s", topic)
            # NOTE: Do NOT subscribe to act/{custId}/on — broker disconnects clients that do
            log.info("Subscribed to all topics — waiting for messages ...")
            connected._loop.call_soon_threadsafe(connected.set)
        else:
            log.error("[%s] FAILED: rc=%s", label, rc)
            failed._loop.call_soon_threadsafe(failed.set)

    def on_message(client, userdata, msg):
        raw_bytes = msg.payload
        text = raw_bytes.decode("utf-8", errors="replace")

        # Online topic sends plain strings like "on", "continue"
        if msg.topic.endswith("/on"):
            log.info("[ONLINE] %s", text)
            return

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            log.warning("Non-JSON payload on %s: %s", msg.topic, text[:200])
            return

        parts = msg.topic.split("/")
        if len(parts) >= 6 and parts[4] == "m":
            dryer_id = parts[3]
            msg_type = parts[5]
            dryer_name = next(
                (d.get("dryer_name", "?") for d in dryers if str(d["id"]) == dryer_id),
                dryer_id,
            )

            # Always dump raw payload for discovery
            raw = json.dumps(payload, indent=2)
            if msg_type == "telemetry":
                screen = payload.get("screen")
                state = SCREEN_STATES.get(screen, f"Unknown({screen})")
                log.info("[%s] TELEMETRY (state=%s):\n%s", dryer_name, state, raw)
            elif msg_type == "system":
                log.info("[%s] SYSTEM:\n%s", dryer_name, raw)
            else:
                log.info("[%s] %s:\n%s", dryer_name, msg_type.upper(), raw)
        elif msg.topic.endswith("/on"):
            log.info("[ONLINE] %s", json.dumps(payload, indent=None)[:200])
        else:
            log.info("[???] %s: %s", msg.topic, json.dumps(payload, indent=None)[:200])

    def on_disconnect(client, userdata, flags, rc, properties=None):
        if rc != 0:
            log.warning("MQTT disconnected unexpectedly (rc=%s), will reconnect", rc)
        else:
            log.info("MQTT disconnected")

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    log.info("Connecting to %s:%s ...", MQTT_BROKER, MQTT_PORT)
    client.connect_async(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
    client.loop_start()
    return client, connected, failed


# ── Main ─────────────────────────────────────────────────────────────────────


async def main(email: str, password: str, skip_mqtt: bool = False):
    stop = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    async with aiohttp.ClientSession() as session:
        # Step 1: Login
        auth = await api_login(session, email, password)

        # Step 2: Get dryers
        dryers = await api_get_dryers(session, auth["accessToken"])
        if not dryers:
            log.warning("No freeze dryers found on this account")

        # Save original token before refresh (MQTT might need it)
        original_token = auth["accessToken"]

        # Step 3: Test token refresh
        refreshed = await api_refresh_token(session, auth["refreshToken"])
        if refreshed:
            auth = refreshed

        if skip_mqtt:
            log.info("Skipping MQTT (--skip-mqtt). Done.")
            return

        if not dryers:
            log.info("No dryers to subscribe to. Done.")
            return

        # Step 4: MQTT — build a list of auth approaches to try
        cid = str(auth["customerId"])
        uid = str(auth["userId"])
        at = auth["accessToken"]
        rt = auth["refreshToken"]
        email = email

        attempts = [
            # username/password combos
            ("cid+access", cid, at, None),
            ("cid+refresh", cid, rt, None),
            ("uid+access", uid, at, None),
            ("uid+refresh", uid, rt, None),
            ("email+access", email, at, None),
            ("email+refresh", email, rt, None),
            # JWT in WebSocket Authorization header
            ("ws-bearer+cid", cid, None, {"Authorization": f"Bearer {at}"}),
            ("ws-bearer+noauth", None, None, {"Authorization": f"Bearer {at}"}),
            # no auth at all
            ("no-auth", None, None, None),
        ]

        client = None
        for label, user, pw, ws_headers in attempts:
            client, connected, failed = try_mqtt(
                label, auth["customerId"], dryers, user, pw,
                ws_headers=ws_headers,
            )
            done, pending = await asyncio.wait(
                [asyncio.create_task(connected.wait()), asyncio.create_task(failed.wait())],
                timeout=8,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()

            if connected.is_set():
                break

            client.loop_stop()
            client.disconnect()
            client = None

        if client is None:
            log.error("All MQTT auth approaches failed")
            return

        log.info("Press Ctrl+C to stop")
        await stop.wait()

        log.info("Shutting down ...")
        client.loop_stop()
        client.disconnect()

    log.info("Done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Harvest Right API + MQTT")
    parser.add_argument("--email", required=True, help="Harvest Right account email")
    parser.add_argument("--password", required=True, help="Account password")
    parser.add_argument("--skip-mqtt", action="store_true", help="Only test REST API, skip MQTT")
    args = parser.parse_args()
    asyncio.run(main(args.email, args.password, args.skip_mqtt))
