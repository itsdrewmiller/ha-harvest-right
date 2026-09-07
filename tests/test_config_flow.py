"""Tests for the config and reauth flows."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.harvest_right.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

from .conftest import API_BASE, CUSTOMER_ID, EMAIL, PASSWORD, auth_response


async def test_user_flow_success(hass: HomeAssistant, mock_api_endpoints) -> None:
    """A valid login creates an entry storing the refresh token, not the password."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REFRESH_TOKEN] == "refresh-1"
    assert result["data"][CONF_EMAIL] == EMAIL
    assert CONF_PASSWORD not in result["data"]
    assert result["result"].unique_id == str(CUSTOMER_ID)


async def test_user_flow_invalid_auth(hass: HomeAssistant, aioclient_mock) -> None:
    """A 401 on login surfaces the invalid_auth error."""
    aioclient_mock.post(f"{API_BASE}/auth/v1", status=401)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_no_dryers(hass: HomeAssistant, aioclient_mock) -> None:
    """An account with no dryers surfaces the no_dryers error."""
    aioclient_mock.post(f"{API_BASE}/auth/v1", json=auth_response())
    aioclient_mock.get(f"{API_BASE}/freeze-dryer/v1", json=[])
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_dryers"}


async def test_user_flow_duplicate_aborts(
    hass: HomeAssistant, mock_api_endpoints
) -> None:
    """Configuring the same account twice aborts."""
    MockConfigEntry(
        domain=DOMAIN, unique_id=str(CUSTOMER_ID), data={CONF_EMAIL: EMAIL}
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow_success(
    hass: HomeAssistant, mock_api_endpoints, mock_mqtt
) -> None:
    """Re-auth replaces the stored refresh token for the same account."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(CUSTOMER_ID),
        data={CONF_EMAIL: EMAIL, CONF_REFRESH_TOKEN: "old"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: PASSWORD}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    # The stale token was replaced with a freshly issued one.
    assert entry.data[CONF_REFRESH_TOKEN] != "old"
