from typing import Awaitable, Callable

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.parametrize("model,want", [("PBV4PS2", 130), ("PB2180LK", 180)])
async def test_min_temp(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    want: int | float,
) -> None:
    await mock_add_config_entry()
    temps = hass.states.get("climate.mygrill_grill_temperature")
    assert temps is not None
    assert temps.attributes["min_temp"] == want


@pytest.mark.parametrize("model,want", [("PBV4PS2", 420), ("PB2180LK", 500)])
async def test_max_temp(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    want: int | float,
) -> None:
    await mock_add_config_entry()
    temps = hass.states.get("climate.mygrill_grill_temperature")
    assert temps is not None
    assert temps.attributes["max_temp"] == want
