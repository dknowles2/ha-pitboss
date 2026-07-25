from collections.abc import Awaitable, Callable
from unittest.mock import Mock

import pytest
from conftest import get_entity
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.const import DOMAIN
from custom_components.pitboss.coordinator import PitBossDataUpdateCoordinator
from custom_components.pitboss.number import TargetProbeTemperature


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_only_probe_1_entity_created(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    assert hass.states.get("number.mygrill_probe_1_target") is not None
    assert hass.states.get("number.mygrill_probe_2_target") is None


@pytest.mark.parametrize("model", ["PB1150PS3"])
async def test_both_probe_entities_created(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    assert hass.states.get("number.mygrill_probe_1_target") is not None
    assert hass.states.get("number.mygrill_probe_2_target") is not None


@pytest.mark.parametrize("model", ["PB2180LK"])
async def test_no_probe_entities_created(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    assert hass.states.get("number.mygrill_probe_1_target") is None
    assert hass.states.get("number.mygrill_probe_2_target") is None


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_native_value_and_availability(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # No matching probe temperature reported: entity unavailable.
    coordinator.async_set_updated_data({"p1Target": 165, "isFahrenheit": True})
    await hass.async_block_till_done()
    state = hass.states.get("number.mygrill_probe_1_target")
    assert state is not None
    assert state.state == "unavailable"

    coordinator.async_set_updated_data(
        {"p1Target": 165, "p1Temp": 70, "isFahrenheit": True}
    )
    await hass.async_block_till_done()
    state = hass.states.get("number.mygrill_probe_1_target")
    assert state is not None
    assert state.state == "165"
    assert state.attributes["unit_of_measurement"] == "°F"
    assert state.attributes["step"] == 1
    assert state.attributes["min"] == 50
    assert state.attributes["max"] == 250


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_set_native_value(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data(
        {"p1Target": 165, "p1Temp": 70, "isFahrenheit": True}
    )
    await hass.async_block_till_done()

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.mygrill_probe_1_target", "value": 180},
        blocking=True,
    )
    mock_pitboss.set_probe_temperature.assert_awaited_once_with(180)


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_native_value_none_without_data(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    entity = get_entity(
        hass, "number", "number.mygrill_probe_1_target", TargetProbeTemperature
    )
    assert entity.native_value is None
