"""Config flow for Kevo Plus integration."""

from __future__ import annotations

import hashlib
import logging
import uuid
import ssl
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from custom_components.kevo_plus.aiokevoplus import KevoApi, KevoAuthError, KevoError

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import CONF_LOCKS, DOMAIN

_LOGGER = logging.getLogger(__name__)
STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_USERNAME): str,
    vol.Required(CONF_PASSWORD): str,
})

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kevo Plus."""
    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.data: dict = {}
        self._api: KevoApi = None
        self._locks = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}
        try:
            device_id = uuid.UUID(
                bytes=hashlib.md5(user_input[CONF_PASSWORD].encode()).digest()
            )

            def create_api():
                """Create API client with SSL context in executor."""
                ssl_context = ssl.create_default_context()
                return KevoApi(device_id, ssl_context=ssl_context)

            self._api = await self.hass.async_add_executor_job(create_api)
            # Offload the blocking login() call to the executor.
            await self.hass.async_add_executor_job(
                self._api.login, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            # Offload get_locks() to the executor.
            locks = await self.hass.async_add_executor_job(self._api.get_locks)
            self._locks = {lock.lock_id: lock.name for lock in locks}
            self.data = user_input
            return await self.async_step_devices()
        except KevoAuthError:
            errors["base"] = "invalid_auth"
        except KevoError:
            errors["base"] = "cannot_connect"
        except Exception as ex:
            _LOGGER.exception("Unexpected exception: %s", ex)
            errors["base"] = "unknown"
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_devices(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle lock selection step."""
        if user_input is None:
            return self.async_show_form(
                step_id="devices",
                data_schema=vol.Schema({
                    vol.Required(
                        CONF_LOCKS, default=list(self._locks)
                    ): cv.multi_select(self._locks)
                }),
            )

        self.data.update(user_input)
        return self.async_create_entry(
            title=self.data[CONF_USERNAME], data=self.data, options=user_input
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reauthentication step."""
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow for picking devices."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        if self.config_entry.state != config_entries.ConfigEntryState.LOADED:
            return self.async_abort(reason="unknown")

        data = self.hass.data[DOMAIN][self.config_entry.entry_id]
        try:
            locks = {dev.lock_id: dev.name for dev in await data.get_devices()}
        except KevoAuthError:
            return self.async_abort(reason="invalid_auth")
        except KevoError:
            return self.async_abort(reason="cannot_connect")
        except Exception:
            return self.async_abort(reason="unknown")

        default_locks = self.config_entry.options.get(CONF_LOCKS)
        if default_locks is None:
            default_locks = self.config_entry.data.get(CONF_LOCKS)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_LOCKS,
                    default=default_locks,
                ): cv.multi_select(locks),
            }),
        )