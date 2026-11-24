"""Tests for sensors that read the REST dryer record."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.harvest_right.const import CONF_EMAIL, CONF_REFRESH_TOKEN, DOMAIN

from .conftest import API_BASE, CUSTOMER_ID, DRYERS_RESPONSE, EMAIL, auth_response


def _entry() -> MockConfigEntry:
    """Build a config entry for the test account."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(CUSTOMER_ID),
        title=EMAIL,
        data={CONF_EMAIL: EMAIL, CONF_REFRESH_TOKEN: "refresh-0"},
    )


def _register_endpoints(aioclient_mock, dryers: list[dict]) -> None:
    """Register auth and dryer-list responses with the given dryer records."""
    aioclient_mock.post(f"{API_BASE}/auth/v1", json=auth_response())
    aioclient_mock.post(
        f"{API_BASE}/auth/v1/refresh-token",
        json=auth_response(access="access-2", refresh="refresh-2"),
    )
    aioclient_mock.get(f"{API_BASE}/freeze-dryer/v1", json=dryers)


async def _setup_with_telemetry(hass: HomeAssistant, telemetry: dict) -> None:
    """Set up the entry and push one telemetry message so entities are available."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entry.runtime_data._handle_mqtt_message(1, "telemetry", telemetry)
    await hass.async_block_till_done()


async def test_lifetime_counters_from_dryer_record(
    hass: HomeAssistant, aioclient_mock, mock_mqtt
) -> None:
    """Batch count and run times come from the REST dryer record."""
    dryer = {
        **DRYERS_RESPONSE[0],
        "completed_batches": 30,
        "pump_min": 689,
        "system_min": 905,
    }
    _register_endpoints(aioclient_mock, [dryer])
    await _setup_with_telemetry(hass, {"temp": 42})

    assert hass.states.get("sensor.kitchen_dryer_batch_count").state == "30"

    pump = hass.states.get("sensor.kitchen_dryer_pump_run_time")
    assert float(pump.state) == 689
    assert pump.attributes["unit_of_measurement"] == "h"

    system = hass.states.get("sensor.kitchen_dryer_system_run_time")
    assert float(system.state) == 905
    assert system.attributes["unit_of_measurement"] == "h"


async def test_batch_count_falls_back_to_telemetry(
    hass: HomeAssistant, aioclient_mock, mock_mqtt
) -> None:
    """Without completed_batches in the record, batch count uses system.bc."""
    _register_endpoints(aioclient_mock, DRYERS_RESPONSE)
    await _setup_with_telemetry(hass, {"temp": 42, "system": {"bc": 12}})

    assert hass.states.get("sensor.kitchen_dryer_batch_count").state == "12"


async def test_missing_counters_are_unknown(
    hass: HomeAssistant, aioclient_mock, mock_mqtt
) -> None:
    """Counters absent from both the record and telemetry report unknown."""
    _register_endpoints(aioclient_mock, DRYERS_RESPONSE)
    await _setup_with_telemetry(hass, {"temp": 42})

    assert hass.states.get("sensor.kitchen_dryer_batch_count").state == "unknown"
    assert hass.states.get("sensor.kitchen_dryer_pump_run_time").state == "unknown"
    assert hass.states.get("sensor.kitchen_dryer_system_run_time").state == "unknown"
