from collections.abc import Awaitable, Callable
from datetime import timedelta
from unittest.mock import Mock

import pytest
from conftest import get_entity
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.pitboss.const import DOMAIN
from custom_components.pitboss.select import (
    MCU_SETTLE_SECONDS,
    GrillTemperatureUnitSelect,
)

pytestmark = pytest.mark.parametrize("model", ["PBV4PS2"])


async def test_reports_the_unit_the_grill_is_in(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    entry = await mock_add_config_entry()
    coordinator = hass.data[DOMAIN][entry.entry_id]

    coordinator.async_set_updated_data({"isFahrenheit": True})
    await hass.async_block_till_done()
    state = hass.states.get("select.mygrill_grill_temperature_unit")
    assert state is not None
    assert state.state == "°F"

    coordinator.async_set_updated_data({"isFahrenheit": False})
    await hass.async_block_till_done()
    state = hass.states.get("select.mygrill_grill_temperature_unit")
    assert state is not None
    assert state.state == "°C"


async def test_selecting_switches_the_grill(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    entry = await mock_add_config_entry()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"isFahrenheit": True})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.mygrill_grill_temperature_unit", "option": "°C"},
        blocking=True,
    )

    mock_pitboss.set_temperature_unit.assert_awaited_once_with(fahrenheit=False)


async def test_the_choice_holds_until_the_grill_confirms(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """The board clears its cached status when it forwards a command.

    So the next poll still carries the old unit, and without holding the
    pending choice the UI would appear to snap back.
    """
    entry = await mock_add_config_entry()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"isFahrenheit": True})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.mygrill_grill_temperature_unit", "option": "°C"},
        blocking=True,
    )
    state = hass.states.get("select.mygrill_grill_temperature_unit")
    assert state is not None
    assert state.state == "°C"

    # A poll still reporting the old unit must not undo the choice.
    coordinator.async_set_updated_data({"isFahrenheit": True})
    await hass.async_block_till_done()
    state = hass.states.get("select.mygrill_grill_temperature_unit")
    assert state is not None
    assert state.state == "°C"

    # Once the grill agrees, the pending value is dropped and it follows again.
    coordinator.async_set_updated_data({"isFahrenheit": False})
    await hass.async_block_till_done()
    coordinator.async_set_updated_data({"isFahrenheit": True})
    await hass.async_block_till_done()
    state = hass.states.get("select.mygrill_grill_temperature_unit")
    assert state is not None
    assert state.state == "°F"


async def test_a_refresh_is_requested_after_the_mcu_settles(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    entry = await mock_add_config_entry()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"isFahrenheit": True})
    await hass.async_block_till_done()
    mock_pitboss.get_state.reset_mock()

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.mygrill_grill_temperature_unit", "option": "°C"},
        blocking=True,
    )
    assert mock_pitboss.get_state.await_count == 0

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=MCU_SETTLE_SECONDS + 1)
    )
    await hass.async_block_till_done()
    assert mock_pitboss.get_state.await_count >= 1


async def test_the_choice_is_dropped_if_the_grill_never_takes_it(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """One settle window is all the pending value is for.

    A command the grill accepts but does not apply would otherwise leave the
    entity asserting a unit the grill will never report, for its whole life.
    """
    entry = await mock_add_config_entry()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"isFahrenheit": True})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.mygrill_grill_temperature_unit", "option": "°C"},
        blocking=True,
    )
    state = hass.states.get("select.mygrill_grill_temperature_unit")
    assert state is not None
    assert state.state == "°C"

    # The grill keeps reporting the old unit past the settle window.
    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=MCU_SETTLE_SECONDS + 1)
    )
    await hass.async_block_till_done()
    coordinator.async_set_updated_data({"isFahrenheit": True})
    await hass.async_block_till_done()

    state = hass.states.get("select.mygrill_grill_temperature_unit")
    assert state is not None
    assert state.state == "°F"


async def test_selections_do_not_pile_up_timers(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """Each selection replaces the settle timer rather than adding one.

    `async_on_remove` only appends, so registering per selection would grow
    the entity's removal list for its lifetime, and every window would fire
    once per selection made inside it.
    """
    entry = await mock_add_config_entry()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"isFahrenheit": True})
    await hass.async_block_till_done()
    entity = get_entity(
        hass,
        "select",
        "select.mygrill_grill_temperature_unit",
        GrillTemperatureUnitSelect,
    )
    removals = len(entity._on_remove or ())
    confirms = []
    original = entity._async_confirm

    async def counting_confirm(now):
        confirms.append(now)
        await original(now)

    entity._async_confirm = counting_confirm  # type: ignore[method-assign]

    for option in ("°C", "°F", "°C"):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": "select.mygrill_grill_temperature_unit", "option": option},
            blocking=True,
        )

    assert len(entity._on_remove or ()) == removals

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=MCU_SETTLE_SECONDS + 1)
    )
    await hass.async_block_till_done()

    assert len(confirms) == 1
