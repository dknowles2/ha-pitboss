from typing import Awaitable, Callable

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.parametrize("model,has_light", [("PBV4PS2", False), ("PB2180LK", True)])
async def test_creates_entity(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    has_light: bool,
) -> None:
    await mock_add_config_entry()
    light = hass.states.get("light.mygrill_light")
    if has_light:
        assert light is not None
    else:
        assert light is None
