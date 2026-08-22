"""The deterministic migration plan engine: order steps from the dependency topology.

Pure stdlib. The engine, not the model, owns ordering, scope and completion criteria. Given the
four-valued finding set and the dependency analysis, it:

* refuses when the graph is cyclic (no sound order exists) and returns a blocked plan that forces
  human review, rather than inventing a sequence;
* otherwise emits one step per module that carries at least one FAIL finding, in dependency-first
  order (a module is migrated only after everything it imports), so a fix never lands before the
  code it depends on;
* guarantees every FAIL finding lands in EXACTLY ONE step (the plan-completeness invariant the
  eval scores and asserts can go red), by grouping FAILs by their finding's module.

The model may later draft the prose of a step from File Search over changelogs; it never decides
which findings a step contains or what order the steps run in.
"""

from __future__ import annotations

from .breaking_change_engine import finding_id
from .kernel import Citation
from .models import (
    DependencyAnalysis,
    Finding,
    MigrationPlan,
    PlanStep,
    RuleStatus,
)


def _module_of(finding: Finding) -> str:
    """The dotted module a finding sits in, derived from its file path."""
    trimmed = finding.path[:-3] if finding.path.endswith(".py") else finding.path
    return trimmed.replace("/", ".")


def build_plan(
    repo_id: str,
    framework: str,
    findings: tuple[Finding, ...],
    dependency: DependencyAnalysis,
) -> MigrationPlan:
    """Order the FAIL findings into cited steps, or return a blocked plan on a dependency cycle."""
    if dependency.is_cyclic:
        return MigrationPlan(
            repo_id=repo_id,
            framework=framework,
            steps=(),
            findings=findings,
            dependency=dependency,
            blocked_reason=(
                "dependency cycle among "
                f"{list(dependency.cycle)}: no sound migration order exists, so the plan is "
                "blocked pending human review"
            ),
        )

    fails = [f for f in findings if f.status is RuleStatus.FAIL]
    by_module: dict[str, list[Finding]] = {}
    for finding in fails:
        by_module.setdefault(_module_of(finding), []).append(finding)

    # Dependency-first order; any module with FAILs but not in the order (should not happen for an
    # acyclic graph, but a module with no edges still appears) is appended in name order.
    ordered_modules = [m for m in dependency.order if m in by_module]
    ordered_modules += sorted(m for m in by_module if m not in dependency.order)

    steps: list[PlanStep] = []
    for index, module in enumerate(ordered_modules, start=1):
        module_fails = sorted(by_module[module], key=lambda f: (f.path, f.line, f.rule_id))
        steps.append(
            PlanStep(
                order=index,
                module=module,
                title=f"Migrate {module} ({len(module_fails)} breaking change(s))",
                rationale=_rationale(module, module_fails),
                finding_ids=tuple(finding_id_of(f) for f in module_fails),
                citations=tuple(_dedupe_citations(module_fails)),
            )
        )

    return MigrationPlan(
        repo_id=repo_id,
        framework=framework,
        steps=tuple(steps),
        findings=findings,
        dependency=dependency,
    )


def finding_id_of(finding: Finding) -> str:
    """The stable id used to link a plan step back to the finding it resolves."""
    return finding_id(finding.rule_id, finding.path, finding.line)


def _rationale(module: str, fails: list[Finding]) -> str:
    rule_ids = ", ".join(sorted({f.rule_id for f in fails}))
    return f"Resolve {len(fails)} breaking change(s) in {module}: {rule_ids}."


def _dedupe_citations(fails: list[Finding]) -> list[Citation]:
    seen: set[str] = set()
    out: list[Citation] = []
    for finding in fails:
        if finding.citation.source_id in seen:
            continue
        seen.add(finding.citation.source_id)
        out.append(finding.citation)
    return out


def plan_is_complete(plan: MigrationPlan) -> bool:
    """Every FAIL finding lands in exactly one step (the completeness invariant)."""
    fail_ids = [finding_id_of(f) for f in plan.findings if f.status is RuleStatus.FAIL]
    placed = [fid for step in plan.steps for fid in step.finding_ids]
    return sorted(fail_ids) == sorted(placed) and len(placed) == len(set(placed))
