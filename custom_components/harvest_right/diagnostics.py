"""Diagnostics support for the Harvest Right integration."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import HarvestRightConfigEntry

TO_REDACT = {
    "email",
    "password",
    "refresh_token",
    "customer_id",
    "customerId",
    "userId",
    "accessToken",
    "refreshToken",
    "serial",
    "serialNumber",
    "cpuSerial",
    "aName",
    "unique_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HarvestRightConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry, with sensitive data redacted."""
    coordinator = entry.runtime_data
    telemetry = coordinator.data or {}

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "mqtt_connected": coordinator.mqtt_connected,
        "dryer_count": len(coordinator.dryers),
        "dryers": [
            async_redact_data(dryer.get("raw", {}), TO_REDACT)
            for dryer in coordinator.dryers
        ],
        "telemetry": {
            str(dryer_id): {
                "available": coordinator.dryer_available(dryer_id),
                "data": async_redact_data(data, TO_REDACT),
            }
            for dryer_id, data in telemetry.items()
        },
        "generated_at_monotonic": time.monotonic(),
    }
