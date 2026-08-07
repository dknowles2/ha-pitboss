from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import cast
from unittest.mock import Mock

import pytest
from conftest import enable_entity, get_entity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_system import METRIC_SYSTEM
from pytboss.grills import StateDict
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.pitboss.const import (
    DOMAIN,
    STANDBY_SCAN_INTERVAL,
    SYS_INFO_INTERVAL,
)
from custom_components.pitboss.coordinator import PitBossDataUpdateCoordinator
from custom_components.pitboss.sensor import ProbeSensor


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_probe_sensors_enabled_by_meat_probes(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    # PBV4PS2 has 2 meat probes, so probes 1-2 are enabled by default and
    # probes 3-4 are registered but disabled.
    await mock_add_config_entry()
    registry = er.async_get(hass)
    assert hass.states.get("sensor.mygrill_mpc") is not None
    assert hass.states.get("sensor.mygrill_p2") is not None
    assert hass.states.get("sensor.mygrill_p3") is None
    assert hass.states.get("sensor.mygrill_p4") is None
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, "probe3_mygrillid")
    assert entity_id is not None
    entry = registry.async_get(entity_id)
    assert entry is not None
    assert entry.disabled_by is not None


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_recipe_sensors_created_when_supported(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    assert hass.states.get("sensor.mygrill_recipe_time") is not None
    assert hass.states.get("sensor.mygrill_recipe_step") is not None


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_recipe_time_records_no_statistics(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """A countdown is not a measurement; statistics of it mean nothing."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data(
        cast(StateDict, {"moduleIsOn": True, "recipeTime": 90})
    )
    await hass.async_block_till_done()
    state = hass.states.get("sensor.mygrill_recipe_time")
    assert state is not None
    assert state.state == "90"
    assert "state_class" not in state.attributes

    # The step index is not a measurement either.
    coordinator.async_set_updated_data(
        cast(StateDict, {"moduleIsOn": True, "recipeStep": 2})
    )
    await hass.async_block_till_done()
    state = hass.states.get("sensor.mygrill_recipe_step")
    assert state is not None
    assert "state_class" not in state.attributes


@pytest.mark.parametrize("model", ["PB2180LK"])
async def test_recipe_sensors_absent_when_unsupported(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    # Anchored on a sensor PB2180LK does have. Absence alone passes if
    # the platform never set up at all, or if an entity id is renamed --
    # this is the only absence assertion in the suite without a sibling
    # to hold it down.
    assert hass.states.get("sensor.mygrill_probe_1") is not None
    assert hass.states.get("sensor.mygrill_recipe_time") is None
    assert hass.states.get("sensor.mygrill_recipe_step") is None


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_probe_native_value_and_unit(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    # hass units default to US customary (Fahrenheit), so the sensor's
    # native Celsius value gets auto-converted for display.
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"p1Temp": 165, "isFahrenheit": True})
    await hass.async_block_till_done()
    state = hass.states.get("sensor.mygrill_mpc")
    assert state is not None
    assert state.state == "165"
    assert state.attributes["unit_of_measurement"] == "°F"

    coordinator.async_set_updated_data({"p1Temp": 74, "isFahrenheit": False})
    await hass.async_block_till_done()
    state = hass.states.get("sensor.mygrill_mpc")
    assert state is not None
    assert state.state == "165.2"
    assert state.attributes["unit_of_measurement"] == "°F"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_probe_absent_unit_flag_reads_as_fahrenheit(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """Without isFahrenheit the probe value must be declared Fahrenheit.

    Declaring Celsius made Home Assistant convert a raw 165 into 329 F for
    the status-frame-only window.
    """
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"p1Temp": 165})
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mygrill_mpc")
    assert state is not None
    assert state.state == "165"
    assert state.attributes["unit_of_measurement"] == "\u00b0F"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_recipe_sensor_availability(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    # recipeStep is really an int at runtime, despite pytboss's StateDict
    # (incorrectly) typing it as bool.
    coordinator.async_set_updated_data(
        cast(StateDict, {"moduleIsOn": False, "recipeStep": 2})
    )
    await hass.async_block_till_done()
    state = hass.states.get("sensor.mygrill_recipe_step")
    assert state is not None
    assert state.state == "unavailable"

    coordinator.async_set_updated_data(
        cast(StateDict, {"moduleIsOn": True, "recipeStep": 2})
    )
    await hass.async_block_till_done()
    state = hass.states.get("sensor.mygrill_recipe_step")
    assert state is not None
    assert state.state == "2"

    # A frame that carries no moduleIsOn reads as off, the same default the
    # power switch applies to the same key.
    coordinator.async_set_updated_data(cast(StateDict, {"recipeStep": 2}))
    await hass.async_block_till_done()
    state = hass.states.get("sensor.mygrill_recipe_step")
    assert state is not None
    assert state.state == "unavailable"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_native_value_none_without_data(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    entity = get_entity(hass, "sensor", "sensor.mygrill_mpc", ProbeSensor)
    assert entity.native_value is None


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_firmware_version_sensor(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """Read once at setup, and reported on the device too."""
    mock_pitboss.get_firmware_version.return_value = {"firmwareVersion": "0.5.7"}
    await mock_add_config_entry()

    state = hass.states.get("sensor.mygrill_firmware_version")
    assert state is not None
    assert state.state == "0.5.7"

    device = dr.async_get(hass).async_get_device({(DOMAIN, "mygrill")})
    assert device is not None
    assert device.sw_version == "0.5.7"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_firmware_sensor_recovers_from_a_failed_first_read(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """A failed read must not break setup, and is retried until it works.

    The sensor exists from the start -- merely unavailable -- because a
    grill that is slow to answer once should not lose the entity until
    the integration is reloaded.
    """
    mock_pitboss.get_firmware_version.side_effect = RuntimeError("nope")
    entry = await mock_add_config_entry()

    state = hass.states.get("sensor.mygrill_firmware_version")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE

    # Retries follow the diagnostics cadence, not the poll rate: a poll
    # landing inside the gate must not ask again.
    attempts = mock_pitboss.get_firmware_version.await_count
    mock_pitboss.get_firmware_version.side_effect = None
    mock_pitboss.get_firmware_version.return_value = {"firmwareVersion": "0.5.7"}
    async_fire_time_changed(
        hass, dt_util.utcnow() + STANDBY_SCAN_INTERVAL + timedelta(seconds=1)
    )
    await hass.async_block_till_done()

    assert mock_pitboss.get_firmware_version.await_count == attempts
    state = hass.states.get("sensor.mygrill_firmware_version")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE

    # The gate elapses (monotonic time cannot be frozen from a test, so it
    # is aged directly) and the next poll's read succeeds.
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator._firmware_attempted_at is not None
    coordinator._firmware_attempted_at -= SYS_INFO_INTERVAL + 1
    async_fire_time_changed(
        hass, dt_util.utcnow() + STANDBY_SCAN_INTERVAL + timedelta(seconds=1)
    )
    await hass.async_block_till_done()

    state = hass.states.get("sensor.mygrill_firmware_version")
    assert state is not None
    assert state.state == "0.5.7"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_controller_diagnostics(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    mock_pitboss.config.get_info.return_value = {"uptime": 3600, "ram_free": 61000}
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"moduleIsOn": False})
    await hass.async_block_till_done()

    uptime = hass.states.get("sensor.mygrill_controller_uptime")
    assert uptime is not None
    assert uptime.state == "3600"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_controller_diagnostics_are_not_read_every_poll(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """They change slowly; a round trip per poll would be wasted."""
    mock_pitboss.config.get_info.return_value = {"uptime": 3600, "ram_free": 61000}
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    mock_pitboss.config.get_info.reset_mock()

    await coordinator._async_update_data()
    await coordinator._async_update_data()
    mock_pitboss.config.get_info.assert_not_awaited()


@pytest.mark.parametrize("model", ["PB2180LK"])
async def test_probes_keep_plain_numbering_without_mpc(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """Only grills with a control port get the MPC/P2 naming."""
    await mock_add_config_entry()
    assert hass.states.get("sensor.mygrill_probe_1") is not None
    assert hass.states.get("sensor.mygrill_mpc") is None


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_a_late_firmware_read_reaches_the_device_page(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """The retry populated the sensor but not the device registry.

    `device_info` is only read when the device is created, so a version that
    arrives after setup had nowhere to go: the sensor showed it while the
    device page stayed blank until the integration was reloaded.
    """
    mock_pitboss.get_firmware_version.side_effect = RuntimeError("nope")
    entry = await mock_add_config_entry()

    registry = dr.async_get(hass)
    device = registry.async_get_device(identifiers={(DOMAIN, "mygrill")})
    assert device is not None
    assert device.sw_version is None

    mock_pitboss.get_firmware_version.side_effect = None
    mock_pitboss.get_firmware_version.return_value = {"firmwareVersion": "0.5.7"}
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator._firmware_attempted_at is not None
    coordinator._firmware_attempted_at -= SYS_INFO_INTERVAL + 1
    async_fire_time_changed(
        hass, dt_util.utcnow() + STANDBY_SCAN_INTERVAL + timedelta(seconds=1)
    )
    await hass.async_block_till_done()

    device = registry.async_get_device(identifiers={(DOMAIN, "mygrill")})
    assert device is not None
    assert device.sw_version == "0.5.7"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_chamber_temperature_ships_disabled(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """It duplicates a reading the climate entity already publishes.

    Only worth having for the unit override it accepts and the climate
    entity does not, so it stays out of the way until someone asks for it.
    """
    await mock_add_config_entry()
    assert hass.states.get("sensor.mygrill_chamber_temperature") is None
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, "chamber_temp_mygrillid")
    assert entity_id is not None
    entry = registry.async_get(entity_id)
    assert entry is not None
    assert entry.disabled_by is not None


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_chamber_temperature_mirrors_the_climate_reading(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    entry = await mock_add_config_entry()
    entity_id = await enable_entity(hass, entry, "sensor", "chamber_temp_mygrillid")
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"isFahrenheit": True, "grillTemp": 275})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == 275.0
    assert state.attributes["unit_of_measurement"] == UnitOfTemperature.FAHRENHEIT
    climate = hass.states.get("climate.mygrill_grill_temperature")
    assert climate is not None
    assert climate.attributes["current_temperature"] == 275.0


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_chamber_temperature_null_reading_is_unknown(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """The boards put null on the wire for the no-reading sentinel."""
    entry = await mock_add_config_entry()
    entity_id = await enable_entity(hass, entry, "sensor", "chamber_temp_mygrillid")
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data(
        cast(StateDict, {"isFahrenheit": True, "grillTemp": None})
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_UNKNOWN


@pytest.mark.parametrize("model", ["PBV4PS2"])
@pytest.mark.parametrize("units", [METRIC_SYSTEM])
async def test_chamber_temperature_takes_a_unit_override(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """The entire reason this entity exists.

    A Celsius grill on a metric Home Assistant, shown in Fahrenheit. The
    climate entity is fed the same registry option and ignores it -- there is
    no lookup for it in `climate/__init__.py` -- which is what this asserts by
    reading both at once.
    """
    entry = await mock_add_config_entry()
    entity_id = await enable_entity(hass, entry, "sensor", "chamber_temp_mygrillid")
    registry = er.async_get(hass)
    registry.async_update_entity_options(
        entity_id,
        "sensor",
        {"unit_of_measurement": UnitOfTemperature.FAHRENHEIT},
    )
    await hass.async_block_till_done()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"isFahrenheit": False, "grillTemp": 121})
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["unit_of_measurement"] == UnitOfTemperature.FAHRENHEIT
    assert float(state.state) == pytest.approx(249.8)

    climate = hass.states.get("climate.mygrill_grill_temperature")
    assert climate is not None
    assert climate.attributes["current_temperature"] == 121.0


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_smoker_temperature_ships_disabled(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """The frame carries it; what it reads on a given grill is unverified."""
    await mock_add_config_entry()
    assert hass.states.get("sensor.mygrill_smoker_temperature") is None
    # Anchored: a sensor this model does have, so the absence above means
    # disabled rather than a platform that never set up.
    assert hass.states.get("sensor.mygrill_mpc") is not None
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, "smoker_temp_mygrillid")
    assert entity_id is not None
    entry = registry.async_get(entity_id)
    assert entry is not None
    assert entry.disabled_by is not None


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_smoker_temperature_reads_its_own_field(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """Not a second name for the chamber: distinct bytes, distinct value."""
    entry = await mock_add_config_entry()
    entity_id = await enable_entity(hass, entry, "sensor", "smoker_temp_mygrillid")
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data(
        {"isFahrenheit": True, "grillTemp": 275, "smokerActTemp": 180}
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == 180.0
    assert state.attributes["unit_of_measurement"] == UnitOfTemperature.FAHRENHEIT
    # The chamber is reading something else at the same moment.
    climate = hass.states.get("climate.mygrill_grill_temperature")
    assert climate is not None
    assert climate.attributes["current_temperature"] == 275.0


@pytest.mark.parametrize("model", ["PB850M"])
async def test_no_smoker_sensor_on_a_board_that_never_reports_one(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """26 of the 137 models decode no smoker field at all.

    Creating the entity anyway would leave it unknown for the life of the
    entry -- the same shape as the startup-error sensor on these boards.
    """
    await mock_add_config_entry()
    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "smoker_temp_mygrillid") is None
    )
    # Anchored, so this cannot pass by the platform not setting up.
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "probe1_mygrillid") is not None
    )
