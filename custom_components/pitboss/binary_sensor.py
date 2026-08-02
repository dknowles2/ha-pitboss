"""Binary sensor platform for PitBoss."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, probe_label
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


@dataclass(frozen=True, kw_only=True)
class PBBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes PitBoss binary sensor entity."""

    key: Literal[
        "err1",
        "err2",
        "err3",
        "erL",
        "highTempErr",
        "fanErr",
        "hotErr",
        "motorErr",
        "noPellets",
        "motorState",
        "fanState",
        "hotState",
    ]
    device_class: BinarySensorDeviceClass | None = BinarySensorDeviceClass.PROBLEM
    entity_category: EntityCategory | None = EntityCategory.DIAGNOSTIC


ENTITY_DESCRIPTIONS = (
    PBBinarySensorEntityDescription(
        key="err1",
        icon="mdi:thermometer-alert",
    ),
    PBBinarySensorEntityDescription(
        key="err2",
        icon="mdi:thermometer-alert",
    ),
    PBBinarySensorEntityDescription(
        key="err3",
        icon="mdi:thermometer-alert",
    ),
    PBBinarySensorEntityDescription(
        key="erL",
        name="Startup error",
        icon="mdi:fire-off",
    ),
    PBBinarySensorEntityDescription(
        key="highTempErr",
        name="High temperature error",
        icon="mdi:thermometer-alert",
    ),
    PBBinarySensorEntityDescription(
        key="fanErr",
        name="Fan error",
        icon="mdi:fan-alert",
    ),
    PBBinarySensorEntityDescription(
        key="hotErr",
        name="Igniter error",
        icon="mdi:fire-alert",
    ),
    PBBinarySensorEntityDescription(
        key="motorErr",
        name="Auger error",
        icon="mdi:cog-stop",
    ),
    PBBinarySensorEntityDescription(
        key="noPellets",
        name="No pellets",
        icon="mdi:fire-off",
    ),
    PBBinarySensorEntityDescription(
        key="motorState",
        name="Auger",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=None,
        icon="mdi:filter-cog",
    ),
    PBBinarySensorEntityDescription(
        key="fanState",
        name="Fan",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=None,
        icon="mdi:fan",
    ),
    PBBinarySensorEntityDescription(
        key="hotState",
        name="Igniter",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=None,
        icon="mdi:fire",
    ),
)


# The grill only reports errors for the first three probes.
PROBE_ERROR_KEYS = {"err1": 1, "err2": 2, "err3": 3}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Setup binary_sensor platform."""
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = []
    assert entry.unique_id is not None
    for entity_description in ENTITY_DESCRIPTIONS:
        entities.append(BinarySensor(coordinator, entry.unique_id, entity_description))
    entities.append(ConnectivitySensor(coordinator, entry.unique_id))
    async_add_entities(entities)


class BinarySensor(BaseEntity, BinarySensorEntity):
    """PitBoss binary_sensor class."""

    entity_description: PBBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
        entity_description: PBBinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self.entity_description = entity_description
        self._attr_unique_id = f"{entity_description.key}_{entry_unique_id}"
        # Name these after the physical port too, so a grill with an MPC does
        # not report a "P2 error" as "Probe 2 error".
        probe_number = PROBE_ERROR_KEYS.get(entity_description.key)
        if probe_number is not None:
            self._attr_name = f"{probe_label(coordinator.has_mpc, probe_number)} error"

    @property
    def is_on(self) -> bool | None:
        if data := self.coordinator.data:
            return data.get(self.entity_description.key)
        return None


class ConnectivitySensor(BaseEntity, BinarySensorEntity):
    """Reports whether the grill is currently reachable.

    Unlike every other entity this one stays available while the grill is
    disconnected: an entity that disappears cannot say the grill is offline,
    which is the one thing an offline automation needs to hear.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self._attr_unique_id = f"connectivity_{entry_unique_id}"
        self._attr_name = "Connectivity"

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.api) and self.coordinator.api.is_connected()
