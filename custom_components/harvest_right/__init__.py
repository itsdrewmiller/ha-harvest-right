"""The Harvest Right integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry

from .api import HarvestRightApi, HarvestRightApiError
from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    SERVICE_REFRESH,
)
from .coordinator import HarvestRightCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

type HarvestRightConfigEntry = ConfigEntry[HarvestRightCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: HarvestRightConfigEntry
) -> bool:
    """Set up Harvest Right from a config entry."""
    api = HarvestRightApi(
        async_get_clientsession(hass),
        entry.data[CONF_EMAIL],
        password=entry.data.get(CONF_PASSWORD),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
    )

    coordinator = HarvestRightCoordinator(hass, entry, api)
    try:
        await coordinator.async_setup()
    except HarvestRightApiError as err:
        raise ConfigEntryNotReady(str(err)) from err

    # First refresh discovers the dryer list (raises ConfigEntryAuthFailed /
    # ConfigEntryNotReady itself on failure).
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _register_services(hass)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: HarvestRightConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
        if not hass.config_entries.async_loaded_entries(DOMAIN):
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: HarvestRightConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: HarvestRightConfigEntry,
    device: DeviceEntry,
) -> bool:
    """Allow deleting a device only if its dryer is no longer on the account."""
    coordinator = entry.runtime_data
    known_serials = {(DOMAIN, d["serial"]) for d in coordinator.dryers}
    return not known_serials.intersection(device.identifiers)


@callback
def _register_services(hass: HomeAssistant) -> None:
    """Register the integration's services once."""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    async def _handle_refresh(call: ServiceCall) -> None:
        """Force a telemetry refresh on every loaded entry."""
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            await entry.runtime_data.async_refresh_telemetry()

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _handle_refresh)
