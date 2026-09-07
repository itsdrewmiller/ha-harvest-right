"""Config and options flow for the Harvest Right integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .api import HarvestRightApi, HarvestRightApiError, HarvestRightAuthError
from .const import (
    CONF_CUSTOMER_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_TEMPERATURE_UNIT,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
    OPT_SCAN_INTERVAL,
    OPT_TEMPERATURE_UNIT,
    TEMP_UNIT_CELSIUS,
    TEMP_UNIT_FAHRENHEIT,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


class HarvestRightConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Harvest Right config flow."""

    VERSION = 1

    async def _validate(
        self, email: str, password: str
    ) -> tuple[dict[str, str], HarvestRightApi | None]:
        """Attempt a login and dryer fetch, returning (errors, api)."""
        api = HarvestRightApi(
            async_get_clientsession(self.hass), email, password=password
        )
        try:
            await api.login()
            dryers = await api.get_freeze_dryers()
        except HarvestRightAuthError:
            return {"base": "invalid_auth"}, None
        except HarvestRightApiError:
            return {"base": "cannot_connect"}, None
        except Exception:
            _LOGGER.exception("Unexpected error validating Harvest Right login")
            return {"base": "unknown"}, None

        if not dryers:
            return {"base": "no_dryers"}, None
        return {}, api

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial user step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, api = await self._validate(
                user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if api is not None:
                await self.async_set_unique_id(str(api.customer_id))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL],
                    data={
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_REFRESH_TOKEN: api.refresh_token_value,
                        CONF_CUSTOMER_ID: api.customer_id,
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when the stored session expires."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Prompt the user for their password again."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            errors, api = await self._validate(
                entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if api is not None:
                if str(api.customer_id) != entry.unique_id:
                    errors["base"] = "wrong_account"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data={
                            **entry.data,
                            CONF_REFRESH_TOKEN: api.refresh_token_value,
                        },
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={CONF_EMAIL: entry.data[CONF_EMAIL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> HarvestRightOptionsFlow:
        """Return the options flow handler."""
        return HarvestRightOptionsFlow()


class HarvestRightOptionsFlow(OptionsFlow):
    """Handle Harvest Right options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the integration options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    OPT_TEMPERATURE_UNIT,
                    default=options.get(OPT_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[TEMP_UNIT_FAHRENHEIT, TEMP_UNIT_CELSIUS],
                        translation_key="temperature_unit",
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    OPT_SCAN_INTERVAL,
                    default=options.get(
                        OPT_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_MINUTES,
                        max=MAX_SCAN_INTERVAL_MINUTES,
                        step=5,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
