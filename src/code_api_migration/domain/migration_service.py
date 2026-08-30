"""The migration copilot orchestrator: analyse a checkout, plan, and route the consequential result.

This is the domain's front door and the one place the pure engines compose. It parses the
checkout (``ast_engine``), builds the dependency graph (``dependency_graph``), evaluates the
framework's breaking-change pack (``breaking_change_engine`` fed by ``pack_loader``), orders the
plan (``plan_engine``), then reduces the whole analysis to a :class:`MigrationResult`.

The house split is exact: every consequential number and verdict here comes from the pure
engines, never from a model. Proposing changes to a repository is consequential, so a result
carrying any FAIL finding (or a plan blocked by a dependency cycle) sets ``requires_human_review``
and never auto-executes; a clean checkout does not manufacture a review. PII is redacted BEFORE
the audit write (commit metadata such as author emails crosses this path when a changelog is
summarised), every result carries the plan's citations, and the caller routes an escalation to
Hrz7 through the review port (rule R8).
"""

from __future__ import annotations

from pii_kit import redact

from ..ports.audit import AuditSinkPort
from ..ports.observability import ObservabilityTracerPort
from .ast_engine import analyze_files
from .breaking_change_engine import evaluate_pack
from .dependency_graph import build_dependency_analysis
from .kernel import AuditEvent, Citation, Decision, Severity, utcnow
from .models import (
    Finding,
    MigrationPlan,
    MigrationResult,
    RepoCheckout,
    RuleStatus,
)
from .pack_loader import PackResolver
from .pii import PII_PATTERNS
from .plan_engine import build_plan

#: Severity rank for reducing a finding set to one band; higher is more severe.
_SEVERITY_RANK: dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}

#: How many citations to carry on the result (a reviewer traces the rest from the plan).
_MAX_CITATIONS = 8

#: One span per analysed checkout. Structural attributes only: see :meth:`MigrationService.run`.
_RUN_SPAN = "migration.run"


def analyze(checkout: RepoCheckout, *, resolve_pack: PackResolver) -> MigrationPlan:
    """Run the full pure analysis for a checkout and return its migration plan.

    Deterministic and model-free: the same checkout and pack yield an identical plan every run.
    The pack arrives through ``resolve_pack``, so this function reads no filesystem and the
    determinism above is a property of its inputs rather than of a directory it went looking at.
    """
    pack = resolve_pack(checkout.framework)
    parsed = analyze_files(checkout.files)
    dependency = build_dependency_analysis(parsed)
    findings = evaluate_pack(pack, parsed)
    return build_plan(checkout.repo_id, checkout.framework, findings, dependency)


def _overall_severity(plan: MigrationPlan) -> Severity:
    if plan.is_blocked:
        return Severity.CRITICAL
    fails = [f for f in plan.findings if f.status is RuleStatus.FAIL]
    if not fails:
        return Severity.LOW
    return max((f.severity for f in fails), key=lambda s: _SEVERITY_RANK[s])


def _result_citations(plan: MigrationPlan) -> tuple[Citation, ...]:
    seen: set[str] = set()
    out: list[Citation] = []
    for finding in plan.findings:
        if finding.status is not RuleStatus.FAIL:
            continue
        if finding.citation.source_id in seen:
            continue
        seen.add(finding.citation.source_id)
        out.append(finding.citation)
        if len(out) >= _MAX_CITATIONS:
            break
    return tuple(out)


class MigrationService:
    """Analyse a checkout into a plan and a consequential, cited, audited result."""

    def __init__(
        self,
        audit: AuditSinkPort,
        *,
        tracer: ObservabilityTracerPort,
        resolve_pack: PackResolver,
    ) -> None:
        self._audit = audit
        self._tracer = tracer
        self._resolve_pack = resolve_pack

    def plan(self, checkout: RepoCheckout) -> MigrationPlan:
        """The pure analysis, exposed for the plan/finding views without an audit write."""
        return analyze(checkout, resolve_pack=self._resolve_pack)

    def run(self, checkout: RepoCheckout, *, actor: str) -> tuple[MigrationResult, MigrationPlan]:
        """Analyse the checkout, record a redacted audit event, and build the routed result.

        The whole path runs inside one span. Its attributes are STRUCTURAL only, never the
        repository id, a source file, a changelog line or a finding: a trace backend is not
        the WORM audit trail; it has no redaction stage, a wider read audience and no
        retention rule written against a regulator's requirement, so anything content-shaped
        that reaches a span has left the boundary the ``redact`` call below exists to hold,
        and left it silently.
        """
        with self._tracer.span(_RUN_SPAN, action="run", actor=actor, framework=checkout.framework):
            return self._run(checkout, actor=actor)

    def _run(self, checkout: RepoCheckout, *, actor: str) -> tuple[MigrationResult, MigrationPlan]:
        plan = self.plan(checkout)
        fails = [f for f in plan.findings if f.status is RuleStatus.FAIL]
        needs_info = [f for f in plan.findings if f.status is RuleStatus.NEEDS_INFO]
        requires_review = bool(fails) or plan.is_blocked
        severity = _overall_severity(plan)
        decision = Decision.ESCALATED if requires_review else Decision.ALLOWED
        summary = _summary(checkout, plan, fails, needs_info)
        citations = _result_citations(plan)

        # Redact BEFORE the audit write: no author email or other identifier from a changelog or
        # commit message reaches the WORM record. The changelog is the field PII arrives on, so it
        # is folded into the redacted summary rather than written raw.
        audit_text = summary
        if checkout.changelog:
            audit_text = f"{summary} :: {checkout.changelog}"
        self._audit.record(
            AuditEvent(
                action="migration_analysis",
                actor=actor,
                decision=decision,
                severity=severity,
                redacted_summary=redact(audit_text, PII_PATTERNS),
                citations=citations,
                timestamp=utcnow(),
            )
        )

        result = MigrationResult(
            subject=checkout.repo_id,
            severity=severity,
            decision=decision,
            summary=summary,
            requires_human_review=requires_review,
            framework=checkout.framework,
            fail_count=len(fails),
            needs_info_count=len(needs_info),
            step_count=len(plan.steps),
            blocked=plan.is_blocked,
            provenance=checkout.changelog,
            citations=citations,
        )
        return result, plan


def _summary(
    checkout: RepoCheckout,
    plan: MigrationPlan,
    fails: list[Finding],
    needs_info: list[Finding],
) -> str:
    if plan.is_blocked:
        return f"{checkout.repo_id}: migration BLOCKED ({plan.blocked_reason})"
    return (
        f"{checkout.repo_id}: {checkout.framework} migration plan with {len(plan.steps)} step(s), "
        f"{len(fails)} breaking change(s), {len(needs_info)} needs-info"
    )
