"""System health support for the Harvest Right integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import API_BASE, DOMAIN


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks."""
    register.async_register_info(_system_health_info)


async def _system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return information for the system health card."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    connected = sum(1 for entry in entries if entry.runtime_data.mqtt_connected)

    return {
        "configured_accounts": len(entries),
        "mqtt_connected_accounts": connected,
        "api_reachable": system_health.async_check_can_reach_url(hass, API_BASE),
    }
