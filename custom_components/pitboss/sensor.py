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
    device_class = SensorDeviceClass.TEMPERATURE
    state_class = SensorStateClass.MEASUREMENT
    icon = "mdi:thermometer"


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

    key: Literal["recipeStep", "recipeTime"]
    state_class = SensorStateClass.MEASUREMENT


RECIPE_ENTITY_DESCRIPTIONS = (
    RecipeSensorEntityDescription(
        key="recipeStep",
        name="Recipe Step",
        icon="mdi:book-open-variant",
    ),
    RecipeSensorEntityDescription(
        key="recipeTime",
        name="Recipe Time",
        icon="mdi:timer",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
    ),
)


class BaseSensorEntity(BaseEntity, SensorEntity):
    """Base PitBoss sensor entity."""

    entity_description: ProbeSensorEntityDescription | RecipeSensorEntityDescription

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
        entity_description: (
            ProbeSensorEntityDescription | RecipeSensorEntityDescription
        ),
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self.entity_description = entity_description
        if isinstance(self.entity_description, ProbeSensorEntityDescription):
            self.probe_number: int = self.entity_description.probe_number
            self._attr_unique_id = f"probe{self.probe_number}_{entry_unique_id}"
        else:
            self._attr_unique_id = f"{self.entity_description.key}_{entry_unique_id}"

    @property
    def available(self) -> bool:
        return bool(self.coordinator.data) and super().available

    @property
    def native_value(self) -> int | None:
        """Return the native value of the recipe sensor."""
        if data := self.coordinator.data:
            return data.get(self.entity_description.key)
        return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Setup sensor platform."""
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.unique_id is not None
    entities: list[ProbeSensor | RecipeSensor] = []
    for entity_description in PROBE_ENTITY_DESCRIPTIONS:
        entities.append(ProbeSensor(coordinator, entry.unique_id, entity_description))
    for recipe_description in RECIPE_ENTITY_DESCRIPTIONS:
        entities.append(RecipeSensor(coordinator, entry.unique_id, recipe_description))
    async_add_entities(entities)


class ProbeSensor(BaseSensorEntity):
    """PitBoss probe Sensor class."""

    entity_description: ProbeSensorEntityDescription

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added.

        This only applies with first added to the entity registry.
        """
        return self.probe_number <= self.coordinator.api.spec.meat_probes

    @property
    def native_unit_of_measurement(self) -> str | None:
        if data := self.coordinator.data:
            if not data.get("isFahrenheit"):
                return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT


class RecipeSensor(BaseSensorEntity):
    """PitBoss recipe Sensor class."""

    entity_description: RecipeSensorEntityDescription

    @property
    def available(self) -> bool:
        if data := self.coordinator.data:
            return data.get("moduleIsOn", True) and super().available
        return super().available

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added.
        This only applies with first added to the entity registry.
        """
        return self.coordinator.api.spec.json.get("has_recipe_functionality", False)
