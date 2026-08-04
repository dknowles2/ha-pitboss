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
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import (
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DOMAIN,
    LOGGER,
    MCU_SETTLE_SECONDS,
)
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Setup binary_sensor platform."""
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
        self._pending_target: float | None = None
        self._cancel_settle: CALLBACK_TYPE | None = None

    async def async_added_to_hass(self) -> None:
        """Register the one removal callback this entity needs."""
        await super().async_added_to_hass()
        # Registered once rather than per set: `async_on_remove` only
        # appends, so re-registering would grow the list for the life of
        # the entity.
        self.async_on_remove(self._cancel_pending_settle)

    @callback
    def _cancel_pending_settle(self) -> None:
        if self._cancel_settle is not None:
            self._cancel_settle()
            self._cancel_settle = None

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
            return 5.0
        else:
            return 1.0

    @property
    def min_temp(self) -> float:
        if accepted := self._accepted_setpoints:
            return min(accepted)
        from_unit = UnitOfTemperature.FAHRENHEIT
        to_unit = self.temperature_unit
        if (min_temp := self.coordinator.api.spec.min_temp) is None:
            min_temp = DEFAULT_MIN_TEMP
        return TemperatureConverter.convert(min_temp, from_unit, to_unit)

    @property
    def max_temp(self) -> float:
        if accepted := self._accepted_setpoints:
            return max(accepted)
        from_unit = UnitOfTemperature.FAHRENHEIT
        to_unit = self.temperature_unit
        if (max_temp := self.coordinator.api.spec.max_temp) is None:
            max_temp = DEFAULT_MAX_TEMP
        return TemperatureConverter.convert(max_temp, from_unit, to_unit)

    @property
    def temperature_unit(self) -> str:
        if (data := self.coordinator.data) and not data.get("isFahrenheit", False):
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

        Shows what was asked until the grill confirms it: the board wipes
        its cached status the moment it forwards a command to the MCU, so
        the next poll still carries the old setpoint and the slider would
        appear to snap back. The select and the probe targets already work
        this way; the climate card was the one control that did not.
        """
        if self._pending_target is not None:
            return self._pending_target
        if (data := self.coordinator.data) and (
            temp := data.get("grillSetTemp")
        ) is not None:
            return float(temp)
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._pending_target is not None:
            reported = (self.coordinator.data or {}).get("grillSetTemp")
            if reported is not None and float(reported) == self._pending_target:
                self._pending_target = None
        super()._handle_coordinator_update()

    async def async_set_temperature(self, **kwargs) -> None:
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        # Snapped here as well as in pytboss -- deliberately the same
        # arithmetic -- so what is held and shown is the value the board
        # will actually report, not the one it will silently correct.
        wanted = float(temp)
        if accepted := self._accepted_setpoints:
            asked = wanted
            wanted = min(accepted, key=lambda value: abs(value - asked))
        await self.coordinator.api.set_grill_temperature(int(wanted))
        self._pending_target = wanted
        self.async_write_ha_state()
        # The MCU reports back within a couple of seconds; an immediate
        # refresh would only read the cleared status. A second set inside
        # the window replaces the timer rather than queueing another.
        self._cancel_pending_settle()
        self._cancel_settle = async_call_later(
            self.hass, MCU_SETTLE_SECONDS, self._async_confirm
        )

    async def _async_confirm(self, _now) -> None:
        self._cancel_settle = None
        await self.coordinator.async_request_refresh()
        # One settle window is all the pending value is for. If the refresh
        # confirmed it, `_handle_coordinator_update` has already cleared it;
        # if the grill did not take it, follow the grill rather than assert
        # a value it will never report.
        if self._pending_target is not None:
            self._pending_target = None
            self.async_write_ha_state()

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
