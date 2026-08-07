"""The contract between this integration and pytboss.

Every other test in this suite runs against a mocked `pytboss.api.PitBoss`,
so the state dictionaries the entities are driven from are written here by
hand. That makes the suite fast and precise about *this* repo's reasoning,
and blind to the boundary: pytboss could rename a key, drop a field, or stop
emitting one on some board, and nothing here would fail until a user
reported an entity stuck at unknown.

These tests read the real library instead of a mock. They do not exercise
the transports -- that needs a grill -- but they hold the two things most
likely to drift apart between releases of two repos that ship separately.
"""

from typing import get_type_hints

import pytest
from pytboss import grills
from pytboss.grills import StateDict

from custom_components.pitboss.binary_sensor import (
    ENTITY_DESCRIPTIONS as BINARY_SENSOR_DESCRIPTIONS,
)
from custom_components.pitboss.sensor import PROBE_ENTITY_DESCRIPTIONS

# Keys this integration reads out of a state dictionary. Kept as a literal
# rather than scraped from the source: the point is to notice when the two
# repos disagree, and a list derived from the same code it is checking would
# follow a rename rather than catch it.
STATE_KEYS_READ = frozenset(
    {
        "erL",
        "err1",
        "err2",
        "err3",
        "fanErr",
        "fanState",
        "grillSetTemp",
        "grillTemp",
        "highTempErr",
        "hotErr",
        "hotState",
        "isFahrenheit",
        "lightState",
        "moduleIsOn",
        "motorErr",
        "motorState",
        "noPellets",
        "p1Temp",
        "p2Temp",
        "p3Temp",
        "p4Temp",
        "primeState",
        "recipeStep",
        "recipeTime",
    }
)

# `probe_target` reads `pNTarget` for every probe the grill has, but pytboss
# only ever puts probes 1 and 2 in the state -- no board's routine emits a
# third or fourth. The read is deliberate rather than dead: it costs nothing,
# and a definitions refresh that starts emitting one would be picked up
# without a change here. Listed so the subset check below stays honest about
# what it is not covering.
PROBE_TARGET_KEYS_READ_BUT_NEVER_EMITTED = frozenset({"p3Target", "p4Target"})


def test_every_state_key_the_integration_reads_is_declared_by_pytboss() -> None:
    """A renamed or dropped key should fail here, not in someone's logbook."""
    declared = set(get_type_hints(StateDict))
    assert STATE_KEYS_READ <= declared, (
        "these keys are read by the integration but no longer declared by "
        f"pytboss's StateDict: {sorted(STATE_KEYS_READ - declared)}"
    )


def test_the_probe_target_keys_we_tolerate_missing_are_still_missing() -> None:
    """The moment a board reports one, the tolerance above is worth revisiting.

    Not a failure so much as a prompt: probes 3 and 4 would gain a
    board-reported target, which `probe_target` already prefers over the
    virtual data store.
    """
    declared = set(get_type_hints(StateDict))
    assert not (PROBE_TARGET_KEYS_READ_BUT_NEVER_EMITTED & declared), (
        "pytboss now declares a probe target this integration assumed was "
        "never reported; check `probe_target`'s ordering still makes sense"
    )


def test_every_binary_sensor_key_is_a_field_pytboss_declares() -> None:
    """A description keyed to something pytboss does not report is dead.

    `emits()` would answer False for it on every board, so the entity would
    silently never be created anywhere -- which looks identical to the
    feature working until someone goes looking for the sensor. A typo in a
    new description fails here instead.
    """
    declared = set(get_type_hints(StateDict))
    keyed = {d.key for d in BINARY_SENSOR_DESCRIPTIONS}
    assert keyed <= declared, (
        "binary sensor descriptions keyed to fields pytboss does not "
        f"declare: {sorted(keyed - declared)}"
    )


def test_every_binary_sensor_description_is_reachable_on_some_board() -> None:
    """The same rot, caught one step later.

    A field can be declared by `StateDict` and still be emitted by no board
    -- pytboss drops some per board, and a definitions refresh can retire
    one outright. Either way the description is dead weight, and nobody
    finds out from an entity that is simply absent.
    """
    boards = {g.control_board.name: g.control_board for g in grills.get_grills()}
    unreachable = [
        d.key
        for d in BINARY_SENSOR_DESCRIPTIONS
        if not any(b.emits(d.key) for b in boards.values())
    ]
    assert not unreachable, (
        f"no catalogued board reports these, so the entities are never "
        f"created for anyone: {sorted(unreachable)}"
    )


@pytest.mark.parametrize("grill", grills.get_grills(), ids=lambda g: g.name)
def test_every_probe_the_grill_declares_can_actually_be_reported(
    grill: grills.Grill,
) -> None:
    """`meat_probes` decides which probe sensors ship enabled.

    It comes from the model, and whether the field can be reported at all
    comes from the board's parsing routine -- two different sources that
    have to agree, or a grill ships an enabled sensor that is unknown for
    the life of the entry.
    """
    board = grill.control_board
    probes = grill.meat_probes or 0
    for description in PROBE_ENTITY_DESCRIPTIONS:
        if description.probe_number > probes:
            continue
        assert board.emits(description.key), (
            f"{grill.name} declares {probes} meat probes, so probe "
            f"{description.probe_number} ships enabled, but board "
            f"{board.name} never reports {description.key}"
        )
