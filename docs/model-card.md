# Model card: Code and API Migration Copilot (H5)

**This system has no model in its path.** This card exists to say so precisely, and to record the
boundary a model would have to respect if one is ever added. It is not a card for a model that
exists; treating it as one would be the misreading it is written to prevent.

## There is no model bound in any profile

There is no generation, narration or LLM port in this repository. The full port set registered in
`ports/__init__.py` and bound in `config/settings.yaml` is: `audit`, `identity`, `review_router`,
`repo_scanner`, `repo_access`, `ci_status`, `tracer` and `evaluation`. None of them reaches a
model, and no `adapters/{local,gcp,onprem}/generation.py` exists in any family. The one model
identifier in the tree is `_GATED_MODEL` in `adapters/gcp/evaluation.py`: it is the label the
`model-quality-gate` promotion gate records a verdict AGAINST, not a model this service calls.

## Every consequential output is deterministic

The outputs a reviewer acts on are produced by pure stdlib engines in `domain/`, composed by
`domain/migration_service.py`:

- `ast_engine.py`: module facts parsed with the standard library `ast` module.
- `dependency_graph.py`: the import graph, its topological order, and a refusal on cycles.
- `breaking_change_engine.py`: every breaking-change finding, from falsifiable machine rules held
  as versioned YAML data in `config/packs/`.
- `plan_engine.py`: the migration plan, every FAIL finding in exactly one dependency-first step.
- `patch_engine.py`: the drafted patch, applied in memory and re-analysed, demoted to draft unless
  it applies, clears its finding and still parses.

Same checkout plus same pack yields an identical result on every run. There is therefore no
model-attributable output to characterise: no accuracy, bias, hallucination or drift profile
belongs to a component this system does not have.

## The boundary a model would have to respect

If a generation port is added later, these constraints are not negotiable, because they are what
the rest of the repo's controls assume:

- It may **narrate, classify or draft** only. It may never produce a finding, a severity band, a
  plan step or a patch. With the generation adapter stubbed, the findings, the plan and the
  severity must stay byte-identical.
- **Redaction happens before the call.** PII is masked with `pii-kit` before anything reaches the
  model, exactly as it already is before the audit write and before the review payload.
- **Every output stays cited.** A narrated claim carries the same `Citation` set as the finding it
  restates; an ungrounded draft is discarded rather than published.
- **Escalation is unchanged.** A consequential result still sets `requires_human_review` and is
  still ROUTED to `human-review-console` through `ReviewRouterPort` in the same call (rule R8).

## Controls that must exist before a model is introduced

1. A `generation` port registered in the FIVE places `CONTRIBUTING.md` names (`PORT_PROTOCOLS`,
   `config.DEFAULT_BINDINGS`, a `Container` accessor, `config/settings.yaml`, and a `PortCase` in
   `tests/contract/canonical.py`), with an adapter in all three families: `local` deterministic
   and SDK-free, `gcp` lazily imported, `onprem` refusing.
2. The exact model id and version pinned in this card, in the same commit that binds it, and kept
   in step with `_GATED_MODEL` so an `model-quality-gate` verdict cannot be inherited across a model swap.
3. A per-request token budget, a rate limit and a documented kill switch that forces
   deterministic-only operation (COMPLIANCE rows P-10 and P-11).
4. An evaluation that scores the LIVE model, not only the stub: the offline gate measures the
   deterministic engines, so a managed-profile run through the `model-quality-gate` promotion gate has to score
   the narration itself.
5. Prompt-injection screening on the input, through the `agent-guardrail-gateway` (COMPLIANCE row
   R1), failing closed to deterministic-only when the screen is unavailable.

## Status

Model-free as built. This card records a boundary, not a model, and no managed model path is
production-cleared because none exists. Revisit it in the same commit that introduces one.
