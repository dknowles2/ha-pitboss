"""Sensor platform for pitboss."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.components.sensor.const import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


@dataclass(frozen=True, kw_only=True)
class ProbeSensorEntityDescription(SensorEntityDescription):
    """Describes a PitBoss probe sensor."""

    key: Literal["p1Temp", "p2Temp", "p3Temp", "p4Temp"]
    probe_number: int
    device_class: SensorDeviceClass = SensorDeviceClass.TEMPERATURE
    state_class: SensorStateClass = SensorStateClass.MEASUREMENT
    icon: str = "mdi:thermometer"


PROBE_ENTITY_DESCRIPTIONS = (
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


@dataclass(frozen=True, kw_only=True)
class RecipeSensorEntityDescription(SensorEntityDescription):
    """Describes a PitBoss recipe sensor."""

    key: Literal["recipeTime", "recipeStep"]
    state_class: SensorStateClass = SensorStateClass.MEASUREMENT


RECIPE_ENTITY_DESCRIPTIONS = (
    RecipeSensorEntityDescription(
        key="recipeTime",
        name="Recipe Time",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
    ),
    RecipeSensorEntityDescription(
        key="recipeStep",
        name="Recipe Step",
        icon="mdi:format-list-numbered",
    ),
)

type PBSensorEntityDescription = (
    ProbeSensorEntityDescription | RecipeSensorEntityDescription
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_devices: AddEntitiesCallback
):
    """Setup sensor platform."""
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.unique_id is not None
    entities: list[BaseSensorEntity] = []
    entity_description: PBSensorEntityDescription
    for entity_description in PROBE_ENTITY_DESCRIPTIONS:
        entities.append(ProbeSensor(coordinator, entry.unique_id, entity_description))
    if coordinator.api.spec.json.get("has_recipe_functionality", False):
        for entity_description in RECIPE_ENTITY_DESCRIPTIONS:
            entities.append(
                RecipeSensor(coordinator, entry.unique_id, entity_description)
            )
    async_add_devices(entities)


class BaseSensorEntity(BaseEntity, SensorEntity):
    """Base class for PitBoss sensor entities."""

    entity_description: PBSensorEntityDescription

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
        entity_description: PBSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self.entity_description = entity_description

    @property
    def native_value(self) -> int | None:
        """Return the native value of the sensor."""
        if data := self.coordinator.data:
            return data.get(self.entity_description.key)
        return None


class ProbeSensor(BaseSensorEntity):
    """PitBoss probe Sensor class."""

    entity_description: ProbeSensorEntityDescription

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
        entity_description: ProbeSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_unique_id, entity_description)
        self.probe_number = self.entity_description.probe_number
        self._attr_unique_id = f"probe{self.probe_number}_{entry_unique_id}"

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


class RecipeSensor(BaseSensorEntity):
    """PitBoss recipe Sensor class."""

    entity_description: RecipeSensorEntityDescription

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
        entity_description: RecipeSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_unique_id, entity_description)
        self._attr_unique_id = f"{entity_description.key}_{entry_unique_id}"

    @property
    def available(self) -> bool:
        if data := self.coordinator.data:
            return data.get("moduleIsOn", True) and super().available
        return super().available
