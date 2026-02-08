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

        for dryer in self.dryers:
            dryer_id = dryer["id"]
            await self.mqtt.subscribe_dryer(dryer_id)
            self.dryer_data[dryer_id] = {}

        self._token_refresh_task = self.hass.async_create_background_task(
            self._async_token_refresh_loop(),
            f"{DOMAIN}_token_refresh",
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
                    self.mqtt.update_token(self.api.access_token)
                _LOGGER.debug("Token refreshed successfully")
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("Error refreshing token, will retry in 5 minutes")
                await asyncio.sleep(300)

    async def async_shutdown(self) -> None:
        """Disconnect MQTT and cancel background tasks."""
        if self._token_refresh_task:
            self._token_refresh_task.cancel()
            try:
                await self._token_refresh_task
            except asyncio.CancelledError:
                pass
        if self.mqtt:
            await self.mqtt.disconnect()
        _LOGGER.debug("Coordinator shut down")
