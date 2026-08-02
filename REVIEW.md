# Reviewing changes to ha-pitboss

This integration is a thin Home Assistant shell over
[pytboss](https://github.com/dknowles2/pytboss), which does all the protocol
work and is pinned in `requirements.txt`. That repo has its own `REVIEW.md`
describing the same boundary from the other side.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the fork-and-PR mechanics. This
document is about *where* a change belongs.

## What lives here

Home Assistant's half of the problem, and only that:

- The config and options flows (`config_flow.py`)
- The update coordinator and its polling (`coordinator.py`)
- Entity platforms — `climate`, `sensor`, `binary_sensor`, `switch`, `light`,
  `number` — and their naming, units, device classes, and registry entries
- Translations

## What does not

Frames, offsets, commands, control boards, and which models exist. If a change
would still be correct with no Home Assistant in the picture, it belongs
upstream in pytboss.

## Deciding which repo a bug belongs to

| Symptom | Repo |
| --- | --- |
| An entity is missing, misnamed, or in the wrong unit | here |
| Setup UX, options flow, reauth, discovery text | here |
| Polling frequency, availability, coordinator behaviour | here |
| A grill can be discovered but not added | pytboss — definitions |
| Temperatures wrong, doubled, or shifted by a constant | pytboss — board parsing |
| A model is missing from the picker | pytboss — definitions |
| A command does nothing | pytboss |

The grill's own behaviour is never this repo's to fix.

## The mistake to watch for

**Never work around a protocol problem by remapping a control board here.**

This integration has made that mistake twice, and both are instructive because
each one *appeared* to work:

- It carried `if control_board == "PBL2": control_board = "PBL3"` in
  `config_flow.py`, because pytboss had no `PBL2` definitions. The grill became
  selectable — and then reported nonsense in celsius, because `PBL3` applies a
  fahrenheit-to-celsius conversion that `PBL2` has commented out. Setpoints
  were converted twice: 225°F shown as 107. #315 removes it.
- #258 proposed aliasing the BLE prefix `LBL` to the board `PBL` to make those
  grills addable. `LBL` frames are three bytes shorter than `PBL` frames, so
  every field after the missing one would have been read at the wrong offset.
  Superseded by definitions work upstream.

The tell is the same in both: a one-line change in the config flow that makes
a model selectable without anything having learned to parse it. The board a
grill advertises is a fact about the hardware. If it isn't supported, the fix
is upstream.

`control_board` comes from the device ID prefix:

```python
control_board = self._device_id.split("-")[0]
```

Pass it through rather than translating it. `pytboss.PitBoss` accepts
`control_board=` for exactly this reason — several models ship on two board
generations that do not parse identically, and omitting it takes the vendor's
most recent board, which is not always the one in front of you. Note that
manually entered device IDs may carry no prefix at all, so that path needs
deciding rather than assuming.

## Generated files

`docs/SUPPORTED_GRILLS.md` is produced by `scripts/generate_grill_docs.py` from
whatever pytboss version is installed. Don't hand-edit it, and don't include it
in a version-bump PR — `.github/workflows/update-grill-docs.yml` regenerates
and commits it whenever the `pytboss==` pin in `requirements.txt` changes, and
can also be run on demand via `workflow_dispatch`.

That workflow pushes straight to `main`, which the `Main` ruleset would
otherwise refuse — the failure looks like `GH013: Repository rule violations`.
The bypass is granted to deploy keys rather than to the GitHub Actions app, so
no workflow's `GITHUB_TOKEN` can reach `main`; the job clones with a
write-enabled deploy key whose private half is an environment secret on the
`docs` environment, restricted to `main`. Adding another write-enabled deploy
key to this repo would silently inherit that bypass, since the rulesets API
scopes it to deploy keys as a class rather than to one key.

`manifest.json`'s version is kept in step by `sync-manifest-version.yml`.

## Testing

CI runs, and a PR should pass:

```sh
uv run pytest
uv run ruff check .
uv run mypy .
```

Run `mypy .` rather than `mypy custom_components/pitboss` — CI checks the whole
tree, and errors in `tests/` are easy to miss otherwise.

The suite may not run locally. `homeassistant.setup` needs the `bluetooth`
component, which fails to start in some environments; the symptom is *every*
test in a file failing on `bluetooth_adapters`, including ones untouched by the
change. That is environmental, and CI is then the real check — but say so in
the PR rather than implying the tests were run.

When a test asserts against pytboss data, confirm the assertion isn't vacuous
by resolving the same values directly:

```sh
python -c "from pytboss import grills; print(sorted(g.name for g in grills.get_grills('PBL2')))"
```

A test that only asserts "some models came back" passes whether or not the
behaviour it names still exists. That is precisely how the `PBL2` workaround
survived as long as it did.

## Version bumps

A pytboss release is what carries protocol fixes into this repo:

1. pytboss is released.
2. Dependabot opens a `requirements.txt` bump, or bump it yourself in its own
   PR, separate from any code that depends on it.
3. Merging that bump regenerates `docs/SUPPORTED_GRILLS.md` automatically.

If a change here needs a pytboss version that isn't released yet, say so in the
PR and merge in order — stacked PRs that depend on an unreleased library will
fail CI in a way that looks like the change is broken.
