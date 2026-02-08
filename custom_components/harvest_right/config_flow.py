"""Config flow for Harvest Right integration."""

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HarvestRightApi, HarvestRightAuthError
from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class HarvestRightConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Harvest Right."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            api = HarvestRightApi(
                async_get_clientsession(self.hass),
                user_input[CONF_EMAIL],
                user_input[CONF_PASSWORD],
            )
            try:
                result = await api.login()
            except HarvestRightAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(str(result["customerId"]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )
