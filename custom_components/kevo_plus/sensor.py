"""Support for Kevo Plus lock sensors."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import KevoCoordinator
from .const import DOMAIN, MODEL

async def async_setup_entry(hass: HomeAssistant, config: ConfigEntry, add_entities: AddEntitiesCallback) -> None:
    """Set up the sensor platform."""
    coordinator: KevoCoordinator = hass.data[DOMAIN][config.entry_id]

    try:
        devices = await coordinator.get_devices()
    except Exception as ex:
        raise PlatformNotReady("Error getting devices") from ex

    entities = [
        KevoSensorEntity(
            hass=hass,
            name="Battery Level",
            device=lock,
            coordinator=coordinator,
            device_type="battery_level",
        )
        for lock in devices
    ]

    add_entities(entities)

class KevoSensorEntity(CoordinatorEntity, SensorEntity):
    """Representation of a Kevo Sensor Entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        device,
        coordinator: KevoCoordinator,
        device_type: str,
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._device_type = device_type

        self._attr_name = name
        self._attr_has_entity_name = True
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_unique_id = f"{device.lock_id}_{device_type}"

        if device_type == "battery_level":
            self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_native_value = device.battery_level

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.lock_id)},
            manufacturer=device.brand,
            name=device.name,
            model=MODEL,
            sw_version=device.firmware,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._device_type == "battery_level":
            self._attr_native_value = self._device.battery_level
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(self._device.api.register_callback(self._handle_coordinator_update))