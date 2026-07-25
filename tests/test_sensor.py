from collections.abc import Awaitable, Callable
from typing import cast

import pytest
from conftest import get_entity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytboss.grills import StateDict
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.const import DOMAIN
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
    assert hass.states.get("sensor.mygrill_probe_1") is not None
    assert hass.states.get("sensor.mygrill_probe_2") is not None
    assert hass.states.get("sensor.mygrill_probe_3") is None
    assert hass.states.get("sensor.mygrill_probe_4") is None
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


@pytest.mark.parametrize("model", ["PB2180LK"])
async def test_recipe_sensors_absent_when_unsupported(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
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
    state = hass.states.get("sensor.mygrill_probe_1")
    assert state is not None
    assert state.state == "165"
    assert state.attributes["unit_of_measurement"] == "°F"

    coordinator.async_set_updated_data({"p1Temp": 74, "isFahrenheit": False})
    await hass.async_block_till_done()
    state = hass.states.get("sensor.mygrill_probe_1")
    assert state is not None
    assert state.state == "165.2"
    assert state.attributes["unit_of_measurement"] == "°F"


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


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_native_value_none_without_data(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    entity = get_entity(hass, "sensor", "sensor.mygrill_probe_1", ProbeSensor)
    assert entity.native_value is None
