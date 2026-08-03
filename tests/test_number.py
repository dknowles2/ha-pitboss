from collections.abc import Awaitable, Callable
from unittest.mock import Mock

import pytest
from conftest import get_entity
from homeassistant.core import HomeAssistant
from pytboss.exceptions import UnsupportedOperation
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitboss.const import DOMAIN
from custom_components.pitboss.coordinator import PitBossDataUpdateCoordinator
from custom_components.pitboss.number import TargetProbeTemperature


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_an_entity_per_probe(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """Every probe gets a target, whether or not the board has a command.

    This grill declares `set-probe-1-temperature` only; P2's target goes to
    the scratchpad instead. It has two probes, so there is no P3 or P4.
    """
    await mock_add_config_entry()
    assert hass.states.get("number.mygrill_mpc_target") is not None
    assert hass.states.get("number.mygrill_p2_target") is not None
    assert hass.states.get("number.mygrill_p3_target") is None


@pytest.mark.parametrize("model", ["PB1150PS3"])
async def test_both_probe_entities_created(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """This grill has no MPC, so the ports keep their plain numbering."""
    await mock_add_config_entry()
    assert hass.states.get("number.mygrill_probe_1_target") is not None
    assert hass.states.get("number.mygrill_probe_2_target") is not None


@pytest.mark.parametrize("model", ["PB2180LK"])
async def test_probes_without_any_command_still_get_targets(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    """This grill declares no probe command at all, and has four probes.

    Before the scratchpad route it got no target entities whatsoever.
    """
    await mock_add_config_entry()
    for probe_number in (1, 2, 3, 4):
        entity_id = f"number.mygrill_probe_{probe_number}_target"
        assert hass.states.get(entity_id) is not None, entity_id


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_native_value_and_availability(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Available with no probe plugged in: a target can be dialled in before
    # the probe goes into the meat.
    coordinator.async_set_updated_data({"p1Target": 165, "isFahrenheit": True})
    await hass.async_block_till_done()
    state = hass.states.get("number.mygrill_mpc_target")
    assert state is not None
    assert state.state == "165"

    coordinator.async_set_updated_data(
        {"p1Target": 165, "p1Temp": 70, "isFahrenheit": True}
    )
    await hass.async_block_till_done()
    state = hass.states.get("number.mygrill_mpc_target")
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
        {"entity_id": "number.mygrill_mpc_target", "value": 180},
        blocking=True,
    )
    mock_pitboss.set_probe_target.assert_awaited_once_with(1, 180)


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_native_value_none_without_data(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
) -> None:
    await mock_add_config_entry()
    entity = get_entity(
        hass, "number", "number.mygrill_mpc_target", TargetProbeTemperature
    )
    assert entity.native_value is None


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_setting_a_target_goes_through_the_library(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """Which route a probe takes is pytboss's business, not ours."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_updated_data({"moduleIsOn": True, "isFahrenheit": True})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.mygrill_p2_target", "value": 165},
        blocking=True,
    )

    mock_pitboss.set_probe_target.assert_awaited_once_with(2, 165)
    state = hass.states.get("number.mygrill_p2_target")
    assert state is not None
    assert state.state == "165"


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_a_target_set_while_off_is_kept(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """The grill's store rejects writes while it is off."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    mock_pitboss.set_probe_target.side_effect = UnsupportedOperation
    coordinator.async_set_updated_data({"moduleIsOn": False, "isFahrenheit": True})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.mygrill_p2_target", "value": 165},
        blocking=True,
    )

    # Still shown, so the user sees what will be sent at power-on.
    state = hass.states.get("number.mygrill_p2_target")
    assert state is not None
    assert state.state == "165"
    assert coordinator.restored_targets[2] == 165


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_a_target_set_while_off_is_written_at_power_on(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """What makes setting a target on a cold grill mean anything."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    mock_pitboss.set_probe_target.side_effect = UnsupportedOperation
    coordinator.async_set_updated_data({"moduleIsOn": False, "isFahrenheit": True})
    await coordinator.async_set_probe_target(2, 165)

    mock_pitboss.set_probe_target.side_effect = None
    mock_pitboss.get_probe_targets.return_value = {}
    await coordinator._async_refresh_probe_targets({"moduleIsOn": True})

    mock_pitboss.set_probe_target.assert_awaited_with(2, 165)


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_targets_are_seeded_only_once_per_power_cycle(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    mock_pitboss.set_probe_target.side_effect = UnsupportedOperation
    coordinator.async_set_updated_data({"moduleIsOn": False, "isFahrenheit": True})
    await coordinator.async_set_probe_target(2, 165)
    mock_pitboss.set_probe_target.side_effect = None
    mock_pitboss.set_probe_target.reset_mock()
    mock_pitboss.get_probe_targets.return_value = {}

    for _ in range(3):
        await coordinator._async_refresh_probe_targets({"moduleIsOn": True})
    assert mock_pitboss.set_probe_target.await_count == 1

    # Power cycle: the grill's store is wiped, so it has to be seeded again.
    await coordinator._async_refresh_probe_targets({"moduleIsOn": False})
    await coordinator._async_refresh_probe_targets({"moduleIsOn": True})
    assert mock_pitboss.set_probe_target.await_count == 2


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_a_target_the_grill_already_has_is_not_overwritten(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """One set elsewhere wins over the one we are holding."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    mock_pitboss.set_probe_target.side_effect = UnsupportedOperation
    coordinator.async_set_updated_data({"moduleIsOn": False, "isFahrenheit": True})
    await coordinator.async_set_probe_target(2, 165)
    mock_pitboss.set_probe_target.side_effect = None
    mock_pitboss.set_probe_target.reset_mock()
    mock_pitboss.get_probe_targets.return_value = {2: 190}

    await coordinator._async_refresh_probe_targets({"moduleIsOn": True})

    mock_pitboss.set_probe_target.assert_not_awaited()
    assert coordinator.probe_target(2) == 190


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_a_target_restored_after_a_power_cycle_still_reaches_the_grill(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """The grill cycled while Home Assistant was down, and is on again.

    Entities are added after the coordinator's first refresh, so by the time
    a restored target arrives the coordinator has already seeded against an
    empty set. Without re-arming, the target would show here and never be
    written to the grill.
    """
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    # First refresh: grill is on, its store was wiped by the power cycle.
    await coordinator._async_refresh_probe_targets({"moduleIsOn": True})
    mock_pitboss.set_probe_target.reset_mock()

    # The entity now restores what we were holding before the restart.
    coordinator.note_restored_target(2, 165)
    await coordinator._async_refresh_probe_targets({"moduleIsOn": True})

    mock_pitboss.set_probe_target.assert_awaited_once_with(2, 165)


@pytest.mark.parametrize("model", ["PBV4PS2"])
async def test_a_restored_target_the_grill_already_has_is_not_rewritten(
    hass: HomeAssistant,
    mock_add_config_entry: Callable[[], Awaitable[MockConfigEntry]],
    mock_pitboss: Mock,
) -> None:
    """Re-arming must not overwrite a target set from the vendor's app."""
    entry = await mock_add_config_entry()
    coordinator: PitBossDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    mock_pitboss.get_probe_targets.return_value = {2: 190}
    await coordinator._async_refresh_probe_targets({"moduleIsOn": True})
    mock_pitboss.set_probe_target.reset_mock()

    coordinator.note_restored_target(2, 165)
    await coordinator._async_refresh_probe_targets({"moduleIsOn": True})

    mock_pitboss.set_probe_target.assert_not_awaited()
    assert coordinator.probe_target(2) == 190
