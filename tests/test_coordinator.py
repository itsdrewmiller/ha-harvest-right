"""Tests for coordinator MQTT recovery."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.harvest_right.api import HarvestRightAuthError
from custom_components.harvest_right.const import DOMAIN
from custom_components.harvest_right.coordinator import HarvestRightCoordinator


@pytest.fixture
def coordinator(hass):
    """Build a coordinator without starting background tasks or network IO."""
    api = MagicMock()
    api.ensure_valid_token = AsyncMock()
    api.refresh_token_value = None
    api.access_token = "token"
    entry = MockConfigEntry(domain=DOMAIN)
    result = HarvestRightCoordinator(hass, entry, api)
    result.mqtt = MagicMock()
    result.mqtt.is_connected = False
    result.mqtt.last_message_time = 0
    return result


async def _watchdog_tick(coordinator):
    """Run one watchdog iteration without waiting in real time."""
    with (
        patch(
            "custom_components.harvest_right.coordinator.asyncio.sleep",
            side_effect=[None, asyncio.CancelledError],
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await coordinator._async_watchdog_loop()


async def test_reconnect_backoff_and_cap(coordinator):
    """Both triggers share increasing delays, including at low uptime."""
    with patch("custom_components.harvest_right.coordinator.time.monotonic") as clock:
        now = 0
        clock.return_value = now
        await coordinator._async_refresh_and_reconnect()
        assert coordinator.mqtt.force_reconnect.call_count == 1

        delays = [
            60,
            120,
            240,
            480,
            960,
            1920,
            3840,
            7680,
            15360,
            30720,
            61440,
            86400,
            86400,
        ]
        for count, delay in enumerate(delays, start=2):
            clock.return_value = now + delay - 1
            await coordinator._async_refresh_and_reconnect()
            await coordinator._reconnect_mqtt()
            assert coordinator.mqtt.force_reconnect.call_count == count - 1

            now += delay
            clock.return_value = now
            await coordinator._reconnect_mqtt()
            assert coordinator.mqtt.force_reconnect.call_count == count


async def test_watchdog_retries_without_another_failure_callback(coordinator):
    """A rejected connection retries on schedule despite a fresh watchdog timer."""
    with patch("custom_components.harvest_right.coordinator.time.monotonic") as clock:
        clock.return_value = 0
        await coordinator._async_refresh_and_reconnect()
        clock.return_value = 30
        await _watchdog_tick(coordinator)
        assert coordinator.mqtt.force_reconnect.call_count == 1
        clock.return_value = 60
        await _watchdog_tick(coordinator)
        assert coordinator.mqtt.force_reconnect.call_count == 2


async def test_success_resets_backoff(coordinator):
    """An observed connection restores immediate recovery and the initial delay."""
    with patch("custom_components.harvest_right.coordinator.time.monotonic") as clock:
        clock.return_value = 0
        await coordinator._reconnect_mqtt()
        clock.return_value = 60
        await coordinator._reconnect_mqtt()

        coordinator.mqtt.is_connected = True
        await _watchdog_tick(coordinator)
        coordinator.mqtt.is_connected = False
        await coordinator._reconnect_mqtt()
        assert coordinator.mqtt.force_reconnect.call_count == 3

        clock.return_value = 120
        await coordinator._reconnect_mqtt()
        assert coordinator.mqtt.force_reconnect.call_count == 4


@pytest.mark.parametrize("failure_source", ["token", "mqtt"])
async def test_transient_failure_keeps_backoff(coordinator, failure_source):
    """Token and client errors both wait before retrying."""
    failing_call = (
        coordinator.api.ensure_valid_token
        if failure_source == "token"
        else coordinator.mqtt.force_reconnect
    )
    failing_call.side_effect = [RuntimeError("unavailable"), None]
    with patch("custom_components.harvest_right.coordinator.time.monotonic") as clock:
        clock.return_value = 0
        await coordinator._reconnect_mqtt()
        clock.return_value = 59
        await coordinator._reconnect_mqtt()
        assert failing_call.call_count == 1
        clock.return_value = 60
        await coordinator._reconnect_mqtt()
        assert failing_call.call_count == 2


async def test_reconnect_does_not_overlap(coordinator):
    """A second trigger cannot overlap a slow token refresh past its deadline."""
    with patch("custom_components.harvest_right.coordinator.time.monotonic") as clock:

        async def refresh():
            clock.return_value = 1000
            await coordinator._reconnect_mqtt()

        coordinator.api.ensure_valid_token.side_effect = refresh
        clock.return_value = 0
        await coordinator._reconnect_mqtt()
        coordinator.api.ensure_valid_token.assert_awaited_once()
        coordinator.mqtt.force_reconnect.assert_called_once_with("token")


async def test_auth_failure_starts_reauth(coordinator):
    """Invalid credentials start reauth and clear the scheduled retry."""
    coordinator.api.ensure_valid_token.side_effect = HarvestRightAuthError("expired")
    with patch.object(coordinator.entry, "async_start_reauth") as reauth:
        await coordinator._reconnect_mqtt()
        reauth.assert_called_once_with(coordinator.hass)
    coordinator.mqtt.force_reconnect.assert_not_called()
    assert coordinator._next_reconnect_attempt is None
