"""Tests for config entry diagnostics."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.harvest_right.const import (
    CONF_EMAIL,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)
from custom_components.harvest_right.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import CUSTOMER_ID, EMAIL


async def test_diagnostics_redacts_sensitive_data(
    hass: HomeAssistant, mock_api_endpoints, mock_mqtt
) -> None:
    """Diagnostics include telemetry but redact secrets."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(CUSTOMER_ID),
        title=EMAIL,
        data={CONF_EMAIL: EMAIL, CONF_REFRESH_TOKEN: "secret-token"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entry.runtime_data._handle_mqtt_message(1, "telemetry", {"temp": 10})
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["entry"]["data"][CONF_EMAIL] == "**REDACTED**"
    assert diag["entry"]["data"][CONF_REFRESH_TOKEN] == "**REDACTED**"
    assert diag["dryer_count"] == 1
    assert diag["telemetry"]["1"]["data"]["temp"] == 10
