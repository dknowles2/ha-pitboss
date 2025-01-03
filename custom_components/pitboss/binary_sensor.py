"""Binary sensor platform for PitBoss."""

from __future__ import annotations

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

ENTITY_DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="err1",
        name="Probe 1 error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="err2",
        name="Probe 2 error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="err3",
        name="Probe 3 error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="erL",
        name="Startup error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="highTempErr",
        name="High temperature error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="fanErr",
        name="Fan error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="hotErr",
        name="Igniter error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="motorErr",
        name="Auger error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="noPellets",
        name="No pellets",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="motorState",
        name="Auger",
        device_class=BinarySensorDeviceClass.RUNNING,
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

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
        entity_description: BinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self.entity_description = entity_description
        self._attr_unique_id = f"{entity_description.key}_{entry_unique_id}"

    @property
    def is_on(self) -> bool | None:
        if data := self.coordinator.data:
            return data.get(self.entity_description.key)  # type: ignore[return-value]
        return None
