"""Switch platform for pitboss."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LOGGER
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_devices: AddEntitiesCallback
):
    """Setup sensor platform."""
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.unique_id is not None
    async_add_devices(
        [
            PowerSwitch(coordinator, entry.unique_id),
            PrimerSwitch(coordinator, entry.unique_id),
        ]
    )


class BaseSwitchEntity(BaseEntity, SwitchEntity):
    """Base PitBoss switch entity."""

    def __init__(
        self, coordinator: PitBossDataUpdateCoordinator, entry_unique_id: str
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self._attr_unique_id = f"{self.entity_description.key}_{self.entry_unique_id}"

    @property
    def is_on(self) -> bool | None:
        if data := self.coordinator.data:
            return data.get(self.entity_description.key)  # type: ignore[return-value]
        return None


class PowerSwitch(BaseSwitchEntity):
    """PitBoss power switch."""

    entity_description = SwitchEntityDescription(
        key="moduleIsOn",
        name="Module power",
        device_class=SwitchDeviceClass.SWITCH,
    )

    async def async_turn_on(self, **_: Any) -> None:
        """Turn on the switch."""
        LOGGER.warn("For safety reasons, the grill cannot be turned on remotely.")

    async def async_turn_off(self, **_: Any) -> None:
        """Turn off the switch."""
        await self.coordinator.api.turn_grill_off()


class PrimerSwitch(BaseSwitchEntity):
    """PitBoss primer switch."""

    entity_description = SwitchEntityDescription(
        key="primeState",
        name="Prime",
        device_class=SwitchDeviceClass.SWITCH,
    )

    async def async_turn_on(self, **_: Any) -> None:
        """Turn on the primer motor."""
        await self.coordinator.api.turn_primer_motor_on()

    async def async_turn_off(self, **_: Any) -> None:
        """Turn off the primer motor."""
        await self.coordinator.api.turn_primer_motor_off()
