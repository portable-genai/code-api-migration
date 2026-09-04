# Features FAQ

For product, engineering and delivery teams: what this agent does, what produces each output,
and, importantly, where its responsibilities **stop** and a sibling catalog system takes over.
Cross-references: [`README.md`](../../README.md), [`SPEC.md`](../../SPEC.md),
[`ARCHITECTURE.md`](../../ARCHITECTURE.md), [`DEMO.md`](../../DEMO.md).

### What does H5 actually produce?

A cited, reviewable **migration plan** for a target repository checkout. From a checkout and a
framework name it produces: the parsed module facts, a dependency graph over the checkout's own
imports, a set of **breaking-change findings** (each PASS, FAIL, NEEDS_INFO or NOT_APPLICABLE),
an ordered **migration plan** in which every FAIL finding appears in exactly one dependency-first
step, drafted **patches** validated by re-analysis, and one `MigrationResult` carrying the overall
severity band, the citations and the review reference. Every finding cites the pack rule and the
migration note it came from.

### What produces each output? Is a model involved?

No model is involved. There is **no generation, narration or LLM port in this repo** and no
generation adapter in any of the three families. Every consequential output comes from five pure
stdlib engines in `domain/`, composed by `domain/migration_service.py`:

| Engine | What it decides |
|---|---|
| `ast_engine.py` | Module facts parsed with the standard library `ast` module: imports, calls, call arity |
| `dependency_graph.py` | The intra-checkout import graph, a topological migration order, and a REFUSAL when the graph has a cycle |
| `breaking_change_engine.py` | Every finding, from the falsifiable machine rules in the YAML packs. Four-valued, so a rule that cannot decide says NEEDS_INFO rather than manufacturing a PASS |
| `plan_engine.py` | The ordered plan: each FAIL finding in exactly one step, dependency-first |
| `patch_engine.py` | The drafted diff, applied in memory and re-analysed. It stays DRAFT unless it applies cleanly, clears its finding and still parses |

Because the engines are pure and the packs are data, the same checkout and the same pack yield an
identical plan on every run. An engineer or an auditor can recompute any finding without a model.
See [`../model-card.md`](../model-card.md) for the boundary a model would have to respect if one
were ever added.

### Is anything auto-executed? Does it open pull requests by itself?

No. A result carrying any FAIL finding, or a plan blocked by a dependency cycle, sets
`requires_human_review` AND is routed to the `human-review-console` through
`ReviewRouterPort` in the same call that produced it (dependency rule R8): the flag alone is not
the escalation, and the response carries a `review_ref` so a caller can tell a routed escalation
from one that stopped locally. CRITICAL demands two approvals rather than one.

Writing back to a target repository is the one consequential mutation, and it lives behind
`RepoAccessPort` as a separate, deliberate act: no shipped surface calls `open_pull_request`
while a result is pending review, and the managed implementation is one of the three placeholders
that `managed_readiness.py` refuses to serve until it is implemented and integration-tested.

### What data does it touch, and what is redacted?

Source files, their imports and call sites, plus changelog text and the commit metadata that
comes with it. Author emails and similar identifiers cross that path, so PII is masked with the
shared `pii-kit` **before** the audit write and **before** any review payload leaves the process.
See [security-faq.md](security-faq.md) for the exact ordering.

### Which capabilities does this repo own vs integrate from the catalog?

This is one system in a catalog of composable GRC systems. It **owns** the migration analysis and
its outputs. It **integrates** the cross-cutting concerns below rather than rebuilding them, and
the honest state of each integration is:

| Concern | Owner | State in this repo |
|---|---|---|
| Human review and maker-checker console | `human-review-console` | Wired. An adapter in every profile over the shared `review-kit`; the managed router refuses rather than swallowing an escalation with no console configured |
| AI-quality, eval and promotion gate | `model-quality-gate` | Client half wired (`eval/run_eval.py --mode gate`, bundle `code-api-migration`). Registering the bundle and its thresholds with `model-quality-gate` is still owed |
| Observability, tracing, immutable audit, FinOps | `agent-observability` | Tracing half wired (OTLP to the `agent-observability` collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is set). The audit trail is local and tamper-evident; binding it to the shared sink is still owed |
| Agent registry, versioning, entitlements | `agent-registry` | The A2A card is served at `/.well-known/agent-card.json`, built from the same tool table the runtime binds. Registering it with `agent-registry` is still owed |
| Runtime guardrail: prompt-injection defence, output filtering | `agent-guardrail-gateway` | Not wired. There is no guardrail port, because there is no model boundary to screen yet |
| Governed RAG knowledge base with citations | `enterprise-knowledge-base` | Not used. The rule packs are the grounding; a fork that grounds findings in live changelogs or vendor API specs must integrate `enterprise-knowledge-base` |
| Architecture and requirements intake validation | `architecture-validator` | Not a code control. Rule R6 is an intake action; the validation reference is recorded in `COMPLIANCE.md` when the project passes |

So the review console, the promotion authority, the shared audit sink, the registry and the
guardrail are *dependencies*, not features of this repo. The authority for each row is the R1 to
R8 table in [`COMPLIANCE.md`](../../COMPLIANCE.md).

### How many ways can the same capability be reached?

Five, and they behave the same because they share the domain service rather than reimplementing
it: the FastAPI app (`POST /v1/migrations`), the argparse CLI (`code_api_migration analyze
<repo>`), the agent tools advertised on the A2A card, the embeddable micro-frontend in `ui/`, and
the eval harness. Each routes an escalated result to human review in the same call that produced
it, so rule R8 does not hold on four surfaces out of five. Agent tool results are additionally
masked for personal data before they return, because a tool result becomes model context.

### How do I see it working?

`make demo` runs the presenter-paced walkthrough: it starts a loopback server, narrates each of
the eight steps on the terminal, performs it against the REAL services, and then asserts the
service actually reached the state the narration claimed. `make demo-selftest` is the same arc
headless and unattended, `make demo-static` writes the audit-first HTML for screenshots, and
`make portability` runs the executable portability claim. Everything runs offline on synthetic,
obviously fictional fixtures with no cloud and no API key.
