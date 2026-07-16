"""Config flow for the Inforcer integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    InforcerApiError,
    InforcerAuthError,
    InforcerClient,
    InforcerConnectionError,
    InforcerRateLimitError,
)
from .const import (
    CONF_API_KEY,
    CONF_REGION,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
    MAX_UPDATE_INTERVAL_MINUTES,
    MIN_UPDATE_INTERVAL_MINUTES,
    REGIONS,
)

_LOGGER = logging.getLogger(__name__)

REGION_OPTIONS = [
    selector.SelectOptionDict(value=region, label=region.upper())
    for region in REGIONS
]


async def _async_validate_api_key(hass, region: str, api_key: str) -> str | None:
    """Call GET /beta/tenants to validate a key. Returns an error code or None."""
    session = async_get_clientsession(hass)
    client = InforcerClient(session, REGIONS[region], api_key)
    try:
        await client.async_get_tenants()
    except InforcerAuthError:
        return "invalid_auth"
    except InforcerRateLimitError:
        return "rate_limited"
    except InforcerConnectionError:
        return "cannot_connect"
    except InforcerApiError:
        return "unknown"
    return None


class InforcerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Inforcer."""

    VERSION = 1

    def __init__(self) -> None:
        self._region: str | None = None
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: pick a region."""
        if user_input is not None:
            self._region = user_input[CONF_REGION]
            return await self.async_step_api_key()

        schema = vol.Schema(
            {
                vol.Required(CONF_REGION): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=REGION_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_api_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: enter and validate the API key."""
        errors: dict[str, str] = {}
        assert self._region is not None

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            error = await _async_validate_api_key(self.hass, self._region, api_key)
            if error is None:
                await self.async_set_unique_id(self._region)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Inforcer ({self._region.upper()})",
                    data={CONF_REGION: self._region, CONF_API_KEY: api_key},
                )
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="api_key", data_schema=schema, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle a 401 triggering the reauth flow."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        self._region = entry_data[CONF_REGION]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user for a new API key after the old one stopped working."""
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None
        assert self._region is not None

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            error = await _async_validate_api_key(self.hass, self._region, api_key)
            if error is None:
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data={**self._reauth_entry.data, CONF_API_KEY: api_key},
                )
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> InforcerOptionsFlow:
        return InforcerOptionsFlow()


class InforcerOptionsFlow(OptionsFlow):
    """Options flow: adjust the poll interval, or rotate the API key proactively."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self.config_entry

        if user_input is not None:
            new_api_key = user_input.get(CONF_API_KEY)
            if new_api_key:
                error = await _async_validate_api_key(
                    self.hass, entry.data[CONF_REGION], new_api_key
                )
                if error is not None:
                    errors["base"] = error
                else:
                    self.hass.config_entries.async_update_entry(
                        entry, data={**entry.data, CONF_API_KEY: new_api_key}
                    )

            if not errors:
                return self.async_create_entry(
                    data={
                        CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL],
                    }
                )

        current_interval = entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_MINUTES
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL, default=current_interval
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_UPDATE_INTERVAL_MINUTES,
                        max=MAX_UPDATE_INTERVAL_MINUTES,
                        unit_of_measurement="minutes",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(CONF_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
