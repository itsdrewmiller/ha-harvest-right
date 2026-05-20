"""Tests for the options flow and system health."""

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.harvest_right import system_health
from custom_components.harvest_right.const import (
    CONF_EMAIL,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    OPT_SCAN_INTERVAL,
    OPT_TEMPERATURE_UNIT,
    TEMP_UNIT_CELSIUS,
)

from .conftest import CUSTOMER_ID, EMAIL


async def test_options_flow(hass: HomeAssistant, mock_api_endpoints, mock_mqtt) -> None:
    """The options flow stores the temperature unit and scan interval."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(CUSTOMER_ID),
        title=EMAIL,
        data={CONF_EMAIL: EMAIL, CONF_REFRESH_TOKEN: "r"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {OPT_TEMPERATURE_UNIT: TEMP_UNIT_CELSIUS, OPT_SCAN_INTERVAL: 60},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[OPT_TEMPERATURE_UNIT] == TEMP_UNIT_CELSIUS
    assert entry.options[OPT_SCAN_INTERVAL] == 60


async def test_system_health(
    hass: HomeAssistant, mock_api_endpoints, mock_mqtt
) -> None:
    """System health reports the configured account count."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(CUSTOMER_ID),
        title=EMAIL,
        data={CONF_EMAIL: EMAIL, CONF_REFRESH_TOKEN: "r"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    info = await system_health._system_health_info(hass)
    assert info["configured_accounts"] == 1
    assert info["mqtt_connected_accounts"] == 1


def test_system_health_register() -> None:
    """async_register wires up the info callback."""
    register = MagicMock()
    system_health.async_register(MagicMock(), register)
    register.async_register_info.assert_called_once()
