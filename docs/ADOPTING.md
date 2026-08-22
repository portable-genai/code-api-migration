# Adopting this repo as your base

This repository (H5, the Code and API Migration Copilot) is a **common base** that a bank or
other regulated institution forks to build its own **repository migration analyser**: a service
that parses a target checkout, builds its dependency graph, evaluates versioned breaking-change
rule packs against it, and produces a cited, reviewable migration plan with drafted patches that
a human approves before anything is written back. It ships a reusable hexagonal core (a
stdlib-only domain, typed ports, three swappable adapter families, a green offline gate) plus a
fully worked migration vertical you can keep, retune, or replace with your own rule packs.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical rebrand**
(one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (the layout and the port table),
> [`CONTRIBUTING.md`](../CONTRIBUTING.md) (the file-by-file touch list for adding an adapter or a
> port), [`COMPLIANCE.md`](../COMPLIANCE.md) (what is covered and what is still owed), the
> [`faq/`](faq/) directory.

---

## 1. What you keep vs what you rewrite

The domain is split physically, with an enforced dependency direction: `domain/models.py` imports
`domain/kernel.py` and never the reverse (practices-audit check A7). `kernel.py` holds the
vertical-neutral machinery and knows nothing about migrations; `models.py` holds this vertical's
artifacts. A fork building a different vertical rewrites `models.py` and leaves `kernel.py` alone.

| Layer | Where | For a new vertical or brand |
|---|---|---|
| **Kernel** (vertical-neutral) | All of `domain/kernel.py`: `Severity`, `Decision`, `Citation`, `AuditEvent`, `utcnow`. Plus every Protocol in `ports/` and the identity vocabulary in `ports/identity.py`, the `Container` wiring in `config.py`, and `adapters/_review_payload.py`'s redact-then-convert mechanics | keep untouched |
| **Policy** (your numbers) | The jurisdiction list `JURISDICTIONS` in `domain/pii.py`; `_SEVERITY_RANK` and `_MAX_CITATIONS` in `domain/migration_service.py`; the dual-control band `_DUAL_CONTROL` in `adapters/_review_payload.py`; the per-rule `severity:` values inside each pack; the `THRESHOLDS` in `eval/run_eval.py` | change deliberately (see section 4) |
| **Vertical** (the migration artifacts) | The models in `domain/models.py` (`RepoCheckout`, `Finding`, `MigrationPlan`, `PlanStep`, `PatchValidation`, `MigrationResult`, `PullRequestIntent`, `RuleStatus`, `PatchStatus`), the rule packs under `config/packs/`, the fixture checkouts in `fixtures/repos/`, the eval golden set, the UI plan views | rewrite or reseed for your estate |

If your product is another *repository analysis* tool, the five pure engines transfer directly:
`ast_engine.py` (stdlib `ast` facts), `dependency_graph.py` (topological order, refusal on
cycles), `breaking_change_engine.py` (four-valued machine rules), `plan_engine.py` (every FAIL
finding in exactly one dependency-ordered step) and `patch_engine.py` (apply in memory, re-analyse,
demote to draft unless the patch clears its finding and still parses). You replace the rule packs
and the fixtures, and you retune the policy numbers.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly.

- **Upstream-owned** (take our changes): `domain/kernel.py`, the five pure engines, `ports/`,
  `tests/contract/`, the eval harness mechanics (`eval/run_eval.py` structure), the hexagon wiring
  (`config.py` `Container`), `scripts/` and the CI workflows.
- **Adopter-owned** (yours; expect to edit): **the rule packs**, `config/settings.yaml` *values*,
  the fixture checkouts, `adapters/onprem/*`, UI theming and branding, the eval golden set, and
  the jurisdiction rows in `COMPLIANCE.md`.

**The rule packs are the prime adopter-owned surface.** `config/packs/<framework>/pack.yaml` is
configuration, never code: `domain/pack_loader.py` parses it, refuses any unknown field, kind or
framework at load, and hands the engine frozen `RulePack` objects, so a malformed rule cannot
degrade into a false PASS. The base ships two synthetic packs, `flask` and `requests`, whose rule
kinds are `deprecated_call`, `signature_change` and `semver_window`. Adding a migration for your
estate is a new pack directory, not an engine edit; adding a new rule *kind* is the one change
that reaches into `pack_loader.py` and `breaking_change_engine.py` together.

Track upstream via git tags; rebase your adopter-owned changes onto each release rather than
merging `main` continuously.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the python package (`code_api_migration`), the
console-script name (also `code_api_migration`, see `[project.scripts]`), the
`CODEMIGRATION` env-var prefix, the Terraform resource stem (`h5-svc`) and the distribution and
git id (`code-api-migration`) across the tree in ONE simultaneous pass, so no rule can
rewrite another rule's output. Preview first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_migration --cli acme-migrate \
    --env-prefix ACME --resource acme-migrate --dry-run

# Apply, including the Markdown prose:
python scripts/rename_fork.py --package acme_migration --cli acme-migrate \
    --env-prefix ACME --resource acme-migrate --include-docs --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
make install
make gate
```

`--dist` defaults to the package name with underscores hyphenated (`acme-migration` above); pass
it explicitly if your git id follows a different convention. Markdown is skipped unless you pass
`--include-docs`, so you can rename the code first and review the prose separately. `--resource`
is validated here against the same `^[a-z][a-z0-9-]{2,18}$` regex the Terraform `name_prefix`
variable enforces at plan time, so a bad stem fails in a second rather than at `terraform plan`.
The script deliberately does NOT touch the human decisions below.

## 4. The human decisions (the script can't make these)

1. **Region and residency.** The build is pinned to `asia-southeast1` in three places that must
   agree: `config/settings.yaml` (`region: ${GCP_REGION:-asia-southeast1}`),
   `infra/terraform/render.tf.json` (`local.render_region`), and the Terraform pair `var.region`
   and `var.allowed_regions` in your tfvars. The cross-variable validation on `var.region` fails
   at plan time if the effective region is outside the allowlist, so set the pair together. See
   [`runbook.md`](runbook.md).
2. **Identity and IdP.** This repo owns no login flow. `gcp` verifies the IAP-injected assertion
   and is the one adapter that declares `VERIFIED`, so set `CODEMIGRATION_IAP_AUDIENCE` to your
   IAP-protected backend service (unset or emptied REFUSES every caller, deliberately). `local`
   resolves seeded dev personas from `X-Dev-Persona` and is offline demo and test only; `onprem`
   is a client-IdP placeholder that raises rather than pretending. Wire your issuer on the
   deployed service, not in this code.
3. **The rule packs.** The shipped `flask` and `requests` packs are synthetic, and their rule set
   is the whole product surface: replace them with the frameworks, deprecated APIs and version
   windows your estate actually migrates. Each rule carries its own `severity:` and its own
   citation `source:`, which is what makes a finding traceable back to a migration note. Keep the
   loader strict: it is what stops a typo becoming a silently missing check.
4. **Policy numbers.** Own the numbers your engineering-risk function sets: the jurisdictions in
   `domain/pii.py`, the dual-control band `_DUAL_CONTROL` in `adapters/_review_payload.py`
   (CRITICAL demands two approvals today), and the eval thresholds in `eval/run_eval.py`
   (`detection_accuracy >= 0.80`, `plan_completeness == 1.0`, `pii_safety >= 0.99`). These are
   module constants and per-rule pack values today rather than a `policy:` block in
   `config/settings.yaml`; that lift is the open B4 item in
   [`practices-audit.md`](practices-audit.md). Change them deliberately and pin your values with a
   test.
5. **Reference data is fictional.** The three fixture checkouts under `fixtures/repos/`
   (`legacy_flask_app`, `tangled_service`, `tidy_app`) and every pack citation are obviously
   synthetic; the one national id in the fixtures exists solely so the redaction check has an
   independent literal to look for. Replace them with your own synthetic checkouts. **Do not run
   against real repositories without your own security and model-risk sign-off.**
6. **Eval golden set.** Rebuild `eval/datasets/golden_cases.jsonl` for your packs. A fork inherits
   a green gate that measures the WRONG ruleset until you do: the harness structure and the strict
   `pii_safety` metric are generic, the golden cases are yours.
7. **Deploy posture.** Review the Dockerfile (digest-pinned base, non-root uid 10001, `HEALTHCHECK`
   on `/healthz`) and `infra/terraform/` before you expose anything: the org-policy location
   allowlist and the key hygiene constraints (`org_policy.tf`), the regional CMEK key ring
   (`kms.tf`), the dry-run-first VPC-SC perimeter (`vpc_sc.tf`), the locked WORM logging bucket
   (`logging_worm.tf`) and the internal-load-balancer-only serving edge (`production_edge.tf`).
   Note that `src/code_api_migration/managed_readiness.py` lists the managed operations
   that are still placeholders and refuses API startup on a managed profile while any of them is
   bound: empty that tuple by implementing and integration-testing the adapters, do not delete it.

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. Several concerns it *touches* are
owned by sibling platform services: integrate rather than rebuild them. Here is what is actually
wired in this tree today, and what is honestly not (the authority is the R1 to R8 table in
[`COMPLIANCE.md`](../COMPLIANCE.md)):

| Concern | Owner | Wired here? |
|---|---|---|
| Human review and maker-checker console | **Hrz7** | **Yes.** `ports/review_router.py` with an adapter in every family, over the shared `review-kit`. Set `HRZ_HUMAN_REVIEW_URL`; the managed router REFUSES rather than swallowing an escalation when it is empty. |
| AI-quality and promotion gate | **Hrz4** | **Client half only.** `adapters/gcp/evaluation.py` asks the Hrz4 authority (`CODEMIGRATION_QUALITY_URL`) under bundle `code-api-migration` and refuses to run off the managed profile. You must still REGISTER that bundle and its thresholds with Hrz4, or gate mode has no authority to ask. |
| Observability, tracing and immutable audit | **Hrz5** | **Tracing half only.** `adapters/gcp/tracer.py` exports OTLP to the Hrz5 collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. The audit trail is local and tamper-evident (hash chain plus external anchor); binding it to the shared sink is still open. |
| Agent registry, identity and entitlements | **Hrz3** | **Card only.** The A2A card is served at `/.well-known/agent-card.json` and built from the same tool table the runtime binds. Registering it with Hrz3 and taking entitlements from it is yours. |
| Runtime guardrail: prompt-injection defence, output filtering | **Hrz1** | **No.** There is no `GuardrailPort` in this tree. Bind one before any untrusted text reaches a model. |
| Governed RAG knowledge base | **Hrz2** | **No, and not needed today.** There is no retrieval port; the rule packs are the grounding. A fork that grounds findings in live changelogs or API specs must integrate Hrz2 and make empty retrieval a hard error. |
| Architecture and requirements intake validation | **Rsk3** | **No.** Rule R6 is an intake action rather than a code control; record the validation reference in `COMPLIANCE.md` when the project passes. |

So the review console, the promotion authority, the shared audit sink, the registry and the
guardrail are *dependencies*, not features of this repo. Decide for each whether you integrate it
or stub it, and record the decision.

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py`, recreated the venv, `make gate` and `make docs-check` green.
- [ ] Set the region in all three places (settings, `render.tf.json`, the tfvars pair) to your in-country region.
- [ ] Wired your IdP on the deployed service and set `CODEMIGRATION_IAP_AUDIENCE`.
- [ ] Replaced the `flask` and `requests` packs with the migrations your estate actually runs.
- [ ] Owned the policy numbers (PII jurisdictions, the dual-control band, the eval thresholds) with your risk function.
- [ ] Replaced every fixture checkout under `fixtures/repos/` with your own synthetic ones.
- [ ] Rebuilt `eval/datasets/golden_cases.jsonl` for your packs.
- [ ] Reviewed the deploy posture (Dockerfile, the Terraform stack, the bind address) and emptied `managed_readiness.py` honestly.
- [ ] Wired your Hrz7 endpoint and decided which sibling systems you integrate vs stub.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
