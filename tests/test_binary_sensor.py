from collections.abc import Awaitable, Callable
from dataclasses import replace
from unittest.mock import Mock

import pytest
from conftest import get_entity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.binary_sensor import (
    ENTITY_DESCRIPTIONS,
    PROBE_ERROR_KEYS,
    BinarySensor,
)
from custom_components.pitboss.const import DOMAIN
from custom_components.pitboss.coordinator import PitBossDataUpdateCoordinator


def _entity_id(name: str) -> str:
    return f"binary_sensor.mygrill_{name.lower().replace(' ', '_')}"


# Spelled out rather than computed with `probe_label`, so that a wrong label
# is a test failure instead of a quietly updated expectation.
PROBE_ERROR_NAMES = {"err1": "MPC error", "err2": "P2 error", "err3": "P3 error"}


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_creates_all_entities(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    for description in ENTITY_DESCRIPTIONS:
        # The probe error sensors carry no description name: the entity sets
        # `_attr_name` from the port label, which takes precedence anyway.
        if description.key in PROBE_ERROR_KEYS:
            name = PROBE_ERROR_NAMES[description.key]
        else:
            assert isinstance(description.name, str)
            name = description.name
        entity_id = _entity_id(name)
        assert hass.states.get(entity_id) is not None, entity_id


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_is_on_no_data(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    state = hass.states.get(_entity_id("MPC error"))
    assert state is not None
    assert state.state == "unavailable"

    entity = get_entity(hass, "binary_sensor", _entity_id("MPC error"), BinarySensor)
    assert entity.is_on is None


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_is_on_with_data(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"err1": True, "motorState": False})
    await hass.async_block_till_done()
    probe_1_error = hass.states.get(_entity_id("MPC error"))
    auger = hass.states.get(_entity_id("Auger"))
    assert probe_1_error is not None
    assert auger is not None
    assert probe_1_error.state == "on"
    assert auger.state == "off"


@pytest.mark.parametrize("model", ["PBV4PS2"])
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


@pytest.mark.parametrize("model", ["PBV4PS2"])
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


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_connectivity_follows_the_grill_not_just_the_socket(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """A connected transport whose grill stops answering is not reachable.

    On the cloud protocol `is_connected()` reflects the socket to the
    vendor's relay, which stays open whether or not the grill is behind
    it -- a powered-off grill read as "connected" until this check also
    asked whether polls succeed.
    """
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    mock_pitboss.is_connected.return_value = True
    coordinator.async_set_updated_data({})
    await hass.async_block_till_done()
    state = hass.states.get(_entity_id("Connectivity"))
    assert state is not None
    assert state.state == "on"

    coordinator.async_set_update_error(TimeoutError("grill gone"))
    await hass.async_block_till_done()
    state = hass.states.get(_entity_id("Connectivity"))
    assert state is not None
    assert state.state == "off"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_a_target_reached_sensor_per_probe(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """PBV4PS2 has two probes, so there is no third or fourth."""
    await mock_add_config_entry()
    assert hass.states.get(_entity_id("MPC target reached")) is not None
    assert hass.states.get(_entity_id("P2 target reached")) is not None
    assert hass.states.get(_entity_id("P3 target reached")) is None


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_target_reached_follows_the_probe(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    coordinator.async_set_updated_data({"p1Temp": 70, "p1Target": 165})
    await hass.async_block_till_done()
    state = hass.states.get(_entity_id("MPC target reached"))
    assert state is not None
    assert state.state == "off"

    coordinator.async_set_updated_data({"p1Temp": 165, "p1Target": 165})
    await hass.async_block_till_done()
    state = hass.states.get(_entity_id("MPC target reached"))
    assert state is not None
    assert state.state == "on"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_target_reached_is_off_rather_than_unknown(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """An automation on off-to-on cannot trigger out of `unknown`.

    So an unplugged probe, or one with no target, reads `off` rather than
    reporting that it does not know.
    """
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Probe plugged in, no target anywhere.
    coordinator.async_set_updated_data({"p2Temp": 70})
    await hass.async_block_till_done()
    state = hass.states.get(_entity_id("P2 target reached"))
    assert state is not None
    assert state.state == "off"

    # Target set, no probe in the port.
    coordinator.restored_targets[2] = 165
    coordinator.async_set_updated_data({"p2Temp": None})
    await hass.async_block_till_done()
    state = hass.states.get(_entity_id("P2 target reached"))
    assert state is not None
    assert state.state == "off"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_target_reached_uses_a_target_the_grill_does_not_report(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """The point of the sensor: probes the grill raises nothing for."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.restored_targets[2] = 165

    coordinator.async_set_updated_data({"p2Temp": 164})
    await hass.async_block_till_done()
    state = hass.states.get(_entity_id("P2 target reached"))
    assert state is not None
    assert state.state == "off"

    coordinator.async_set_updated_data({"p2Temp": 166})
    await hass.async_block_till_done()
    state = hass.states.get(_entity_id("P2 target reached"))
    assert state is not None
    assert state.state == "on"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_meat_probe_control_sensor(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """PBV4PS2 has a control port, so it reads `on`."""
    await mock_add_config_entry()
    state = hass.states.get(_entity_id("Meat probe control"))
    assert state is not None
    assert state.state == "on"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_meat_probe_control_sensor_without_a_control_port(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """The module parametrizes `model`, so the spec is swapped instead."""
    mock_pitboss.spec = replace(mock_pitboss.spec, has_mpc=False)

    await mock_add_config_entry()

    state = hass.states.get(_entity_id("Meat probe control"))
    assert state is not None
    assert state.state == "off"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_meat_probe_control_stays_available_while_disconnected(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """It answers a question about the model, not about the connection."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    mock_pitboss.is_connected.return_value = False
    coordinator.async_set_updated_data({})
    await hass.async_block_till_done()

    state = hass.states.get(_entity_id("Meat probe control"))
    assert state is not None
    assert state.state == "on"


@pytest.mark.parametrize("model", ["PB850CS2"])
async def test_a_flag_the_board_never_reports_gets_no_entity(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """PBM2 has no `erL` in either parsing routine.

    The sensor was created anyway and sat unknown for the life of the entry,
    since the merged state never carries the key. `erL` is the only one of
    these flags that is not universal today; the gate is written against
    what the board reports rather than against that fact, so a definitions
    refresh is followed without a change here.
    """
    await mock_add_config_entry()
    assert hass.states.get(_entity_id("Startup error")) is None
    # The rest still arrive: this must not thin out the platform.
    assert hass.states.get(_entity_id("Fan error")) is not None
    assert hass.states.get(_entity_id("Igniter error")) is not None


@pytest.mark.parametrize("model", ["PB850CS2"])
async def test_the_stale_row_from_an_earlier_release_is_removed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """The boards this affects are the ones already running.

    Their `startup_error` row is already in the registry, and Home Assistant
    keeps a row whose entity stops being created -- rendering it as
    unavailable rather than dropping it, with manual deletion the only way
    out. Not creating the entity alone would turn "permanently unknown" into
    "permanently unavailable" for exactly the installs this is meant to fix,
    so the row is removed too. Seeding it is the only way this path runs.
    """
    registry = er.async_get(hass)
    mock_config_entry.add_to_hass(hass)
    stale = registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"erL_{mock_config_entry.unique_id}",
        suggested_object_id="mygrill_startup_error",
        config_entry=mock_config_entry,
    )
    assert registry.async_get(stale.entity_id) is not None

    await mock_add_config_entry()

    assert registry.async_get(stale.entity_id) is None
    # A flag the board does report keeps its row.
    assert (
        registry.async_get_entity_id(
            "binary_sensor", DOMAIN, f"fanErr_{mock_config_entry.unique_id}"
        )
        is not None
    )


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_target_reached_ignores_a_target_at_the_minimum(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """Plugging a probe into a cold grill used to light this sensor.

    The board reports 50 F for a probe it is not working to, and a probe
    sitting in a room is warmer than that, so the sensor came on the moment
    one was plugged in -- reporting the probe's presence rather than the
    meat's temperature.
    """
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    mock_pitboss.is_connected.return_value = True

    coordinator.async_set_updated_data(
        {"isFahrenheit": True, "p1Target": 50, "p1Temp": 77}
    )
    await hass.async_block_till_done()
    assert hass.states.get(_entity_id("MPC target reached")).state == "off"

    coordinator.async_set_updated_data(
        {"isFahrenheit": True, "p1Target": 145, "p1Temp": 150}
    )
    await hass.async_block_till_done()
    assert hass.states.get(_entity_id("MPC target reached")).state == "on"
