from collections.abc import Awaitable, Callable
from unittest.mock import Mock

import pytest
from conftest import get_entity
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.const import DOMAIN
from custom_components.pitboss.coordinator import PitBossDataUpdateCoordinator
from custom_components.pitboss.light import GrillLight

ENTITY_ID = "light.mygrill_light"


@pytest.mark.parametrize("model,has_light", [("PBV4PS2", False), ("PB2180LK", True)])
async def test_creates_entity(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    has_light: bool,
) -> None:
    await mock_add_config_entry()
    light = hass.states.get(ENTITY_ID)
    if has_light:
        assert light is not None
    else:
        assert light is None


@pytest.mark.parametrize("model", ["PB2180LK"])
async def test_availability_and_is_on(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # No data: unavailable.
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "unavailable"

    coordinator.async_set_updated_data({"lightState": True})
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "on"

    coordinator.async_set_updated_data({"lightState": False})
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "off"


@pytest.mark.parametrize("model", ["PB2180LK"])
async def test_turn_on_and_off(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"lightState": False})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": ENTITY_ID}, blocking=True
    )
    mock_pitboss.turn_light_on.assert_awaited_once()

    await hass.services.async_call(
        "light", "turn_off", {"entity_id": ENTITY_ID}, blocking=True
    )
    mock_pitboss.turn_light_off.assert_awaited_once()


@pytest.mark.parametrize("model", ["PB2180LK"])
async def test_is_on_none_without_data(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    entity = get_entity(hass, "light", ENTITY_ID, GrillLight)
    assert entity.is_on is None


@pytest.mark.parametrize("model", ["PB2180LK"])
async def test_unavailable_when_disconnected(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """State is not reported once the grill is gone, even if data was cached."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"lightState": True})
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "on"

    mock_pitboss.is_connected.return_value = False
    coordinator.async_set_updated_data({"lightState": True})
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "unavailable"
