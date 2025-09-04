"""Binary sensor platform for PitBoss."""

from __future__ import annotations
from typing import Literal

from attr import dataclass
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


@dataclass(frozen=True, kw_only=True)
class PBBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a PitBoss probe sensor."""

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
    ]
    device_class = BinarySensorDeviceClass.PROBLEM
    entity_category = EntityCategory.DIAGNOSTIC


ENTITY_DESCRIPTIONS = (
    PBBinarySensorEntityDescription(
        key="err1",
        name="Probe 1 error",
    ),
    PBBinarySensorEntityDescription(
        key="err2",
        name="Probe 2 error",
    ),
    PBBinarySensorEntityDescription(
        key="err3",
        name="Probe 3 error",
    ),
    PBBinarySensorEntityDescription(
        key="erL",
        name="Startup error",
    ),
    PBBinarySensorEntityDescription(
        key="highTempErr",
        name="High temperature error",
    ),
    PBBinarySensorEntityDescription(
        key="fanErr",
        name="Fan error",
    ),
    PBBinarySensorEntityDescription(
        key="hotErr",
        name="Igniter error",
    ),
    PBBinarySensorEntityDescription(
        key="motorErr",
        name="Auger error",
    ),
    PBBinarySensorEntityDescription(
        key="noPellets",
        name="No pellets",
    ),
    PBBinarySensorEntityDescription(
        key="motorState",
        name="Auger",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=None,
        icon="mdi:filter-cog",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Setup binary_sensor platform."""
    coordiantor: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    assert entry.unique_id is not None
    for entity_description in ENTITY_DESCRIPTIONS:
        entities.append(BinarySensor(coordiantor, entry.unique_id, entity_description))
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

    @property
    def is_on(self) -> bool | None:
        if data := self.coordinator.data:
            return data.get(self.entity_description.key)
        return None
