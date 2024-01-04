"""Climate platform for PitBoss."""

from __future__ import annotations

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    ClimateEntityDescription,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Setup binary_sensor platform."""
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GrillClimate(coordinator, entry.unique_id)])


class GrillClimate(BaseEntity, ClimateEntity):
    """PitBoss climate class for the grill."""

    _attr_hvac_mode = HVACMode.HEAT
    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_target_temperature_step = 5

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self.entity_description = ClimateEntityDescription(
            key="grill_temperature",
            name="Grill temperature",
        )
        self._attr_unique_id = f"{self.entity_description.key}_{entry_unique_id}"
        self._attr_min_temp = self.coordinator.grill_spec.min_temp
        self._attr_max_temp = self.coordinator.grill_spec.max_temp

    @property
    def temperature_unit(self) -> str:
        if data := self.coordinator.data:
            if not data.get("isFahrenheit", False):
                return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def current_temperature(self) -> float | None:
        if data := self.coordinator.data:
            if "grillTemp" in data:
                return float(data["grillTemp"])
        return None

    @property
    def target_temperature(self) -> float | None:
        if data := self.coordinator.data:
            if "grillSetTemp" in data:
                return float(data["grillSetTemp"])
        return None

    async def async_set_temperature(self, **kwargs) -> None:
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await self.coordinator.api.set_grill_temperature(temp)

    @property
    def hvac_action(self) -> HVACAction | str | None:
        if data := self.coordinator.data:
            if data.get("hotState", False):
                return HVACAction.HEATING
            if data.get("fanState", False):
                return HVACAction.FAN
            return HVACAction.IDLE
        return None
