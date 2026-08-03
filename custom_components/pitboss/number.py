"""Number platform for pitboss."""

from dataclasses import dataclass
from typing import Literal

from homeassistant.components.number import NumberEntityDescription, RestoreNumber
from homeassistant.components.number.const import NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import (
    DEFAULT_PROBE_CELSIUS_STEP,
    DEFAULT_PROBE_FAHRENHEIT_STEP,
    DEFAULT_PROBE_MAX_TEMP,
    DEFAULT_PROBE_MIN_TEMP,
    DOMAIN,
    probe_label,
)
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


@dataclass(frozen=True, kw_only=True)
class PitBossNumberEntityDescription(NumberEntityDescription):
    key: Literal["p1Target", "p2Target", "p3Target", "p4Target"]
    probe_number: Literal[1, 2, 3, 4]
    device_class: NumberDeviceClass = NumberDeviceClass.TEMPERATURE
    icon: str = "mdi:thermometer"


PROBE_DESCRIPTIONS = (
    PitBossNumberEntityDescription(key="p1Target", probe_number=1),
    PitBossNumberEntityDescription(key="p2Target", probe_number=2),
    PitBossNumberEntityDescription(key="p3Target", probe_number=3),
    PitBossNumberEntityDescription(key="p4Target", probe_number=4),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_devices: AddEntitiesCallback
):
    """Setup number platform."""
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.unique_id is not None
    probe_count = coordinator.api.spec.meat_probes or 1
    entities = [
        TargetProbeTemperature(coordinator, entry.unique_id, description)
        for description in PROBE_DESCRIPTIONS
        if description.probe_number <= probe_count
    ]
    if entities:
        async_add_devices(entities)


class TargetProbeTemperature(BaseEntity, RestoreNumber):
    """PitBoss target probe temperature class."""

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
        entity_description: PitBossNumberEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self.entity_description: PitBossNumberEntityDescription = entity_description
        self._attr_unique_id = f"{entity_description.key}_{entry_unique_id}"
        label = probe_label(coordinator.has_mpc, entity_description.probe_number)
        self._attr_name = f"{label} target"

    async def async_added_to_hass(self) -> None:
        """Restore the target we last set for this probe.

        The grill's own store is wiped when it is switched off, so without
        this a target set on a cold grill would not survive a Home Assistant
        restart. Anything the grill is holding wins over the restored value.
        """
        await super().async_added_to_hass()
        probe_number = self.entity_description.probe_number
        if self.coordinator.probe_target(probe_number) is not None:
            return
        last_data = await self.async_get_last_number_data()
        if last_data is None or last_data.native_value is None:
            return
        # `probe_targets` holds grill-unit values; the restored one carries the
        # unit it was displayed in, which the grill may since have changed.
        value = last_data.native_value
        stored_unit = last_data.native_unit_of_measurement
        if stored_unit and stored_unit != self.coordinator.grill_unit:
            value = TemperatureConverter.convert(
                value, stored_unit, self.coordinator.grill_unit
            )
        self.coordinator.restored_targets[probe_number] = round(value)

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement of the entity."""
        return self.coordinator.grill_unit

    @property
    def native_step(self) -> float:
        """Return the step size of the number."""
        if self.native_unit_of_measurement == UnitOfTemperature.FAHRENHEIT:
            return DEFAULT_PROBE_FAHRENHEIT_STEP
        return DEFAULT_PROBE_CELSIUS_STEP

    @property
    def available(self) -> bool:
        # Deliberately not gated on the probe being plugged in: the grill
        # accepts a target for an empty port, so it can be dialled in before
        # the probe goes into the meat.
        return super().available

    @property
    def native_value(self) -> float | None:
        """Return the probe target, in the grill's own unit.

        Deliberately an int: coercing to float would render the state as
        "165.0" where it has always been "165".
        """
        return self.coordinator.probe_target(self.entity_description.probe_number)

    async def async_set_native_value(self, value: float) -> None:
        """Set the target, by whichever route this probe supports."""
        await self.coordinator.async_set_probe_target(
            self.entity_description.probe_number, round(value)
        )
        self.coordinator.async_update_listeners()

    @property
    def native_min_value(self) -> float:
        """Return the minimum value."""
        return TemperatureConverter.convert(
            DEFAULT_PROBE_MIN_TEMP,
            UnitOfTemperature.FAHRENHEIT,
            self.native_unit_of_measurement,
        )

    @property
    def native_max_value(self) -> float:
        """Return the maximum value."""
        return TemperatureConverter.convert(
            DEFAULT_PROBE_MAX_TEMP,
            UnitOfTemperature.FAHRENHEIT,
            self.native_unit_of_measurement,
        )
