"""MQTT client for Harvest Right using native TCP with TLS."""

import json
import logging
import ssl
import time
import uuid
from collections.abc import Callable

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

from homeassistant.core import HomeAssistant

from .const import MQTT_BROKER, MQTT_KEEPALIVE, MQTT_PORT, MQTT_SESSION_EXPIRY

_LOGGER = logging.getLogger(__name__)

# Message types to subscribe to per dryer
SUBSCRIBE_MSG_TYPES = [
    "telemetry",
    "system",
    "name-update",
]

MessageCallback = Callable[[int, str, dict], None]


class HarvestRightMqttClient:
    """MQTT client for Harvest Right freeze dryers using native TCP with TLS."""

    def __init__(
        self,
        hass: HomeAssistant,
        customer_id: int,
        email: str,
        access_token: str,
        on_message: MessageCallback,
    ) -> None:
        self._hass = hass
        self._customer_id = customer_id
        self._email = email
        self._access_token = access_token
        self._on_message = on_message
        self._subscribed_dryers: set[int] = set()
        self._last_message_time: float = 0.0
        self._on_connect_fail: Callable[[], None] | None = None
        self._client: mqtt.Client | None = None

    def _init_client(self) -> None:
        """Create and configure the paho MQTT client (blocking — call from executor)."""
        suffix = uuid.uuid4().hex[:6]
        client_id = f"{self._customer_id}-ha-device.{suffix}"

        self._connect_props = Properties(PacketTypes.CONNECT)
        self._connect_props.SessionExpiryInterval = MQTT_SESSION_EXPIRY

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv5,
        )
        self._client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
        self._client.username_pw_set(self._email, self._access_token)
        self._client.reconnect_delay_set(min_delay=1, max_delay=120)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            self._client.enable_logger(_LOGGER)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_mqtt_message
        self._client.on_disconnect = self._on_disconnect

    @property
    def last_message_time(self) -> float:
        """Return the monotonic time of the last received message."""
        return self._last_message_time

    def set_on_connect_fail(self, callback: Callable[[], None]) -> None:
        """Set a callback for connection authentication failures."""
        self._on_connect_fail = callback

    @property
    def is_connected(self) -> bool:
        """Return True if the MQTT client is currently connected."""
        return self._client is not None and self._client.is_connected()

    async def connect(self) -> None:
        """Connect to the MQTT broker (non-blocking).

        The actual connection happens on paho's network thread.
        If the broker is unreachable, _on_connect will never fire
        and the watchdog will eventually trigger a reconnect.
        """
        _LOGGER.info("Connecting to MQTT broker %s:%s", MQTT_BROKER, MQTT_PORT)
        await self._hass.async_add_executor_job(self._connect_sync)

    def _connect_sync(self) -> None:
        """Initialize client and start async connect (runs on executor)."""
        if self._client is None:
            self._init_client()
        self._last_message_time = time.monotonic()
        self._client.connect_async(
            MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE,
            properties=self._connect_props,
        )
        self._client.loop_start()

    async def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        if self._client is None:
            return
        _LOGGER.debug("Disconnecting from MQTT broker")
        self._client.loop_stop()
        self._client.disconnect()

    async def subscribe_dryer(self, dryer_id: int) -> None:
        """Register a dryer for topic subscription.

        Actual subscribing happens in _on_connect when the connection is ready.
        """
        self._subscribed_dryers.add(dryer_id)

    def _subscribe_dryer_topics(self, dryer_id: int) -> None:
        """Subscribe to MQTT topics for a dryer."""
        for msg_type in SUBSCRIBE_MSG_TYPES:
            topic = f"act/{self._customer_id}/ed/{dryer_id}/m/{msg_type}"
            self._client.subscribe(topic, qos=0)
            _LOGGER.debug("Subscribed to %s", topic)

    def publish_online(self) -> None:
        """Publish 'on' to the online topic to keep telemetry flowing.

        The dryer's WiFi adapter only sends telemetry while it knows a client
        is listening.  The web app publishes 'on' on connect and periodically.
        """
        if self._client is None or not self._client.is_connected():
            return
        topic = f"act/{self._customer_id}/on"
        self._client.publish(topic, "on", qos=0)
        _LOGGER.debug("Published 'on' to %s", topic)

    def update_token(self, access_token: str) -> None:
        """Update the access token and reconnect to apply it."""
        if access_token == self._access_token:
            _LOGGER.debug("Token unchanged, skipping reconnect")
            return
        self.force_reconnect(new_token=access_token)

    def force_reconnect(self, new_token: str | None = None) -> None:
        """Force a full MQTT reconnect, optionally with a new token.

        Stops the network loop, disconnects, updates credentials if
        provided, and starts a fresh connection. Safe to call from any thread.
        """
        _LOGGER.info("Forcing MQTT reconnect")
        if new_token is not None:
            self._access_token = new_token

        if self._client is not None:
            try:
                self._client.loop_stop()
            except Exception:
                _LOGGER.debug("loop_stop raised during force_reconnect", exc_info=True)

            try:
                self._client.disconnect()
            except Exception:
                _LOGGER.debug("disconnect raised during force_reconnect", exc_info=True)

        # Reset the timer so the watchdog gives this connection time
        # to establish before triggering another reconnect
        self._last_message_time = time.monotonic()

        # Re-create the client to get a fresh client ID and clean state
        self._init_client()
        self._client.connect_async(
            MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE,
            properties=self._connect_props,
        )
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        """Handle MQTT connection."""
        if rc == 0:
            self._last_message_time = time.monotonic()
            _LOGGER.info("Connected to MQTT broker successfully")
            # Subscribe to dryer topics
            for dryer_id in self._subscribed_dryers:
                self._subscribe_dryer_topics(dryer_id)
            # Publish "on" to signal the dryer to start sending telemetry
            online_topic = f"act/{self._customer_id}/on"
            client.publish(online_topic, "on", qos=0)
            _LOGGER.debug("Published 'on' to %s", online_topic)
        else:
            _LOGGER.error("MQTT connection failed with code %s", rc)
            # Stop paho's auto-reconnect loop — the coordinator will
            # handle reconnection with a fresh token via force_reconnect
            try:
                client.disconnect()
            except Exception:
                pass
            if self._on_connect_fail is not None:
                self._on_connect_fail()

    def _on_mqtt_message(self, client, userdata, msg) -> None:
        """Handle incoming MQTT message — runs on paho's network thread."""
        self._last_message_time = time.monotonic()

        # Online/offline topic sends plain strings ("on", "continue"), not JSON
        if msg.topic.endswith("/on"):
            text = msg.payload.decode("utf-8", errors="replace")
            _LOGGER.debug("Online status update: %s", text)
            return

        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            _LOGGER.warning("Failed to decode MQTT message on %s", msg.topic)
            return

        # Parse topic: act/{custId}/ed/{dryerId}/m/{msgType}
        parts = msg.topic.split("/")
        if len(parts) >= 6 and parts[2] == "ed" and parts[4] == "m":
            try:
                dryer_id = int(parts[3])
            except ValueError:
                _LOGGER.warning("Invalid dryer ID in topic %s", msg.topic)
                return
            msg_type = parts[5]
            self._on_message(dryer_id, msg_type, payload)
        else:
            _LOGGER.debug("Unhandled topic: %s", msg.topic)

    def _on_disconnect(self, client, userdata, flags, rc, properties=None) -> None:
        """Handle MQTT disconnection."""
        if rc != 0:
            _LOGGER.warning(
                "Unexpected MQTT disconnect (code %s), will attempt reconnect", rc
            )
        else:
            _LOGGER.debug("MQTT disconnected cleanly")
