"""Support for Kevo Plus locks."""
from __future__ import annotations
from typing import Any

from aiokevoplus import KevoLock as AioKevoLock

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, KevoCoordinator

import logging
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Kevo lock platform."""
    coordinator: KevoCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    locks = await coordinator.get_devices()
    async_add_entities(KevoLock(lock, coordinator) for lock in locks)

class KevoLock(CoordinatorEntity, LockEntity):
    """Representation of a Kevo lock."""

    def __init__(self, lock: AioKevoLock, coordinator: KevoCoordinator):
        """Initialize the lock."""
        super().__init__(coordinator)
        self._lock = lock
        self._attr_name = lock.name
        self._attr_unique_id = lock.lock_id
        self._attr_device_class = "lock"
        self._is_locked = None

    @property
    def is_locked(self) -> bool | None:
        """Return true if lock is locked."""
        if self.coordinator.data:
            for device in self.coordinator.data.values():
                if device.lock_id == self._lock.lock_id:
                    return device.is_locked
        return self._is_locked

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the device."""
        try:
            _LOGGER.debug("Locking %s", self.name)
            # Since lock() is a coroutine, we need to await it directly
            await self._lock.lock()
            self._is_locked = True
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Failed to lock %s: %s", self.name, str(e))
            self._is_locked = None
            self.async_write_ha_state()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the device."""
        try:
            _LOGGER.debug("Unlocking %s", self.name)
            # Since unlock() is a coroutine, we need to await it directly
            await self._lock.unlock()
            self._is_locked = False
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        except Exception as e:
            _LOGGER.error("Failed to unlock %s: %s", self.name, str(e))
            self._is_locked = None
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            for device in self.coordinator.data.values():
                if device.lock_id == self._lock.lock_id:
                    self._lock = device
                    self._is_locked = device.is_locked
                    break
        self.async_write_ha_state()