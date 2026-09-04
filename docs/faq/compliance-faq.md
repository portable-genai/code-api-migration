# Compliance FAQ

For compliance, model-risk and second-line teams assessing this repo's posture. The authority is
[`COMPLIANCE.md`](../../COMPLIANCE.md), which maps every catalog principle (P-01 to P-13) and
every platform dependency rule (R1 to R8) to a control and an evidence file, and marks the rows
this repo still OWES. This FAQ summarises; on any conflict the mapping table wins.

### Is this system deciding anything autonomously?

No. It is decision support. A result carrying any FAIL finding, or a plan blocked by a dependency
cycle, sets `requires_human_review` AND is routed to the `human-review-console` through
`ReviewRouterPort` in the same call that produced it (rule R8). The flag alone is not the
escalation, and the managed router REFUSES rather than swallowing an escalation when no console is
configured. CRITICAL demands two approvals rather than one. Writing back to a repository is a
separate, consequential act behind `RepoAccessPort`, reserved for an approved review.

### How is the consequential decision explainable?

It is deterministic. The severity band, every finding and every plan step come from pure stdlib
engines (`ast_engine`, `dependency_graph`, `breaking_change_engine`, `plan_engine`,
`patch_engine`), and the rules those engines evaluate are versioned YAML data in `config/packs/`,
not code. Same checkout plus same pack yields an identical plan, so a reviewer can recompute any
finding. Every finding and every result carries a `Citation` naming the pack rule and its source
note. There is no model in the path at all today: see [`../model-card.md`](../model-card.md),
which records the boundary rather than a model.

### How is personal data handled?

Source control is not PII-free: changelogs and commit metadata carry author emails and similar
identifiers. Redaction therefore happens BEFORE the audit write and again BEFORE any review
payload leaves the process, using the shared `pii-kit` with the jurisdiction selection and
ordering this deployment owns in `domain/pii.py` (`SG`, `HK`, `JP`, `AU`, national rows first).
The eval gate scores `pii_safety >= 0.99` two independent ways, and
`tests/unit/test_not_falsely_green.py` proves that metric can go red. The enterprise redaction and
injection-defence gateway is the sibling `agent-guardrail-gateway` system, which this repo does NOT yet bind
(COMPLIANCE row R1): bind it before any untrusted text reaches a model.

### How is the work auditable?

Every analysis writes an already-redacted, immutable `AuditEvent` naming the verified actor, the
decision, the severity and the citations. The local trail is append-only, hash-chained and
externally ANCHORED, so a truncated tail is detectable rather than invisible; once store and
anchor disagree the service refuses to append rather than re-anchoring. The managed profile writes
to a locked, CMEK-encrypted, regional Cloud Logging bucket
(`infra/terraform/logging_worm.tf`). The enterprise WORM and trace sink is `agent-observability`; binding this
repo's audit half to it is still owed (COMPLIANCE row R2), though the tracer already exports OTLP
to the `agent-observability` collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.

### What is the model-risk story when there is no model?

`eval/run_eval.py --mode smoke` runs in the offline gate on every change and scores three metrics
against a golden set: `detection_accuracy >= 0.80`, `plan_completeness == 1.0` and
`pii_safety >= 0.99`. It exercises the real `MigrationService` with SDK-free adapters, so it
measures the shipped engines. `--mode gate` delegates the promotion verdict to the `model-quality-gate`
AI-quality authority under the bundle `code-api-migration` and refuses to run off the
managed profile, because a promotion certified by a laptop is certified by nothing. Registering
that bundle and its thresholds WITH `model-quality-gate` is still owed (COMPLIANCE rows P-08 and R5). Because no
model produces any output today, there is no model card to file yet, only a boundary: see
[`../model-card.md`](../model-card.md).

### Is data residency enforced, or only documented?

Enforced at deploy time, with one honest caveat. `infra/terraform/` applies a
`gcp.resourceLocations` Org Policy allowlist pinned to the selected region's location group, a
REGIONAL CMEK key ring with 90-day rotation and per-service-agent bindings (encryption does not
cascade), a locked regional WORM log bucket, a dry-run-first VPC-SC perimeter, and a serving edge
that rejects direct public Cloud Run ingress. `var.region` is validated against
`var.allowed_regions` at plan time, so an off-list region fails before anything is created. The
caveat: `make gate` is deliberately offline, so it does not run Terraform.
`infra/terraform/production_edge.tftest.hcl` asserts the residency and lock defaults, but nothing
in the offline gate executes it, which is why the residency rows in `COMPLIANCE.md` read
**Partial** rather than Covered.

### What is still owed?

Read the status column in [`COMPLIANCE.md`](../../COMPLIANCE.md) rather than assuming. As it
stands the repo owes, among others: grounding through `enterprise-knowledge-base` if retrieval is ever added (P-05),
timeouts, a circuit breaker and documented CPS 230 recovery objectives (P-10), cost and latency
controls once a model exists (P-11), the `agent-guardrail-gateway` binding (R1), the `agent-observability`
binding (R2), `agent-registry` registration (R4), `model-quality-gate` bundle registration (R5), the `architecture-validator` intake
reference (R6), and object-level authorisation once this service gains a queryable store.
[`../practices-audit.md`](../practices-audit.md) records the per-check verdicts, including the
open B4 item (lift the dual-control threshold into a `policy:` block).

### Which regulators does this map to?

None, directly, and deliberately. `COMPLIANCE.md` maps to the CATALOG's own principles and rules
and is explicit that the crosswalk from those to MAS TRM, CPS 234, CPS 230, HKMA or PDPA control
ids, and the judgement that a control is SUFFICIENT for a regulation, is **adopter-owned**. It
depends on the institution's risk appetite, regulator, licence conditions and existing control
library. No row in that file should be quoted as regulatory assurance, and an adopter is expected
to add the risk acceptance for every Partial or TODO row at go-live, plus a second-line review of
the deterministic policy in `domain/`, which is bank-owned logic rather than a vendor default.

### Can we run it against real repositories today?

Not without your own security and model-risk sign-off. Every fixture is obviously synthetic, the
shipped rule packs cite fictional migration notes, and three managed operations are still
placeholders that `managed_readiness.py` refuses to serve. The adoption checklist in
[`../ADOPTING.md`](../ADOPTING.md) lists what must precede any live use: replace the packs and
fixtures, own the policy numbers, wire your IdP, rebuild the eval golden set, and set your
residency region.
