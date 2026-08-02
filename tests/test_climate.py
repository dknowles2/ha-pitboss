from collections.abc import Awaitable, Callable
from unittest.mock import Mock

import pytest
from conftest import get_entity
from homeassistant.components.climate.const import HVACAction, HVACMode
from homeassistant.core import HomeAssistant
from pytboss.grills import StateDict
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.climate import GrillClimate
from custom_components.pitboss.const import DOMAIN
from custom_components.pitboss.coordinator import PitBossDataUpdateCoordinator

ENTITY_ID = "climate.mygrill_grill_temperature"


@pytest.mark.parametrize("model,want", [("PBV4PS2", 130), ("PB2180LK", 180)])
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
    mock_pitboss.set_grill_temperature.assert_awaited_once_with(275)


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
