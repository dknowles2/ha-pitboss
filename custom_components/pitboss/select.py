"""Select platform for pitboss."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN, MCU_SETTLE_SECONDS
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity

# The MCU is polled every couple of seconds; give it time to report back.

UNIT_CELSIUS = UnitOfTemperature.CELSIUS
UNIT_FAHRENHEIT = UnitOfTemperature.FAHRENHEIT

# Board command slugs that switch the unit the grill itself works in.
UNIT_COMMANDS = {
    UNIT_CELSIUS: "set-celsius",
    UNIT_FAHRENHEIT: "set-fahrenheit",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Setup select platform."""
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.unique_id is not None
    commands = coordinator.api.spec.control_board.commands
    if all(slug in commands for slug in UNIT_COMMANDS.values()):
        async_add_entities([GrillTemperatureUnitSelect(coordinator, entry.unique_id)])


class GrillTemperatureUnitSelect(BaseEntity, SelectEntity):
    """The temperature unit the grill itself displays and reports in.

    This changes a setting on the grill, not how Home Assistant presents
    values -- every temperature the board reports follows it.
    """

    _attr_icon = "mdi:temperature-celsius"

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self._attr_unique_id = f"grill_temperature_unit_{entry_unique_id}"
        self._attr_name = "Grill temperature unit"
        # Set per instance rather than on the class: the base declares it as
        # an instance variable, so a class-level list is both a mutable class
        # attribute and a mypy override error.
        self._attr_options = [UNIT_CELSIUS, UNIT_FAHRENHEIT]
        self._pending_option: str | None = None
        self._cancel_settle: CALLBACK_TYPE | None = None

    async def async_added_to_hass(self) -> None:
        """Register the one removal callback this entity needs."""
        await super().async_added_to_hass()
        # Registered once rather than per selection: `async_on_remove` only
        # appends, so re-registering would grow the list for the life of the
        # entity. This cancels whichever timer is current.
        self.async_on_remove(self._cancel_pending_settle)

    @callback
    def _cancel_pending_settle(self) -> None:
        if self._cancel_settle is not None:
            self._cancel_settle()
            self._cancel_settle = None

    @property
    def _reported_option(self) -> str | None:
        if data := self.coordinator.data:
            return UNIT_FAHRENHEIT if data.get("isFahrenheit", True) else UNIT_CELSIUS
        return None

    @property
    def current_option(self) -> str | None:
        # Show what we asked for until the grill confirms it: the board wipes
        # its cached status the moment it forwards a command to the MCU, so
        # the next poll still carries the old unit and the UI would appear to
        # snap back.
        return self._pending_option or self._reported_option

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._pending_option and self._reported_option == self._pending_option:
            self._pending_option = None
        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        """Switch the unit the grill works in."""
        await self.coordinator.api.set_temperature_unit(
            fahrenheit=option == UNIT_FAHRENHEIT
        )
        self._pending_option = option
        self.async_write_ha_state()
        # The MCU reports back within a couple of seconds; an immediate
        # refresh would only read the cleared status. A second selection
        # inside the window replaces the timer rather than queueing another.
        self._cancel_pending_settle()
        self._cancel_settle = async_call_later(
            self.hass, MCU_SETTLE_SECONDS, self._async_confirm
        )

    async def _async_confirm(self, _now) -> None:
        self._cancel_settle = None
        await self.coordinator.async_request_refresh()
        # One settle window is all the pending value is for. If the refresh
        # confirmed the change, `_handle_coordinator_update` has already
        # cleared it; if the grill did not take it, follow the grill rather
        # than assert a value it will never report.
        if self._pending_option is not None:
            self._pending_option = None
            self.async_write_ha_state()
