"""Light platform for PitBoss."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_devices: AddEntitiesCallback
):
    """Setup light platform."""
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.unique_id is not None
    if coordinator.api.spec.has_lights:
        async_add_devices([GrillLight(coordinator, entry.unique_id)])


class GrillLight(BaseEntity, LightEntity):
    """PitBoss light class."""

    def __init__(
        self, coordinator: PitBossDataUpdateCoordinator, entity_unique_id: str
    ) -> None:
        super().__init__(coordinator, entity_unique_id)
        self._attr_unique_id = f"light_{entity_unique_id}"
        self._attr_name = "Light"

    @property
    def available(self) -> bool:
        return bool(self.coordinator.data)

    @property
    def is_on(self) -> bool | None:
        """Returns True if the light is on."""
        if data := self.coordinator.data:
            return data.get("lightState")
        return None

    async def async_turn_on(self, **_: Any) -> None:
        """Turn on the light."""
        await self.coordinator.api.turn_light_on()

    async def async_turn_off(self, **_: Any) -> None:
        """Turn off the light."""
        await self.coordinator.api.turn_light_off()
