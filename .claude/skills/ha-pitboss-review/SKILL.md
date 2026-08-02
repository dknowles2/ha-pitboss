---
name: ha-pitboss-review
description: Reviews changes to the ha-pitboss Home Assistant integration. Use when reviewing a pull request, a branch, or uncommitted changes in this repository. Covers the boundary with the pytboss library, Home Assistant entity conventions, and the verification traps specific to this repo.
---

# Review ha-pitboss changes

Adapted from Home Assistant Core's `ha-review` and `ha-integration-knowledge`
skills (Apache-2.0). Modified for a HACS custom component: the quality-scale
machinery and core file paths do not apply here, and the repository-specific
sections are new.

## Scope

Review the branch's changes plus any uncommitted ones against the base. The
base branch here is `main`, not `dev`:

```sh
git diff "$(git merge-base origin/main HEAD)"
```

For a pull request, get context with `gh pr view` and `gh pr diff` first.

**Review only. Do not make changes, and do not post to GitHub — report in the
console.** Do not spawn subagents; this repository is small enough to review
directly.

## 1. The boundary with pytboss — check this first

This integration is a thin shell over
[pytboss](https://github.com/dknowles2/pytboss). Home Assistant Core states the
rule directly, and it is the one this repo has broken twice:

> Integrations should be thin wrappers. Protocol parsing, device state
> machines, or other domain logic belong in a separate PyPI library, not in the
> integration itself.

> Integrations should not implement fixes or workarounds for limitations in
> libraries. Instead, the library should be updated to fix the issue.

Concretely, **flag any change that remaps, aliases, or rewrites a control
board.** `control_board` comes from the device ID prefix and is a fact about
the hardware:

```python
control_board = self._device_id.split("-")[0]
```

Both past violations looked like one-line config-flow fixes that made a model
selectable, and both produced frames read at the wrong offsets afterwards —
`PBL2` grills borrowing `PBL3`'s definitions were converted to celsius twice
(225°F shown as 107), and the proposed `LBL`→`PBL` alias would have read frames
three bytes short. If a model cannot be added, the fix belongs upstream.

See [REVIEW.md](../../../REVIEW.md) for the full symptom-to-repo table. The
short version: anything that would still be wrong with no Home Assistant in the
picture belongs in pytboss.

## 2. Home Assistant conventions

- Polling intervals are not user-configurable. Reject `scan_interval`,
  `update_interval`, or polling-frequency options in config flows.
- Do not let users set the config entry name in a config flow.
- `async_added_to_hass()` and `async_will_remove_from_hass()` must be
  symmetrical — anything subscribed in one is unsubscribed in the other.
- Do not redeclare attributes, properties, or methods the entity base class
  already provides, and do not guard against the base class changing.
- Where Home Assistant's schema validation guarantees a key, index it directly
  (`data["key"]`) rather than `.get("key")`, so a bad assumption fails loudly.
- Avoid defensive checks for values Home Assistant already validates; add
  guards only where a value bypasses validation or is transformed unsafely.
- Tests should not reach into the integration's internals. Drive it through
  Home Assistant's own interfaces.

## 3. Verification traps in this repo

These have each produced a wrong review conclusion before.

- **Run `mypy .`, not `mypy custom_components/pitboss`.** CI checks the whole
  tree, and errors in `tests/` are missed otherwise.
- **A wholesale test failure is usually environmental.** If every test in a
  file fails on `bluetooth_adapters` — including ones the change does not touch
  — `homeassistant.setup` cannot start the `bluetooth` component locally. That
  is not the change. Say the suite could not be run rather than implying it
  passed.
- **Check assertions are not vacuous.** A test asserting only that *some*
  models came back passes whether or not the behaviour it names still holds;
  that is how the `PBL2` workaround survived. Confirm against pytboss directly:

  ```sh
  python -c "from pytboss import grills; print(sorted(g.name for g in grills.get_grills('PBL2')))"
  ```

- **`docs/SUPPORTED_GRILLS.md` is generated.** It should not appear in a
  hand-authored diff; `update-grill-docs.yml` regenerates it when the
  `pytboss==` pin changes. A version bump belongs in its own PR.

## 4. Also review for

Code quality and consistency, bugs, performance, security, test coverage, and
whether user-facing changes need documentation.

## Output format

List specific comments per file and line, then an overall assessment. Do not
list what is already fine.

```
Overall assessment: request changes.
- [CRITICAL] config_flow.py:88 - Remaps PBL2 to PBL3; belongs in pytboss
- [PROBLEM] coordinator.py:41 - Subscription never torn down
- [SUGGESTION] test_sensor.py:20 - Assertion passes even if the entity is absent
```
