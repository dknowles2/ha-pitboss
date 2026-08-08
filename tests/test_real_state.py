"""Entities driven from state pytboss actually produced.

Every other test in this suite hands the coordinator a dictionary written
by hand -- `{"isFahrenheit": True, "grillTemp": 275}` and its siblings.
Those are precise about partial and malformed frames, which is what they
are for, and they are also a shape no grill has ever sent.

`pytboss.testing.build_state` synthesizes both wire frames for a specific
grill and runs them through that board's own parsing routine, so what
arrives here is the real thing: the real field set, the real types, the
real per-board differences, and the fields nobody thought to write down.

One model per board family, weighted towards the awkward ones -- the board
with no `erL`, the two whose vendor routines read a field from bytes that
do not hold it, the ones that convert to Celsius themselves.
"""

from collections.abc import Awaitable, Callable

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from pytboss import testing
from pytboss.grills import Grill
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.const import DOMAIN
from custom_components.pitboss.coordinator import PitBossDataUpdateCoordinator

# One model per control board, chosen for the differences between them:
# PBM2 reports no `erL` and no smoker field, LBL's routines read a grill
# temperature from bytes that do not hold it, PBA and PBE forget to convert
# two fields, PBV2 carries three probes rather than two.
MODELS = [
    "PB1100PSC2",  # PBL
    "PB1500NXW",  # PBM2
    "PB1600 PSE",  # PBD
    "PB1150PS3",  # PBA
    "PB1100HTC",  # PBE
    "LG0800BL",  # LBL
    "PB1020DX",  # PBL3
    "PBV3 M",  # PBV2
    "PB1100SPW2",  # PBC2
]

pytestmark = pytest.mark.parametrize("model", MODELS)


async def test_the_grill_reads_back_what_the_board_reported(
    hass: HomeAssistant,
    spec: Grill,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """A lit grill, from a real parse, on every board family.

    The chamber temperature is the load-bearing one: LBL and LFS drop it
    from the status reply because the vendor's routine reads bytes that do
    not hold it, so it has to come from the temperatures reply instead.
    That is invisible to a hand-written dictionary, which simply contains
    whatever the author typed.
    """
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data(
        testing.build_state(
            spec,
            moduleIsOn=True,
            isFahrenheit=True,
            grillTemp=275,
            grillSetTemp=250,
        )
    )
    await hass.async_block_till_done()

    climate = hass.states.get("climate.mygrill_grill_temperature")
    assert climate is not None
    assert climate.state == "heat"
    assert climate.attributes["current_temperature"] == 275.0
    assert climate.attributes["temperature"] == 250.0


async def test_a_cold_grill_reads_off_rather_than_unknown(
    hass: HomeAssistant,
    spec: Grill,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data(
        testing.build_state(spec, moduleIsOn=False, isFahrenheit=True)
    )
    await hass.async_block_till_done()

    climate = hass.states.get("climate.mygrill_grill_temperature")
    assert climate is not None
    assert climate.state == "off"
    power = hass.states.get("switch.mygrill_module_power")
    assert power is not None
    assert power.state == STATE_OFF


async def test_no_entity_sits_unknown_on_a_full_report(
    hass: HomeAssistant,
    spec: Grill,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """The check a hand-written dictionary cannot make.

    Given everything the board can report, every entity the integration
    created for that board should have a value. One that does not is
    reading a field this board never sends -- the shape that put a
    permanently unknown "Startup error" sensor on PBM grills (#391), found
    then by a user rather than by this suite.
    """
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data(
        testing.build_state(
            spec, moduleIsOn=True, isFahrenheit=True, grillTemp=275, grillSetTemp=250
        )
    )
    await hass.async_block_till_done()

    # Entities that legitimately have no value here, none of which are fed
    # by the state frame:
    #   * buttons have no state until pressed
    #   * the controller diagnostics come from `Sys.GetInfo`, a separate
    #     call the mocked API answers with nothing
    #   * a probe target is unset until somebody sets one, and the sensor
    #     comparing against it has nothing to compare
    exempt = (
        "sensor.mygrill_controller_uptime",
        "sensor.mygrill_controller_free_memory",
    )
    stuck = [
        state.entity_id
        for state in hass.states.async_all()
        if not state.entity_id.startswith("button.")
        and state.entity_id not in exempt
        and not state.entity_id.endswith(("_target", "_target_reached"))
        and state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE)
    ]
    assert not stuck, f"{spec.name}: entities with no value from a full report: {stuck}"


async def test_the_error_flags_the_board_reports_all_read_off(
    hass: HomeAssistant,
    spec: Grill,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """A healthy grill, so every error sensor that exists should be off.

    Boards differ in which flags they carry -- PBM and PBM2 have no `erL`
    at all -- and this asserts against whichever ones the board actually
    produced rather than a fixed list.
    """
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    state = testing.build_state(spec, moduleIsOn=True, isFahrenheit=True)
    coordinator.async_set_updated_data(state)
    await hass.async_block_till_done()

    errors = [
        s
        for s in hass.states.async_all("binary_sensor")
        if "err" in s.entity_id or "error" in s.entity_id
    ]
    assert errors, f"{spec.name}: no error sensors were created at all"
    for sensor in errors:
        assert sensor.state == STATE_OFF, f"{sensor.entity_id} is {sensor.state}"


async def test_a_reported_fault_reaches_the_entity(
    hass: HomeAssistant,
    spec: Grill,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """And the same sensors follow the board when a flag is set."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data(
        testing.build_state(spec, moduleIsOn=True, isFahrenheit=True, noPellets=True)
    )
    await hass.async_block_till_done()

    no_pellets = hass.states.get("binary_sensor.mygrill_no_pellets")
    assert no_pellets is not None
    assert no_pellets.state == STATE_ON
