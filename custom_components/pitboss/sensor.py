"""Sensor platform for pitboss."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_devices: AddEntitiesCallback
):
    """Setup sensor platform."""
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.unique_id is not None
    entities = []
    for i in range(1, coordinator.api.spec.meat_probes + 1):
        entities.append(ProbeSensor(coordinator, entry.unique_id, i))
    async_add_devices(entities)


class ProbeSensor(BaseEntity, SensorEntity):
    """PitBoss probe Sensor class."""

    _attr_icon = "mdi:thermometer"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entity_unique_id: str,
        probe_number: int,
    ) -> None:
        super().__init__(coordinator, entity_unique_id)
        self._attr_unique_id = f"probe{probe_number}_{entity_unique_id}"
        self._attr_name = f"Probe {probe_number}"
        self._probe_number = probe_number

    @property
    def native_unit_of_measurement(self) -> str | None:
        if data := self.coordinator.data:
            if not data.get("isFahrenheit"):
                return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def available(self) -> bool:
        return bool(self.coordinator.data)

    @property
    def native_value(self) -> int | None:
        """Return the native value of the sensor."""
        if data := self.coordinator.data:
            return data[f"p{self._probe_number}Temp"]  # type: ignore[literal-required]
        return None
