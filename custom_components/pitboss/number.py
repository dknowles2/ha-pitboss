"""Number platform for pitboss."""

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.components.number.const import NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import DEFAULT_MAX_TEMP, DEFAULT_MIN_TEMP, DOMAIN
from .coordinator import PitBossDataUpdateCoordinator
from .entity import BaseEntity

ENTITY_DESCRIPTIONS = (
    NumberEntityDescription(
        key="p1Target",
        name="Probe 1 Target",
        device_class=NumberDeviceClass.TEMPERATURE,
        icon="mdi:thermometer",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_devices: AddEntitiesCallback
):
    """Setup number platformm."""
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.unique_id is not None
    entities = []
    for entity_description in ENTITY_DESCRIPTIONS:
        entities.append(
            TargetProbeTemperature(coordinator, entry.unique_id, entity_description)
        )
    async_add_devices(entities)


class TargetProbeTemperature(BaseEntity, NumberEntity):
    """PitBoss target probe temperature class."""

    def __init__(
        self,
        coordinator: PitBossDataUpdateCoordinator,
        entry_unique_id: str,
        entity_description: NumberEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_unique_id)
        self.entity_description: NumberEntityDescription = entity_description
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
        await self.coordinator.api.set_probe_temperature(int(value))

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
