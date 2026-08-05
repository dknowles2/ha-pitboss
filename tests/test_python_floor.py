"""Every shipped module must parse on the oldest Python we admit.

CI runs the version in `.python-version` (3.14), but `hacs.json` admits Home
Assistant releases that run on older interpreters, and the integration is
loaded by the user's Home Assistant rather than by CI. So syntax newer than
the floor is invisible to every check and fatal on install: a module that
cannot be imported takes the whole integration down, and `config_flow.py`
failing to import breaks setup for every protocol, not just a new one.

This nearly shipped once. With `target-version` set to 3.14, `ruff format`
rewrote `except (A, B):` into PEP 758's `except A, B:` -- valid on 3.14, a
SyntaxError before it -- and the reformatted file passed lint, format, mypy
and the suite.

The floor is read from `.ruff.toml` rather than repeated here, so the
formatter's target and this check cannot drift apart.
"""

import ast
import pathlib
import re
import tomllib

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent
COMPONENT = REPO_ROOT / "custom_components" / "pitboss"


def _floor() -> tuple[int, int]:
    """The (major, minor) `target-version` in `.ruff.toml`."""
    config = tomllib.loads((REPO_ROOT / ".ruff.toml").read_text())
    target = config["target-version"]
    match = re.fullmatch(r"py(\d)(\d+)", target)
    assert match, f"unrecognized target-version: {target}"
    return int(match.group(1)), int(match.group(2))


def test_the_floor_is_not_newer_than_the_home_assistant_version_we_admit():
    """`hacs.json` admits 2025.1.0, whose Python floor is 3.12."""
    major, minor = _floor()
    assert (major, minor) <= (3, 12), (
        f"target-version is py{major}{minor}, but hacs.json admits Home "
        "Assistant 2025.1.0, which runs on Python 3.12. Raising this lets "
        "the formatter emit syntax those users cannot import."
    )


@pytest.mark.parametrize(
    "path",
    sorted(COMPONENT.rglob("*.py")),
    ids=lambda p: p.name,
)
def test_module_parses_on_the_oldest_supported_python(path: pathlib.Path):
    try:
        ast.parse(path.read_text(), filename=str(path), feature_version=_floor())
    except SyntaxError as ex:
        major, minor = _floor()
        pytest.fail(
            f"{path.relative_to(REPO_ROOT)} does not parse on Python "
            f"{major}.{minor}: {ex.msg} (line {ex.lineno})"
        )
