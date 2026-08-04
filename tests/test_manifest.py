"""The manifest's discovery matchers must track the pytboss catalogue."""

import json
import pathlib

from pytboss import grills

MANIFEST = (
    pathlib.Path(__file__).parent.parent
    / "custom_components"
    / "pitboss"
    / "manifest.json"
)


def _supported_boards() -> set[str]:
    """Board names with at least one model the config flow would offer.

    Enumerated through the private catalogue because nothing public lists
    board names; `get_grills()` with no filter yields one entry per model,
    which hides the older board of every dual-board pair.
    """
    names = {grill["control_board"]["name"] for grill in grills._get_grills().values()}
    return {name for name in names if any(grills.get_grills(control_board=name))}


def test_bluetooth_matchers_track_the_catalogue() -> None:
    """Both drift directions have shipped: a matcher for a board whose only
    model is unsupported walked users into an unknown_grill dead end, and
    five supported boards had no matcher at all, so those grills were never
    discovered. This fails the build when the catalogue moves again.
    """
    manifest = json.loads(MANIFEST.read_text())
    matchers = {entry["local_name"] for entry in manifest["bluetooth"]}
    expected = {f"{board}-*" for board in _supported_boards()}
    assert matchers == expected
