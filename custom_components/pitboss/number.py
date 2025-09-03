"""Number platform for pitboss."""

from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.components.number.const import NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.unit_conversion import TemperatureConverter
from pytboss.api import PitBoss

from .const import DEFAULT_PROBE_MIN_TEMP, DEFAULT_PROBE_MAX_TEMP, DOMAIN
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


@dataclass(frozen=True, kw_only=True)
class PitBossNumberEntityDescription(NumberEntityDescription):
    key: Literal["p1Target", "p2Target"]
    set_fn: Callable[[PitBoss], Callable[[int], Awaitable[dict]]]
    device_class: NumberDeviceClass = NumberDeviceClass.TEMPERATURE
    icon: str = "mdi:thermometer"
    matching_probe_key: Literal["p1Temp", "p2Temp"]


PROBE_1_DESCRIPTION = PitBossNumberEntityDescription(
    key="p1Target",
    name="Probe 1 Target",
    set_fn=lambda api: api.set_probe_temperature,
    matching_probe_key="p1Temp",
)
PROBE_2_DESCRIPTION = PitBossNumberEntityDescription(
    key="p2Target",
    name="Probe 2 Target",
    set_fn=lambda api: api.set_probe_2_temperature,
    matching_probe_key="p2Temp",
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_devices: AddEntitiesCallback
):
    """Setup number platformm."""
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.unique_id is not None
    entities = [
        TargetProbeTemperature(coordinator, entry.unique_id, PROBE_1_DESCRIPTION)
    ]
    if "set-probe-2-temperature" in coordinator.api.spec.control_board.commands:
        entities.append(
            TargetProbeTemperature(coordinator, entry.unique_id, PROBE_2_DESCRIPTION)
        )
    async_add_devices(entities)


class TargetProbeTemperature(BaseEntity, NumberEntity):
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

    @property
    def native_unit_of_measurement(self) -> UnitOfTemperature | None:
        """Return the unit of measurement of the entity."""
        if data := self.coordinator.data:
            if not data.get("isFahrenheit"):
                return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def native_step(self) -> float:
        """Return the step size of the number."""
        if self.native_unit_of_measurement == UnitOfTemperature.FAHRENHEIT:
            return 1.0  # 5.0
        else:
            return 1.0

    @property
    def available(self) -> bool:
        if data := self.coordinator.data:
            return (
                data.get(self.entity_description.matching_probe_key) is not None
                and bool(data.get("moduleIsOn", True))
                and super().available
            )
        return super().available

    @property
    def native_value(self) -> int | None:
        """Return the native value of the probe target."""
        if data := self.coordinator.data:
            return data.get(self.entity_description.key)
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        await self.entity_description.set_fn(self.coordinator.api)(int(value))

    @property
    def native_min_value(self) -> float:
        """Return the minimum value."""
        min_temp = DEFAULT_PROBE_MIN_TEMP
        return TemperatureConverter.convert(
            min_temp, UnitOfTemperature.FAHRENHEIT, self.native_unit_of_measurement
        )

    @property
    def native_max_value(self) -> float:
        """Return the maximum value."""
        max_temp = DEFAULT_PROBE_MAX_TEMP
        return TemperatureConverter.convert(
            max_temp, UnitOfTemperature.FAHRENHEIT, self.native_unit_of_measurement
        )
