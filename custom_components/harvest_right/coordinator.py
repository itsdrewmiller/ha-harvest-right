"""Data coordinator for Harvest Right integration."""

import asyncio
import logging
import time

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import HarvestRightApi
from .const import DOMAIN
from .mqtt_client import HarvestRightMqttClient

_LOGGER = logging.getLogger(__name__)

# Watchdog thresholds (seconds)
_WATCHDOG_CHECK_INTERVAL = 120  # How often to check for stale connections
_WATCHDOG_STALE_THRESHOLD = 600  # 10 min: request telemetry refresh
_WATCHDOG_DEAD_THRESHOLD = 900  # 15 min: force full reconnect


class HarvestRightCoordinator:
    """Coordinate data from Harvest Right API and MQTT."""

    def __init__(self, hass: HomeAssistant, api: HarvestRightApi, email: str) -> None:
        self.hass = hass
        self.api = api
        self._email = email
        self.mqtt: HarvestRightMqttClient | None = None
        self.dryers: list[dict] = []
        self.dryer_data: dict[int, dict] = {}
        self._token_refresh_task: asyncio.Task | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._telemetry_requested: bool = False

    async def async_setup(self) -> None:
        """Login, fetch dryers, connect MQTT, and start background tasks."""
        await self.api.login()
        self.dryers = await self.api.get_freeze_dryers()

        self.mqtt = HarvestRightMqttClient(
            self.hass,
            self.api.customer_id,
            self._email,
            self.api.access_token,
            self._handle_mqtt_message,
        )
        await self.mqtt.connect()
        self.mqtt.set_on_connect_fail(self._handle_mqtt_connect_fail)

        for dryer in self.dryers:
            dryer_id = dryer["id"]
            await self.mqtt.subscribe_dryer(dryer_id)
            self.dryer_data[dryer_id] = {}

        self._token_refresh_task = self.hass.async_create_background_task(
            self._async_token_refresh_loop(),
            f"{DOMAIN}_token_refresh",
        )
        self._watchdog_task = self.hass.async_create_background_task(
            self._async_watchdog_loop(),
            f"{DOMAIN}_mqtt_watchdog",
        )

        _LOGGER.debug(
            "Setup complete: %d dryer(s) found", len(self.dryers)
        )

    def _handle_mqtt_message(
        self, dryer_id: int, msg_type: str, payload: dict
    ) -> None:
        """Handle MQTT message — called from paho's network thread."""
        self.hass.loop.call_soon_threadsafe(
            self.hass.async_create_task,
            self._async_handle_message(dryer_id, msg_type, payload),
        )

    async def _async_handle_message(
        self, dryer_id: int, msg_type: str, payload: dict
    ) -> None:
        """Process an MQTT message on the HA event loop."""
        if dryer_id not in self.dryer_data:
            _LOGGER.debug("Received data for unknown dryer %s", dryer_id)
            return

        self._telemetry_requested = False

        if msg_type == "telemetry":
            self.dryer_data[dryer_id].update(payload)
        elif msg_type == "system":
            self.dryer_data[dryer_id]["system"] = payload
        elif msg_type == "name-update":
            self.dryer_data[dryer_id]["name_update"] = payload
        else:
            _LOGGER.debug("Unhandled message type %s for dryer %s", msg_type, dryer_id)
            return

        async_dispatcher_send(self.hass, f"{DOMAIN}_{dryer_id}_update")

    async def _async_token_refresh_loop(self) -> None:
        """Periodically refresh the access token."""
        while True:
            try:
                seconds_until_refresh = max(
                    60, self.api.refresh_after - time.time()
                )
                # Refresh slightly early
                wait_time = min(3600, seconds_until_refresh - 60)
                await asyncio.sleep(max(60, wait_time))

                await self.api.ensure_valid_token()
                if self.mqtt:
                    await self.hass.async_add_executor_job(
                        self.mqtt.update_token, self.api.access_token
                    )
                _LOGGER.debug("Token refreshed successfully")
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("Error refreshing token, will retry in 5 minutes")
                await asyncio.sleep(300)

    async def _async_watchdog_loop(self) -> None:
        """Monitor MQTT connection health and reconnect if stale."""
        while True:
            try:
                await asyncio.sleep(_WATCHDOG_CHECK_INTERVAL)

                if not self.mqtt:
                    continue

                last_msg = self.mqtt.last_message_time
                if last_msg == 0.0:
                    # No messages received yet (still connecting or dryer offline)
                    continue

                silence = time.monotonic() - last_msg

                if silence >= _WATCHDOG_DEAD_THRESHOLD:
                    _LOGGER.warning(
                        "No MQTT messages for %.0f seconds, forcing reconnect",
                        silence,
                    )
                    self._telemetry_requested = False
                    await self.api.ensure_valid_token()
                    await self.hass.async_add_executor_job(
                        self.mqtt.force_reconnect, self.api.access_token
                    )
                elif silence >= _WATCHDOG_STALE_THRESHOLD and not self._telemetry_requested:
                    _LOGGER.info(
                        "No MQTT messages for %.0f seconds, requesting telemetry refresh",
                        silence,
                    )
                    self._telemetry_requested = True
                    for dryer_id in self.dryer_data:
                        await self.hass.async_add_executor_job(
                            self.mqtt.request_telemetry, dryer_id
                        )
                elif silence < _WATCHDOG_STALE_THRESHOLD:
                    self._telemetry_requested = False

            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("Error in MQTT watchdog, will retry")

    def _handle_mqtt_connect_fail(self) -> None:
        """Handle MQTT connection failure — called from paho's thread."""
        self.hass.loop.call_soon_threadsafe(
            self.hass.async_create_task,
            self._async_refresh_and_reconnect(),
        )

    async def _async_refresh_and_reconnect(self) -> None:
        """Refresh the token and force an MQTT reconnect."""
        try:
            _LOGGER.info("MQTT auth failure detected, refreshing token and reconnecting")
            await self.api.refresh_token()
            if self.mqtt:
                await self.hass.async_add_executor_job(
                    self.mqtt.force_reconnect, self.api.access_token
                )
        except Exception:
            _LOGGER.exception("Failed to refresh token and reconnect MQTT")

    async def async_shutdown(self) -> None:
        """Disconnect MQTT and cancel background tasks."""
        for task in (self._token_refresh_task, self._watchdog_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self.mqtt:
            await self.mqtt.disconnect()
        _LOGGER.debug("Coordinator shut down")
