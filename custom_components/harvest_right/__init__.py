"""The Harvest Right integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HarvestRightApi
from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN
from .coordinator import HarvestRightCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Harvest Right from a config entry."""
    api = HarvestRightApi(
        async_get_clientsession(hass),
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
    )

    coordinator = HarvestRightCoordinator(hass, api, entry.data[CONF_EMAIL])
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: HarvestRightCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_shutdown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
