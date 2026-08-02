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
- **The test suite often cannot run locally.** `homeassistant.setup` needs the
  `bluetooth` component, which fails to start in some environments; the symptom
  is *every* test in a file failing on `bluetooth_adapters`, including ones the
  change does not touch. That is environmental, and CI is then the real check —
  say so rather than implying the tests were run.

## Before committing

Run the same checks CI runs, and make sure all three pass:

```sh
uv run pytest
uv run ruff check .
uv run mypy .
```

Run `mypy .`, not `mypy custom_components/pitboss` — CI checks the whole tree,
and errors in `tests/` are easy to miss otherwise.
