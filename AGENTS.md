# Agent instructions for ha-pitboss

`ha-pitboss` is a HACS custom component for Home Assistant that talks to
PitBoss/Dansons grills. It is a thin shell over
[pytboss](https://github.com/dknowles2/pytboss), which does all the protocol
work.

- [REVIEW.md](REVIEW.md) — where a change belongs, and the mistakes this repo
  has actually made. Read it before changing anything that touches control
  boards, grill models, or temperatures.
- [CONTRIBUTING.md](CONTRIBUTING.md) — fork-and-PR mechanics.

## Bumping the pytboss version

**The pin lives in two files. Change both, in the same PR, every time.**

```sh
grep pytboss requirements.txt custom_components/pitboss/manifest.json
```

- `requirements.txt` — what CI installs.
- `custom_components/pitboss/manifest.json`, in the `requirements` array —
  what Home Assistant installs for users.

Changing only one is the failure this section exists for, and it is silent:
CI resolves the new release and goes green while every real install keeps the
old one. Nothing surfaces until code uses something the older release does not
have, and then it is an `AttributeError` during setup on users' machines, with
a passing build behind it. This happened with 2026.8.2 — `requirements.txt`
moved, `manifest.json` did not, and a PR was written against a `Grill.has_mpc`
that shipped users did not have.

Dependabot opens only the `requirements.txt` half, so its bump PRs need the
manifest edited in before merging.

Before relying on a pytboss attribute, confirm it exists in the version the
**manifest** pins, not the one CI happens to resolve:

```sh
git -C ../pytboss show <pinned-version>:pytboss/grills.py | grep <attribute>
```

Keep a bump in its own PR, separate from any code that depends on it, and
merge in order — a PR that reads a new attribute is blocked on the release
*and* on the bump landing first, and neither CI nor GitHub can express that.
Say so in the PR.

## Update the docs in the PR that changes the behaviour

`README.md` is what users read to decide whether this integration does what
they want. It is part of the change, not follow-up work — a PR that adds an
entity and leaves the README alone is incomplete, and the gap is invisible in
review because nothing fails.

Update it in the same PR when a change:

- **adds, removes or renames an entity**, or changes when one is created —
  the platform table and the entity list both name specific entities;
- **adds a platform** — the table lists platforms, and `PLATFORMS` in
  `__init__.py` is the list to check it against;
- **adds or changes an action** — see the Actions section;
- **changes what a user sees or has to do**: setup and reconfigure steps,
  repair flows, a new option, polling behaviour they would notice;
- **changes something the README states as a fact** — connection protocols,
  what is and is not local, or the safety position on remote start.

Two things to check rather than assume:

```sh
# Every platform the integration actually sets up.
grep -A 12 'PLATFORMS: list\[Platform\]' custom_components/pitboss/__init__.py
# Every entity name a user will see.
grep -rn '_attr_name' custom_components/pitboss/
```

The README drifted a whole release behind once — it described probe targets
as existing for probes 1 and 2 only, listed six platforms when eight were
registered, and called the `wss` protocol "local WiFi" when it connects
outbound to `socket.dansonscorp.com`. Each of those was correct when written,
and none of them failed a test.

`CONTRIBUTING.md` and `REVIEW.md` change far less often; touch them when the
workflow or the repo boundary genuinely moves, not routinely.

`docs/SUPPORTED_GRILLS.md` is generated — see below.

## Gotchas

- **Generated files — don't hand-edit**:
  - `docs/SUPPORTED_GRILLS.md` is produced by `scripts/generate_grill_docs.py`
    from whatever pytboss is installed. `.github/workflows/update-grill-docs.yml`
    regenerates and commits it whenever the `pytboss==` pin in
    `requirements.txt` changes, so it should never appear in a hand-authored
    diff.
  - `manifest.json`'s `version` is kept in step by `sync-manifest-version.yml`.
    Its `requirements` array is not — that one is yours, see above.
- **Never remap a control board here.** `control_board` comes from the device
  ID prefix and is a fact about the hardware. This repo has made that mistake
  twice, and both times it produced frames read at the wrong offsets. If a
  model cannot be added, the fix is upstream in pytboss. REVIEW.md has both
  cases in full.
- **The test suite runs everywhere, including macOS.** `homeassistant.setup`
  pulls in the `bluetooth` component, which reads BlueZ advertisement history
  through the Linux-only `dbus_fast`. `mock_bluetooth_adapter_history` in
  `tests/conftest.py` stubs that read out. If *every* test in a file starts
  failing on `bluetooth_adapters`, including ones the change does not touch,
  that fixture has stopped covering what upstream now reads — widen it rather
  than writing the failure off as environmental.

## Before committing

Run the same checks CI runs, and make sure all three pass:

```sh
uv run pytest
uv run ruff check .
uv run mypy .
```

Run `mypy .`, not `mypy custom_components/pitboss` — CI checks the whole tree,
and errors in `tests/` are easy to miss otherwise.
