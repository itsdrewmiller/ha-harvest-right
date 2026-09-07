"""Shared fixtures for Harvest Right tests."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

API_BASE = "https://prod.harvestrightapp.com"

EMAIL = "owner@example.com"
PASSWORD = "hunter2"
CUSTOMER_ID = 12345


def auth_response(
    access: str = "access-1",
    refresh: str = "refresh-1",
    customer_id: int = CUSTOMER_ID,
) -> dict:
    """Build a valid auth/refresh API response."""
    return {
        "accessToken": access,
        "refreshToken": refresh,
        "refreshAfter": time.time() + 3600,
        "customerId": customer_id,
        "userId": 67890,
    }


DRYERS_RESPONSE = [
    {
        "id": 1,
        "serial": "HR-0001",
        "dryer_name": "Kitchen Dryer",
        "model": "Medium",
        "firmware": "2.1.0",
        "hardware": "1.0",
    }
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    yield


@pytest.fixture
def mock_api_endpoints(aioclient_mock):
    """Register happy-path responses for every Harvest Right endpoint."""
    aioclient_mock.post(f"{API_BASE}/auth/v1", json=auth_response())
    aioclient_mock.post(
        f"{API_BASE}/auth/v1/refresh-token",
        json=auth_response(access="access-2", refresh="refresh-2"),
    )
    aioclient_mock.get(f"{API_BASE}/freeze-dryer/v1", json=DRYERS_RESPONSE)
    return aioclient_mock


@pytest.fixture
def mock_mqtt():
    """Patch the MQTT client so tests never touch the network."""
    with patch(
        "custom_components.harvest_right.coordinator.HarvestRightMqttClient"
    ) as cls:
        instance = cls.return_value
        instance.connect = AsyncMock()
        instance.disconnect = AsyncMock()
        instance.is_connected = True
        instance.last_message_time = time.monotonic()
        yield instance
