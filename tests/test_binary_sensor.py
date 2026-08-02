from collections.abc import Awaitable, Callable
from unittest.mock import Mock

import pytest
from conftest import get_entity
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.binary_sensor import ENTITY_DESCRIPTIONS, BinarySensor
from custom_components.pitboss.const import DOMAIN
from custom_components.pitboss.coordinator import PitBossDataUpdateCoordinator

pytestmark = pytest.mark.parametrize("model", ["PBV4PS2"])


def _entity_id(name: str) -> str:
    return f"binary_sensor.mygrill_{name.lower().replace(' ', '_')}"


async def test_creates_all_entities(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    for description in ENTITY_DESCRIPTIONS:
        assert isinstance(description.name, str)
        entity_id = _entity_id(description.name)
        assert hass.states.get(entity_id) is not None, entity_id


async def test_is_on_no_data(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    state = hass.states.get(_entity_id("Probe 1 error"))
    assert state is not None
    assert state.state == "unavailable"

    entity = get_entity(
        hass, "binary_sensor", _entity_id("Probe 1 error"), BinarySensor
    )
    assert entity.is_on is None


async def test_is_on_with_data(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"err1": True, "motorState": False})
    await hass.async_block_till_done()
    probe_1_error = hass.states.get(_entity_id("Probe 1 error"))
    auger = hass.states.get(_entity_id("Auger"))
    assert probe_1_error is not None
    assert auger is not None
    assert probe_1_error.state == "on"
    assert auger.state == "off"


async def test_fan_and_igniter_report_their_state(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """Both are already decoded by pytboss; they just were not exposed."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"fanState": True, "hotState": False})
    await hass.async_block_till_done()

    fan = hass.states.get(_entity_id("Fan"))
    igniter = hass.states.get(_entity_id("Igniter"))
    assert fan is not None
    assert igniter is not None
    assert fan.state == "on"
    assert igniter.state == "off"


async def test_connectivity_reports_offline_instead_of_vanishing(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """It must stay available while disconnected, or it can't say so."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    mock_pitboss.is_connected.return_value = True
    coordinator.async_set_updated_data({})
    await hass.async_block_till_done()
    state = hass.states.get(_entity_id("Connectivity"))
    assert state is not None
    assert state.state == "on"

    mock_pitboss.is_connected.return_value = False
    coordinator.async_set_updated_data({})
    await hass.async_block_till_done()
    state = hass.states.get(_entity_id("Connectivity"))
    assert state is not None
    assert state.state == "off"
