"""Sensor platform for pitboss."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.components.sensor.const import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, probe_label
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
        probe_number=1,
    ),
    ProbeSensorEntityDescription(
        key="p2Temp",
        probe_number=2,
    ),
    ProbeSensorEntityDescription(
        key="p3Temp",
        probe_number=3,
    ),
    ProbeSensorEntityDescription(
        key="p4Temp",
        probe_number=4,
    ),
)


@dataclass(frozen=True, kw_only=True)
class RecipeSensorEntityDescription(SensorEntityDescription):
    """Describes a PitBoss recipe sensor."""

    key: Literal["recipeTime", "recipeStep"]
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT


RECIPE_ENTITY_DESCRIPTIONS = (
    RecipeSensorEntityDescription(
        key="recipeTime",
        name="Recipe Time",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        # A countdown, not a measurement: long-term statistics of "seconds
        # remaining" mean nothing.
        state_class=None,
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
    entities: list[SensorEntity] = []
    entity_description: PBSensorEntityDescription
    for entity_description in PROBE_ENTITY_DESCRIPTIONS:
        entities.append(ProbeSensor(coordinator, entry.unique_id, entity_description))
    for description in SYS_INFO_DESCRIPTIONS:
        entities.append(SysInfoSensor(coordinator, entry.unique_id, description))
    entities.append(FirmwareSensor(coordinator, entry.unique_id))
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
        self._attr_name = probe_label(coordinator.has_mpc, self.probe_number)

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
        if (data := self.coordinator.data) and not data.get("isFahrenheit", True):
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
        # Missing defaults to off, matching how the power switch reads the
        # same key; this class alone assumed on.
        if data := self.coordinator.data:
            return data.get("moduleIsOn", False) and super().available
        return super().available


class FirmwareSensor(BaseEntity, SensorEntity):
    """The firmware version running on the control board."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chip"

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self._attr_unique_id = f"firmware_{entry_unique_id}"
        self._attr_name = "Firmware version"

    @property
    def available(self) -> bool:
        # Unavailable only until the first successful read -- the coordinator
        # keeps retrying one that failed at setup. Once known the version
        # cannot change outside a reload, so it stays readable while the
        # grill is away rather than following the connection.
        return self.coordinator.firmware_version is not None

    @property
    def native_value(self) -> str | None:
        return self.coordinator.firmware_version


@dataclass(frozen=True, kw_only=True)
class SysInfoSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor backed by the control board's system info."""

    # Key inside the Sys.GetInfo payload.
    info_key: str
    entity_category: EntityCategory = EntityCategory.DIAGNOSTIC


SYS_INFO_DESCRIPTIONS = (
    SysInfoSensorEntityDescription(
        key="controller_uptime",
        info_key="uptime",
        name="Controller uptime",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
    ),
    SysInfoSensorEntityDescription(
        key="controller_free_memory",
        info_key="ram_free",
        name="Controller free memory",
        icon="mdi:memory",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.KILOBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
)


class SysInfoSensor(BaseEntity, SensorEntity):
    """Diagnostic sensor backed by the control board's system info."""

    entity_description: SysInfoSensorEntityDescription

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
        entity_description: SysInfoSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self.entity_description = entity_description
        self._attr_unique_id = f"{entity_description.key}_{entry_unique_id}"

    @property
    def available(self) -> bool:
        # Without the connection check these would keep reporting whatever
        # was read before the grill went away.
        return (
            super().available
            and self.entity_description.info_key in self.coordinator.sys_info
        )

    @property
    def native_value(self):
        return self.coordinator.sys_info.get(self.entity_description.info_key)
