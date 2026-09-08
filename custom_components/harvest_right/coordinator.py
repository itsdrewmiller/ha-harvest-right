"""Data coordinator for the Harvest Right integration."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HarvestRightApi, HarvestRightApiError, HarvestRightAuthError
from .const import (
    CONF_REFRESH_TOKEN,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_TEMPERATURE_UNIT,
    DOMAIN,
    EVENT_BATCH_SUMMARY,
    OPT_SCAN_INTERVAL,
    OPT_TEMPERATURE_UNIT,
    STALE_THRESHOLD,
    TEMP_UNIT_CELSIUS,
)
from .mqtt_client import HarvestRightMqttClient

_LOGGER = logging.getLogger(__name__)

# Background task intervals (seconds)
_ONLINE_PUBLISH_INTERVAL = 30  # Republish "on" to keep telemetry flowing
_WATCHDOG_DEAD_THRESHOLD = 900  # 15 min of silence: force a full reconnect
_MIN_TOKEN_REFRESH_INTERVAL = 300  # never hammer the auth endpoint faster
_RECONNECT_INITIAL_DELAY = 60
_RECONNECT_MAX_DELAY = 24 * 60 * 60  # 24 hours


class HarvestRightCoordinator(DataUpdateCoordinator[dict[int, dict]]):
    """Coordinate REST + MQTT data for Harvest Right freeze dryers.

    ``data`` is a mapping of dryer id -> accumulated telemetry/system data.
    The periodic update polls the REST dryer list to discover added or
    removed dryers; live telemetry is pushed in over MQTT.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: HarvestRightApi,
    ) -> None:
        """Initialize the coordinator."""
        scan_minutes = entry.options.get(
            OPT_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_minutes),
        )
        self.entry = entry
        self.api = api
        self.dryers: list[dict] = []
        self.mqtt: HarvestRightMqttClient | None = None

        self._dryer_data: dict[int, dict] = {}
        self._dryer_last_msg: dict[int, float] = {}
        self._token_refresh_task: asyncio.Task | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._next_reconnect_attempt: float | None = None
        self._reconnect_delay = _RECONNECT_INITIAL_DELAY
        self._reconnect_in_progress = False

    # ── Setup / teardown ─────────────────────────────────────────────────

    async def async_setup(self) -> None:
        """Authenticate, discover dryers, connect MQTT, and start tasks.

        Raises ConfigEntryAuthFailed for auth problems (triggers re-auth)
        and HarvestRightApiError for transient connection problems.
        """
        try:
            await self.api.ensure_valid_token()
            self.dryers = await self.api.get_freeze_dryers()
        except HarvestRightAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err

        await self._persist_refresh_token()

        for dryer in self.dryers:
            self._dryer_data.setdefault(dryer["id"], {})

        self.mqtt = HarvestRightMqttClient(
            self.hass,
            self.api.customer_id,
            self.api.email,
            self.api.access_token,
            self._handle_mqtt_message,
        )
        self.mqtt.set_on_connect_fail(self._handle_mqtt_connect_fail)
        # Register subscriptions before connecting so _on_connect picks
        # them up as soon as the broker link is established.
        for dryer in self.dryers:
            self.mqtt.subscribe_dryer(dryer["id"])
        await self.mqtt.connect()

        self._token_refresh_task = self.entry.async_create_background_task(
            self.hass, self._async_token_refresh_loop(), f"{DOMAIN}_token_refresh"
        )
        self._watchdog_task = self.entry.async_create_background_task(
            self.hass, self._async_watchdog_loop(), f"{DOMAIN}_mqtt_watchdog"
        )

    async def async_shutdown(self) -> None:
        """Cancel background tasks and disconnect MQTT."""
        for task in (self._token_refresh_task, self._watchdog_task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        if self.mqtt:
            await self.mqtt.disconnect()
        await super().async_shutdown()
        _LOGGER.debug("Coordinator shut down")

    # ── Periodic REST poll: dryer rediscovery ────────────────────────────

    async def _async_update_data(self) -> dict[int, dict]:
        """Poll the REST dryer list and reconcile added/removed dryers."""
        try:
            dryers = await self.api.get_freeze_dryers()
        except HarvestRightAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HarvestRightApiError as err:
            raise UpdateFailed(str(err)) from err

        await self._persist_refresh_token()

        new_ids = {d["id"] for d in dryers}
        old_ids = {d["id"] for d in self.dryers}

        if new_ids != old_ids:
            # Membership changed since setup — reload the entry so devices
            # and entities are added/removed cleanly.
            _LOGGER.info(
                "Dryer list changed (was %s, now %s); reloading integration",
                sorted(old_ids),
                sorted(new_ids),
            )
            self.dryers = dryers
            self.hass.config_entries.async_schedule_reload(self.entry.entry_id)
        else:
            # Same dryers — refresh their metadata (name/firmware may change).
            self.dryers = dryers

        return self._dryer_data

    # ── MQTT message handling ────────────────────────────────────────────

    def _handle_mqtt_message(self, dryer_id: int, msg_type: str, payload: dict) -> None:
        """Receive an MQTT message (paho thread) and marshal to the loop."""
        self.hass.loop.call_soon_threadsafe(
            self._async_handle_message, dryer_id, msg_type, payload
        )

    @callback
    def _async_handle_message(
        self, dryer_id: int, msg_type: str, payload: dict
    ) -> None:
        """Process an MQTT message on the HA event loop."""
        if dryer_id not in self._dryer_data:
            _LOGGER.debug("Ignoring data for unknown dryer %s", dryer_id)
            return

        self._dryer_last_msg[dryer_id] = time.monotonic()

        if msg_type == "telemetry":
            if isinstance(payload, dict):
                self._dryer_data[dryer_id].update(payload)
            else:
                _LOGGER.warning("Non-dict telemetry for dryer %s", dryer_id)
                return
        elif msg_type == "system":
            self._dryer_data[dryer_id]["system"] = payload
        elif msg_type == "name-update":
            self._dryer_data[dryer_id]["name_update"] = payload
        elif msg_type == "batch-summary":
            self._dryer_data[dryer_id]["batch_summary"] = payload
            self.hass.bus.async_fire(
                EVENT_BATCH_SUMMARY,
                {"dryer_id": dryer_id, "summary": payload},
            )
        else:
            _LOGGER.debug("Unhandled message type %s", msg_type)
            return

        self.async_set_updated_data(self._dryer_data)

    # ── Availability ─────────────────────────────────────────────────────

    @property
    def mqtt_connected(self) -> bool:
        """Return True if the MQTT link to the broker is up."""
        return self.mqtt is not None and self.mqtt.is_connected

    def dryer_available(self, dryer_id: int) -> bool:
        """Return True if recent telemetry has been received for a dryer."""
        if not self.mqtt_connected:
            return False
        last = self._dryer_last_msg.get(dryer_id)
        if last is None:
            return False
        return (time.monotonic() - last) < STALE_THRESHOLD.total_seconds()

    def dryer_telemetry(self, dryer_id: int) -> dict:
        """Return the accumulated telemetry dict for a dryer."""
        return self._dryer_data.get(dryer_id, {})

    @property
    def temperature_unit(self) -> str:
        """Return the HA temperature unit the device reports values in."""
        opt = self.entry.options.get(OPT_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT)
        if opt == TEMP_UNIT_CELSIUS:
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    # ── Service: force a telemetry refresh ───────────────────────────────

    async def async_refresh_telemetry(self) -> None:
        """Republish 'on' immediately to prompt fresh telemetry."""
        if self.mqtt:
            await self.hass.async_add_executor_job(self.mqtt.publish_online)

    # ── Token persistence ────────────────────────────────────────────────

    async def _persist_refresh_token(self) -> None:
        """Persist a rotated refresh token back to the config entry."""
        token = self.api.refresh_token_value
        if token and token != self.entry.data.get(CONF_REFRESH_TOKEN):
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={**self.entry.data, CONF_REFRESH_TOKEN: token},
            )
            _LOGGER.debug("Persisted rotated refresh token")

    # ── Background loops ─────────────────────────────────────────────────

    async def _async_token_refresh_loop(self) -> None:
        """Periodically refresh the access token before it expires."""
        while True:
            try:
                seconds_until = max(60.0, self.api.refresh_after - time.time())
                # Refresh ~60s early, never sleep less than the floor, and
                # never longer than an hour.
                wait = min(3600.0, max(_MIN_TOKEN_REFRESH_INTERVAL, seconds_until - 60))
                await asyncio.sleep(wait)

                await self.api.ensure_valid_token()
                await self._persist_refresh_token()
                if self.mqtt:
                    await self.hass.async_add_executor_job(
                        self.mqtt.update_token, self.api.access_token
                    )
                _LOGGER.debug("Token refreshed successfully")
            except asyncio.CancelledError:
                raise
            except ConfigEntryAuthFailed:
                raise
            except HarvestRightAuthError as err:
                _LOGGER.warning("Token refresh needs re-auth: %s", err)
                self.entry.async_start_reauth(self.hass)
                return
            except Exception:
                _LOGGER.exception("Error refreshing token, retrying in 5 minutes")
                await asyncio.sleep(300)

    async def _async_watchdog_loop(self) -> None:
        """Republish 'on' periodically and force a reconnect on long silence."""
        while True:
            try:
                await asyncio.sleep(_ONLINE_PUBLISH_INTERVAL)
                if not self.mqtt:
                    continue

                await self.hass.async_add_executor_job(self.mqtt.publish_online)

                if self.mqtt.is_connected:
                    self._next_reconnect_attempt = None
                    self._reconnect_delay = _RECONNECT_INITIAL_DELAY
                    continue

                if self._next_reconnect_attempt is not None:
                    await self._reconnect_mqtt()
                    continue

                silence = time.monotonic() - self.mqtt.last_message_time
                if silence >= _WATCHDOG_DEAD_THRESHOLD:
                    _LOGGER.warning("MQTT silent for %.0fs, forcing reconnect", silence)
                    await self._reconnect_mqtt()
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("Error in MQTT watchdog, will retry")

    def _handle_mqtt_connect_fail(self) -> None:
        """Handle an MQTT auth failure (paho thread)."""
        self.hass.loop.call_soon_threadsafe(
            self.hass.async_create_task,
            self._async_refresh_and_reconnect(),
        )

    async def _async_refresh_and_reconnect(self) -> None:
        """Refresh the token and reconnect MQTT, with exponential backoff."""
        _LOGGER.info("MQTT auth failure detected, refreshing token")
        await self._reconnect_mqtt()

    async def _reconnect_mqtt(self) -> None:
        """Refresh and reconnect, sharing backoff across all retry triggers."""
        if self.mqtt is None or self._reconnect_in_progress:
            return
        now = time.monotonic()
        if (
            self._next_reconnect_attempt is not None
            and now < self._next_reconnect_attempt
        ):
            return

        self._reconnect_in_progress = True
        self._next_reconnect_attempt = now + self._reconnect_delay
        self._reconnect_delay = min(self._reconnect_delay * 2, _RECONNECT_MAX_DELAY)
        try:
            await self.api.ensure_valid_token()
            await self._persist_refresh_token()
            await self.hass.async_add_executor_job(
                self.mqtt.force_reconnect, self.api.access_token
            )
        except HarvestRightAuthError as err:
            self._next_reconnect_attempt = None
            _LOGGER.warning("Reconnect needs re-auth: %s", err)
            self.entry.async_start_reauth(self.hass)
        except Exception:
            _LOGGER.exception("Failed to refresh token or reconnect MQTT")
        finally:
            self._reconnect_in_progress = False
