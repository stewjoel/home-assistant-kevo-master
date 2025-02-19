"""The Kevo Plus integration."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
import ssl
from datetime import timedelta

# Updated import: use our local vendored copy.
from custom_components.kevo_plus.aiokevoplus import KevoApi, KevoLock, KevoError, KevoAuthError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .const import CONF_LOCKS, DOMAIN

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.LOCK, Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kevo Plus from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    password = entry.data.get(CONF_PASSWORD)
    device_id = uuid.UUID(bytes=hashlib.md5(password.encode()).digest())

    def create_api_client():
        """Create API client with SSL context in executor."""
        ssl_context = ssl.create_default_context()
        return KevoApi(device_id, ssl_context=ssl_context)

    client = await hass.async_add_executor_job(create_api_client)
    try:
        # Offload blocking login call.
        await hass.async_add_executor_job(
            client.login, entry.data.get(CONF_USERNAME), password
        )
    except KevoAuthError as auth_ex:
        raise ConfigEntryAuthFailed("Invalid credentials") from auth_ex
    except KevoError as ex:
        raise ConfigEntryNotReady("Error connecting to Kevo server") from ex

    locks = entry.options.get(CONF_LOCKS) or entry.data.get(CONF_LOCKS)
    coordinator = KevoCoordinator(hass, client, entry, locks)
    try:
        await coordinator.async_refresh()
    except Exception as ex:
        raise ConfigEntryNotReady("Failed to get Kevo devices") from ex

    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_disconnect(event: Event) -> None:
        """Disconnect from Websocket."""
        await client.websocket_close()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_disconnect)
    )

    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload to update options."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await hass.data[DOMAIN][entry.entry_id].api.websocket_close()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

class KevoCoordinator(DataUpdateCoordinator):
    """Kevo Data Coordinator."""

    def __init__(
        self, hass: HomeAssistant, api: KevoApi, entry: ConfigEntry, locks: list[str]
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Kevo",
            update_interval=timedelta(seconds=30),
        )
        self.api = api
        self.entry = entry
        self._selected_locks = locks
        self._devices = {}

    async def _async_update_data(self):
        """Update data via library."""
        try:
            all_devices = await self.hass.async_add_executor_job(self.api.get_locks)
            self._devices = {
                device.lock_id: device
                for device in all_devices
                if device.lock_id in self._selected_locks
            }
            return self._devices
        except KevoAuthError:
            await self.entry.async_start_reauth(self.hass)
            raise ConfigEntryNotReady("Authentication error")
        except Exception as e:
            _LOGGER.error(f"Error updating Kevo locks: {e}")
            raise ConfigEntryNotReady(f"Error communicating with API: {e}")

    async def get_devices(self) -> list:
        """Retrieve the devices associated with the coordinator."""
        if not self._devices:
            await self.async_refresh()
        return list(self._devices.values())