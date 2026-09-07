"""Tests for integration setup, unload and message handling."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.harvest_right.const import (
    CONF_EMAIL,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    EVENT_BATCH_SUMMARY,
    SERVICE_REFRESH,
)

from .conftest import API_BASE, CUSTOMER_ID, EMAIL


def _entry() -> MockConfigEntry:
    """Build a config entry for the test account."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(CUSTOMER_ID),
        title=EMAIL,
        data={CONF_EMAIL: EMAIL, CONF_REFRESH_TOKEN: "refresh-0"},
    )


async def test_setup_and_unload(
    hass: HomeAssistant, mock_api_endpoints, mock_mqtt
) -> None:
    """The entry sets up, creates entities, and unloads cleanly."""
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.kitchen_dryer_temperature") is not None
    assert hass.states.get("binary_sensor.kitchen_dryer_online") is not None
    assert hass.services.has_service(DOMAIN, SERVICE_REFRESH)
    # The rotated refresh token from the refresh call is persisted.
    assert entry.data[CONF_REFRESH_TOKEN] == "refresh-2"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_auth_failure_triggers_reauth(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """A rejected refresh token with no password starts a re-auth flow."""
    aioclient_mock.post(f"{API_BASE}/auth/v1/refresh-token", status=401)
    entry = _entry()
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_telemetry_message_updates_sensor(
    hass: HomeAssistant, mock_api_endpoints, mock_mqtt
) -> None:
    """An incoming telemetry message updates entity state."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data
    coordinator._handle_mqtt_message(
        1, "telemetry", {"temp": 42, "screen": 4, "pct": 75}
    )
    await hass.async_block_till_done()

    assert coordinator.dryer_telemetry(1)["temp"] == 42
    # Progress has no device class, so its state is reported verbatim.
    assert hass.states.get("sensor.kitchen_dryer_progress").state == "75"
    assert hass.states.get("sensor.kitchen_dryer_state").state == "Freezing"
    assert hass.states.get("binary_sensor.kitchen_dryer_freezing").state == "on"


async def test_batch_summary_fires_event(
    hass: HomeAssistant, mock_api_endpoints, mock_mqtt
) -> None:
    """A batch-summary message fires an HA event."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    events = []
    hass.bus.async_listen(EVENT_BATCH_SUMMARY, events.append)

    entry.runtime_data._handle_mqtt_message(1, "batch-summary", {"duration": 3600})
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data["dryer_id"] == 1
