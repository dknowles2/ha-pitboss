"""Sensor platform for pitboss."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.components.sensor.const import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


@dataclass(frozen=True, kw_only=True)
class ProbeSensorEntityDescription(SensorEntityDescription):
    """Describes a PitBoss probe sensor."""

    probe_number: int
    device_class: SensorDeviceClass = SensorDeviceClass.TEMPERATURE
    state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    icon: str = "mdi:thermometer"


ENTITY_DESCRIPTIONS = (
    ProbeSensorEntityDescription(
        key="p1Temp",
        name="Probe 1",
        probe_number=1,
    ),
    ProbeSensorEntityDescription(
        key="p2Temp",
        name="Probe 2",
        probe_number=2,
    ),
    ProbeSensorEntityDescription(
        key="p3Temp",
        name="Probe 3",
        probe_number=3,
    ),
    ProbeSensorEntityDescription(
        key="p4Temp",
        name="Probe 4",
        probe_number=4,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_devices: AddEntitiesCallback
):
    """Setup sensor platform."""
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.unique_id is not None
    entities = []
    for entity_description in ENTITY_DESCRIPTIONS:
        entities.append(ProbeSensor(coordinator, entry.unique_id, entity_description))
    async_add_devices(entities)


class ProbeSensor(BaseEntity, SensorEntity):
    """PitBoss probe Sensor class."""

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
        entity_description: ProbeSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self.entity_description: ProbeSensorEntityDescription = entity_description
        self._attr_unique_id = (
            f"probe{entity_description.probe_number}_{entry_unique_id}"
        )

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added.

        This only applies with first added to the entity registry.
        """
        return (
            self.entity_description.probe_number
            <= self.coordinator.api.spec.meat_probes
        )

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
            return data[self.entity_description.key]  # type: ignore[literal-required]
        return None
