"""Climate platform for PitBoss."""

from __future__ import annotations

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
)
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, GRILL_CELSIUS_STEP, GRILL_FAHRENHEIT_STEP, LOGGER
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Setup climate platform."""
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.unique_id is not None
    async_add_entities([GrillClimate(coordinator, entry.unique_id)])


class GrillClimate(BaseEntity, ClimateEntity):
    """PitBoss climate class for the grill."""

    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]  # noqa: RUF012
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_OFF
    )

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

    @property
    def _accepted_setpoints(self) -> list[float]:
        return self.coordinator.accepted_setpoints(self.temperature_unit)

    @property
    def extra_state_attributes(self) -> dict[str, list[float]] | None:
        """Publish the setpoints the board accepts.

        The board silently ignores anything else, so a dashboard offering a
        free slider is misleading. This lets one offer only what works.
        """
        if accepted := self._accepted_setpoints:
            return {"allowed_setpoints": accepted}
        return None

    @property
    def target_temperature_step(self) -> float:
        if self.temperature_unit == UnitOfTemperature.FAHRENHEIT:
            return float(GRILL_FAHRENHEIT_STEP)
        else:
            return float(GRILL_CELSIUS_STEP)

    @property
    def min_temp(self) -> float:
        # The setpoint list, with nothing behind it. A fallback on
        # `spec.min_temp` used to sit here, but every catalogued grill has
        # increments in both units, and a grill without them cannot even be
        # constructed -- `Grill.from_dict` raises parsing the empty
        # increment string long before an entity exists. The bounds come
        # from the same list that feeds `allowed_setpoints` and the snap,
        # so all three always agree.
        return min(self._accepted_setpoints)

    @property
    def max_temp(self) -> float:
        return max(self._accepted_setpoints)

    @property
    def temperature_unit(self) -> str:
        # Absent defaults to Fahrenheit -- the same default pytboss snaps
        # setpoints with, so the unit shown and the unit commanded agree
        # even on a state built from a status frame alone.
        if (data := self.coordinator.data) and not data.get("isFahrenheit", True):
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def current_temperature(self) -> float | None:
        # Checked for None, not just presence: the boards' own parsing
        # routines put null on the wire for the no-reading sentinel (960),
        # the same way an unplugged probe reads. `float(None)` would raise
        # on every state write for as long as the chamber sensor is out.
        if (data := self.coordinator.data) and (
            temp := data.get("grillTemp")
        ) is not None:
            return float(temp)
        return None

    @property
    def target_temperature(self) -> float | None:
        """The grill's setpoint, or the one just asked for.

        Held by the coordinator rather than here: the grill setpoint number
        is a second control over the same setting, and a value held by
        whichever control happened to be used would leave the other showing
        the previous setpoint for the length of the settle window.
        """
        return self.coordinator.grill_setpoint()

    async def async_set_temperature(self, **kwargs) -> None:
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await self.coordinator.async_set_grill_setpoint(float(temp))

    async def async_turn_off(self) -> None:
        """Turn off the grill."""
        # Deliberately does not touch the setpoint. It is the user's
        # setting, it has no effect while the grill is off, and it is what
        # the grill will use next time it is lit.
        await self.coordinator.api.turn_grill_off()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
        elif hvac_mode == HVACMode.HEAT:
            LOGGER.warning(
                "Not lighting the grill from here. Use the pitboss.start_grill "
                "action, which has to be enabled in the integration options first."
            )

    @property
    def hvac_mode(self) -> HVACMode | None:
        if data := self.coordinator.data:
            if data.get("moduleIsOn", False):
                return HVACMode.HEAT
            else:
                return HVACMode.OFF
        return None

    @property
    def hvac_action(self) -> HVACAction | None:
        if data := self.coordinator.data:
            if data.get("hotState", False):
                return HVACAction.HEATING
            elif not data.get("moduleIsOn", False) and data.get("fanState", False):
                return HVACAction.COOLING
            elif data.get("fanState", False):
                return HVACAction.FAN
            elif not data.get("moduleIsOn", False):
                return HVACAction.OFF
            else:
                return HVACAction.IDLE
        return None
