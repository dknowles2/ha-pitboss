"""Number platform for pitboss."""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Coroutine

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.components.number.const import NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.unit_conversion import TemperatureConverter
from pytboss.api import PitBoss

from .const import DEFAULT_MAX_TEMP, DEFAULT_MIN_TEMP, DOMAIN
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity


@dataclass(frozen=True, kw_only=True)
class PitBossNumberEntityDescription(NumberEntityDescription):
    set_fn: Callable[[PitBoss], Callable[[int], Awaitable[dict]]]


PROBE_1_DESCRIPTION = PitBossNumberEntityDescription(
    key="p1Target",
    name="Probe 1 Target",
    device_class=NumberDeviceClass.TEMPERATURE,
    icon="mdi:thermometer",
    set_fn=lambda api: api.set_probe_temperature,
)
PROBE_2_DESCRIPTION = PitBossNumberEntityDescription(
    key="p2Target",
    name="Probe 2 Target",
    device_class=NumberDeviceClass.TEMPERATURE,
    icon="mdi:thermometer",
    set_fn=lambda api: api.set_probe_2_temperature,
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
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of the entity."""
        if data := self.coordinator.data:
            if not data.get("isFahrenheit"):
                return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def available(self) -> bool:
        return bool(self.coordinator.data)

    @property
    def native_value(self) -> int | None:
        """Return the native value of the probe target."""
        if data := self.coordinator.data:
            return data.get(self.entity_description.key)  # type: ignore[literal-required]
        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        await self.entity_description.set_fn(self.coordinator.api)(int(value))

    @property
    def native_step(self) -> float | None:
        """Return the increment/decrement step."""
        if self.native_unit_of_measurement == UnitOfTemperature.FAHRENHEIT:
            return 5.0
        else:
            return 1.0

    @property
    def native_min_value(self) -> float:
        """Return the minimum value."""
        if (min_temp := self.coordinator.api.spec.min_temp) is None:
            min_temp = DEFAULT_MIN_TEMP
        return TemperatureConverter.convert(
            min_temp, UnitOfTemperature.FAHRENHEIT, self.native_unit_of_measurement
        )

    @property
    def native_max_value(self) -> float:
        """Return the maximum value."""
        if (max_temp := self.coordinator.api.spec.max_temp) is None:
            max_temp = DEFAULT_MAX_TEMP
        return TemperatureConverter.convert(
            max_temp, UnitOfTemperature.FAHRENHEIT, self.native_unit_of_measurement
        )
