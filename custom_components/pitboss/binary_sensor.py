"""Binary sensor platform for PitBoss."""

from __future__ import annotations
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

from .const import DOMAIN
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


class HABinarySensorEntityDescription(BinarySensorEntityDescription):
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
    ]
    device_class = BinarySensorDeviceClass.PROBLEM
    entity_category = EntityCategory.DIAGNOSTIC


ENTITY_DESCRIPTIONS = (
    HABinarySensorEntityDescription(
        key="err1",
        name="Probe 1 error",
        icon="mdi:thermometer-alert",
    ),
    HABinarySensorEntityDescription(
        key="err2",
        name="Probe 2 error",
        icon="mdi:thermometer-alert",
    ),
    HABinarySensorEntityDescription(
        key="err3",
        name="Probe 3 error",
        icon="mdi:thermometer-alert",
    ),
    HABinarySensorEntityDescription(
        key="erL",
        name="Startup error",
        icon="mdi:fire-off",
    ),
    HABinarySensorEntityDescription(
        key="highTempErr",
        name="High temperature error",
        icon="mdi:thermometer-alert",
    ),
    HABinarySensorEntityDescription(
        key="fanErr",
        name="Fan error",
        icon="mdi:fan-alert",
    ),
    HABinarySensorEntityDescription(
        key="hotErr",
        name="Igniter error",
        icon="mdi:fire-alert",
    ),
    HABinarySensorEntityDescription(
        key="motorErr",
        name="Auger error",
        icon="mdi:cog-stop",
    ),
    HABinarySensorEntityDescription(
        key="noPellets",
        name="No pellets",
        icon="mdi:fire-off",
    ),
    HABinarySensorEntityDescription(
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
    entities: list[BinarySensor] = []
    assert entry.unique_id is not None
    for entity_description in ENTITY_DESCRIPTIONS:
        entities.append(BinarySensor(coordiantor, entry.unique_id, entity_description))
    async_add_entities(entities)


class BinarySensor(BaseEntity, BinarySensorEntity):
    """PitBoss binary_sensor class."""

    entity_description: HABinarySensorEntityDescription

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
        entity_description: HABinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self.entity_description = entity_description
        self._attr_unique_id = f"{entity_description.key}_{entry_unique_id}"

    @property
    def is_on(self) -> bool | None:
        if data := self.coordinator.data:
            return data.get(self.entity_description.key)
        return None
