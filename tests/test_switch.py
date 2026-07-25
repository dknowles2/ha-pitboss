from collections.abc import Awaitable, Callable
from unittest.mock import Mock

import pytest
from conftest import get_entity
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.const import DOMAIN
from custom_components.pitboss.coordinator import PitBossDataUpdateCoordinator
from custom_components.pitboss.switch import PowerSwitch


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_both_switches_created(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    assert hass.states.get("switch.mygrill_module_power") is not None
    assert hass.states.get("switch.mygrill_prime") is not None


@pytest.mark.parametrize("model", ["PB1020CS2"])
async def test_primer_switch_absent_when_unsupported(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    assert hass.states.get("switch.mygrill_module_power") is not None
    assert hass.states.get("switch.mygrill_prime") is None


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_is_on_and_availability(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    coordinator.async_set_updated_data({"moduleIsOn": True, "primeState": False})
    await hass.async_block_till_done()
    power_state = hass.states.get("switch.mygrill_module_power")
    prime_state = hass.states.get("switch.mygrill_prime")
    assert power_state is not None
    assert prime_state is not None
    assert power_state.state == "on"
    assert prime_state.state == "off"

    coordinator.async_set_updated_data({"moduleIsOn": False, "primeState": False})
    await hass.async_block_till_done()
    # All switches are unavailable when the module (grill) is off, since
    # availability is gated on the shared "moduleIsOn" key.
    power_state = hass.states.get("switch.mygrill_module_power")
    prime_state = hass.states.get("switch.mygrill_prime")
    assert power_state is not None
    assert prime_state is not None
    assert prime_state.state == "unavailable"
    assert power_state.state == "unavailable"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_power_switch_turn_on_is_a_noop(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"moduleIsOn": False})
    await hass.async_block_till_done()

    entity = get_entity(hass, "switch", "switch.mygrill_module_power", PowerSwitch)
    await entity.async_turn_on()
    mock_pitboss.turn_grill_off.assert_not_awaited()


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_power_switch_turn_off(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"moduleIsOn": True})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.mygrill_module_power"},
        blocking=True,
    )
    mock_pitboss.turn_grill_off.assert_awaited_once()
    mock_pitboss.set_grill_temperature.assert_awaited_once_with(temp=130)


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_primer_switch_turn_on_off(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"moduleIsOn": True, "primeState": False})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.mygrill_prime"},
        blocking=True,
    )
    mock_pitboss.turn_primer_motor_on.assert_awaited_once()

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.mygrill_prime"},
        blocking=True,
    )
    mock_pitboss.turn_primer_motor_off.assert_awaited_once()


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_is_on_none_without_data(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    entity = get_entity(hass, "switch", "switch.mygrill_module_power", PowerSwitch)
    assert entity.is_on is None
