from collections.abc import Awaitable, Callable
from datetime import timedelta
from math import floor
from typing import cast
from unittest.mock import Mock

import pytest
from conftest import get_entity
from homeassistant.components.climate.const import HVACAction, HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytboss.grills import StateDict
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.pitboss.climate import GrillClimate
from custom_components.pitboss.const import DOMAIN, MCU_SETTLE_SECONDS
from custom_components.pitboss.coordinator import PitBossDataUpdateCoordinator

ENTITY_ID = "climate.mygrill_grill_temperature"


# PB2180LK publishes no min_temp, so this used to fall back to the
# DEFAULT_MIN_TEMP constant. Its setpoint list starts at 160, which is the
# board's real floor, so that is what the entity reports now.
@pytest.mark.parametrize("model,want", [("PBV4PS2", 130), ("PB2180LK", 160)])
async def test_min_temp(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    want: float,
) -> None:
    await mock_add_config_entry()
    temps = hass.states.get(ENTITY_ID)
    assert temps is not None
    assert temps.attributes["min_temp"] == want


@pytest.mark.parametrize("model,want", [("PBV4PS2", 420), ("PB2180LK", 500)])
async def test_max_temp(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    want: float,
) -> None:
    await mock_add_config_entry()
    temps = hass.states.get(ENTITY_ID)
    assert temps is not None
    assert temps.attributes["max_temp"] == want


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_target_temperature_step(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    coordinator.async_set_updated_data({"isFahrenheit": True})
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["target_temp_step"] == 5.0

    coordinator.async_set_updated_data({"isFahrenheit": False})
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["target_temp_step"] == 1.0


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_current_and_target_temperature(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # No data yet: entity is unavailable, so these attributes are absent.
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes.get("current_temperature") is None
    assert state.attributes.get("temperature") is None

    coordinator.async_set_updated_data(
        {"grillTemp": 225, "grillSetTemp": 250, "isFahrenheit": True}
    )
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["current_temperature"] == 225.0
    assert state.attributes["temperature"] == 250.0


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_a_null_reading_is_unknown_not_a_crash(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """The boards put null on the wire for the no-reading sentinel (960).

    The same convertTemperature routine that gives an unplugged probe its
    None gives the chamber sensor one too. Coercing that with float() raised
    on every state write for as long as the sensor was out.
    """
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    coordinator.async_set_updated_data(
        cast(StateDict, {"grillTemp": None, "grillSetTemp": None, "isFahrenheit": True})
    )
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes.get("current_temperature") is None
    assert state.attributes.get("temperature") is None


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_absent_unit_flag_reads_as_fahrenheit(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """A state built from a status frame alone carries no isFahrenheit.

    Most boards emit the flag only in the temperatures frame. The entity
    must default to the unit pytboss snaps commands with -- Fahrenheit --
    or the unit shown and the unit commanded disagree for the window.
    """
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"moduleIsOn": True, "grillSetTemp": 250})
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    # The Fahrenheit step; the Celsius default read this as 1.0.
    assert state.attributes["target_temp_step"] == 5.0


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_set_temperature_noop_without_temperature_kwarg(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    await mock_add_config_entry()
    entity = get_entity(hass, "climate", ENTITY_ID, GrillClimate)
    await entity.async_set_temperature()
    mock_pitboss.set_grill_temperature.assert_not_awaited()


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_set_hvac_mode_heat_is_a_safety_noop(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"moduleIsOn": False})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": ENTITY_ID, "hvac_mode": "heat"},
        blocking=True,
    )
    mock_pitboss.turn_grill_off.assert_not_awaited()


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_set_temperature(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"moduleIsOn": True, "isFahrenheit": True})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": ENTITY_ID, "temperature": 275},
        blocking=True,
    )
    # PBV4PS2's board takes setpoints in tens; 275 is not on its list. The
    # entity snaps with the same arithmetic pytboss does, so what is sent --
    # and shown -- is the value the board will actually report.
    mock_pitboss.set_grill_temperature.assert_awaited_once_with(270)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["temperature"] == 270.0


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_the_setpoint_holds_until_the_grill_confirms_it(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """The board wipes its status when it forwards a command to the MCU.

    So the poll right after a set still carries the old setpoint, and the
    slider snapped back to it. The asked-for value holds until the grill
    reports it -- or until the settle window ends, after which the grill's
    own answer wins, whatever it is.
    """
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data(
        {"moduleIsOn": True, "isFahrenheit": True, "grillSetTemp": 250}
    )
    await hass.async_block_till_done()

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": ENTITY_ID, "temperature": 300},
        blocking=True,
    )

    # A poll lands still carrying the old setpoint; the asked-for one holds.
    coordinator.async_set_updated_data(
        {"moduleIsOn": True, "isFahrenheit": True, "grillSetTemp": 250}
    )
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["temperature"] == 300.0

    # The grill reports the new setpoint; from here it is the source again.
    coordinator.async_set_updated_data(
        {"moduleIsOn": True, "isFahrenheit": True, "grillSetTemp": 300}
    )
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["temperature"] == 300.0

    coordinator.async_set_updated_data(
        {"moduleIsOn": True, "isFahrenheit": True, "grillSetTemp": 250}
    )
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["temperature"] == 250.0


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_an_unconfirmed_setpoint_expires_with_the_settle_window(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """If the grill never takes the value, the entity stops asserting it."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data(
        {"moduleIsOn": True, "isFahrenheit": True, "grillSetTemp": 250}
    )
    await hass.async_block_till_done()
    mock_pitboss.get_state.reset_mock()

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": ENTITY_ID, "temperature": 300},
        blocking=True,
    )
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["temperature"] == 300.0

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=MCU_SETTLE_SECONDS + 1)
    )
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["temperature"] == 250.0
    # The window also asks the grill again rather than waiting out the poll.
    assert mock_pitboss.get_state.await_count >= 1


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_turn_off(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"moduleIsOn": True})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": ENTITY_ID, "hvac_mode": "off"},
        blocking=True,
    )
    mock_pitboss.turn_grill_off.assert_awaited_once()
    # The setpoint belongs to the user; turning off must not rewrite it.
    mock_pitboss.set_grill_temperature.assert_not_awaited()


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_hvac_mode(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # No data yet: entity is unavailable.
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "unavailable"

    coordinator.async_set_updated_data({"moduleIsOn": True})
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == HVACMode.HEAT.value

    coordinator.async_set_updated_data({"moduleIsOn": False})
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == HVACMode.OFF.value


@pytest.mark.parametrize(
    "data,want",
    [
        ({"hotState": True, "moduleIsOn": True}, HVACAction.HEATING),
        (
            {"hotState": False, "moduleIsOn": False, "fanState": True},
            HVACAction.COOLING,
        ),
        ({"hotState": False, "moduleIsOn": True, "fanState": True}, HVACAction.FAN),
        ({"hotState": False, "moduleIsOn": False, "fanState": False}, HVACAction.OFF),
        ({"hotState": False, "moduleIsOn": True, "fanState": False}, HVACAction.IDLE),
    ],
)
@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_hvac_action(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    data: StateDict,
    want: HVACAction,
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data(data)
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["hvac_action"] == want.value


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_hvac_mode_and_action_none_without_data(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    entity = get_entity(hass, "climate", ENTITY_ID, GrillClimate)
    assert entity.hvac_mode is None
    assert entity.hvac_action is None


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_bounds_come_from_the_boards_setpoints(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """Fahrenheit bounds are the first and last accepted setpoints."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"isFahrenheit": True})
    await hass.async_block_till_done()

    increments = coordinator.api.spec.temp_increments
    assert increments
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["min_temp"] == min(increments)
    assert state.attributes["max_temp"] == max(increments)
    assert state.attributes["allowed_setpoints"] == [float(v) for v in increments]


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_celsius_setpoints_use_the_boards_own_conversion(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """floor((F - 32) / 1.8), matching the boards that convert in their JS."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"isFahrenheit": False})
    await hass.async_block_till_done()

    increments = coordinator.api.spec.temp_increments
    assert increments
    expected = [float(floor((v - 32) / 1.8)) for v in increments]
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["allowed_setpoints"] == expected
