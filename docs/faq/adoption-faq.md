# Adoption FAQ

For an engineering lead forking this repo as their institution's migration copilot. The
step-by-step is [`../ADOPTING.md`](../ADOPTING.md); this answers the "will it hurt later?"
questions.

### How do I rebrand it for my organisation?

`scripts/rename_fork.py` rewrites the package name (`code_api_migration`), the
console-script name (the same token, see `[project.scripts]`), the `CODEMIGRATION` env prefix, the
Terraform resource stem (`h5-svc`) and the distribution and git id
(`code-api-migration`) in one simultaneous pass, so no rule can rewrite another rule's
output. Preview with `--dry-run`, apply with `--yes`, add `--include-docs` to sweep the Markdown
too. Then recreate the venv, `make install`, and run `make gate`. The script does the mechanical
rename only; the human decisions are the checklist in `ADOPTING.md`.

### If several teams fork this, how does each take upstream fixes?

Track upstream by **git tag** and pin your baseline. The repo declares a core-vs-adopter-owned
boundary (`ADOPTING.md` section 2): upstream owns `domain/kernel.py`, the five pure engines,
`ports/`, `tests/contract/`, the eval harness mechanics and the hexagon wiring in `config.py`; you
own the rule packs, the `config/settings.yaml` values, the fixture checkouts, `adapters/onprem/*`,
UI theming and the eval golden set. Rebase your adopter-owned changes onto each release rather
than merging `main` continuously, so conflicts stay in the files you were told to expect.

### Is there a kernel module I can keep untouched?

Yes, and the split is physical rather than described. `domain/kernel.py` holds the
vertical-neutral machinery (`Severity`, `Decision`, `Citation`, `AuditEvent`, `utcnow`) and
imports nothing from this vertical; `domain/models.py` holds the migration artifacts and imports
`kernel`, never the reverse. A fork building a different vertical rewrites `models.py` and leaves
`kernel.py` alone. `docs/practices-audit.md` records this as check A7, PASS.

### How do I add a migration for a framework we actually use?

Add `config/packs/<framework>/pack.yaml`. Packs are configuration, not code:
`domain/pack_loader.py` parses them and refuses an unknown framework, an unknown rule kind, a
missing required field for a kind, a stray key or a duplicate rule id, all AT LOAD, so a malformed
rule can never degrade into a false PASS. Each rule carries its own `severity:` and the pack
carries the `source:` that becomes the finding's citation. The three shipped rule kinds are
`deprecated_call`, `signature_change` and `semver_window`; adding a new KIND is the one change
that reaches into `pack_loader.py` and `breaking_change_engine.py` together, and it needs a unit
test that proves the new kind can return FAIL and NEEDS_INFO.

### How do I add a new outbound dependency (a new port)?

A port lives in FIVE places at once, and four of the five can be satisfied while the fifth is
missing, which produces a port with zero enforcement and a green build. So
`tests/contract/test_port_parity.py::test_every_home_of_the_port_set_agrees_exactly` asserts set
equality across all five: the Protocol re-export and `PORT_PROTOCOLS` in `ports/__init__.py`,
`config.DEFAULT_BINDINGS`, a `Container` accessor, `config/settings.yaml`, and a `PortCase` in
`tests/contract/canonical.py`. Then bind it in all three families: `local` must WORK offline,
`gcp` must import its SDK lazily, `onprem` must RAISE. The full file-by-file touch list, with the
test that enforces each row, is in [`CONTRIBUTING.md`](../../CONTRIBUTING.md).

### Can I retune the policy numbers without touching code?

Partly, and this is called out honestly. Per-rule severity IS configuration already: it lives in
the pack next to the rule, so a bank sets it without an engine edit. What is still module-level
is the dual-control band (`_DUAL_CONTROL` in `adapters/_review_payload.py`, CRITICAL today), the
PII jurisdiction list (`domain/pii.py`) and the eval thresholds (`eval/run_eval.py`). Lifting the
dual-control threshold into a `policy:` block in `config/settings.yaml` is the open B4 item in
[`../practices-audit.md`](../practices-audit.md). If your risk function must own these as
configuration, plan that small addition as part of adoption.

### How do I change the taxonomy?

`Severity`, `Decision`, `RuleStatus` and `PatchStatus` are `LenientStrEnum` vocabularies from the
shared commons, so a member IS its wire value and an unknown value from a future release does not
crash the reader. Extend the vocabulary without editing engine code; replace it wholesale by
editing the enums in `domain/kernel.py` (neutral) or `domain/models.py` (this vertical).

### Will the demo rot after I diverge?

It is guarded twice. A step exists in exactly two places, `demo.STEPS` and `walkthrough.CHECKS`,
and `tests/unit/test_demo_surface.py` holds the two sets equal inside `make gate`, so a narrated
claim nobody verifies cannot exist. The same test then drives the WHOLE arc against the real
adapters and applies each step's own expectation. On top of that `make demo-selftest` runs the
real walkthrough headless in the demo-gate workflow. Keep both halves when you add a step, and put
the numbers a check reads in the step's `facts` dict rather than only in the rendered prose: a
check that parses prose breaks on a wording change.

### Does the build work for my fork out of the box?

Yes, offline. `make gate` needs no network, no cloud SDK, no project and no credentials, and the
workflows reference no `secrets.` at all, so a fork's build is green immediately. You add
credentials only when you wire the `gcp` profile. Note that the eval gate measures the REFERENCE
packs and golden cases until you rebuild them: that is an explicit adoption step, not a silent
pass. Version your fork with `pyproject.toml version` plus a git tag.

### What should I read before I start?

[`../ADOPTING.md`](../ADOPTING.md) for the checklist, [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md)
for the touch lists, [`../../COMPLIANCE.md`](../../COMPLIANCE.md) for what the base does and does
not yet claim, and [`../practices-audit.md`](../practices-audit.md) for the per-check verdicts you
inherit.
