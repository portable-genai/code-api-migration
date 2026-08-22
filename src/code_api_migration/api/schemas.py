"""API request/response schemas (Pydantic) mapped to/from the pure-domain models."""

from __future__ import annotations

from pydantic import BaseModel

from ..domain.models import MigrationPlan, MigrationResult


class MigrationRequestModel(BaseModel):
    #: The target repository id the scanner resolves to a checkout (a bundled fixture under local).
    repo_id: str


class CitationModel(BaseModel):
    source_id: str
    title: str
    snippet: str = ""


class FindingModel(BaseModel):
    rule_id: str
    framework: str
    status: str
    severity: str
    path: str
    line: int
    symbol: str
    message: str


class PlanStepModel(BaseModel):
    order: int
    module: str
    title: str
    rationale: str
    finding_ids: list[str]


class MigrationResponse(BaseModel):
    subject: str
    severity: str
    decision: str
    summary: str
    requires_human_review: bool
    framework: str
    fail_count: int
    needs_info_count: int
    step_count: int
    blocked: bool
    #: Changelog/commit-metadata excerpt, returned to the authenticated caller (who is authorised
    #: to see repo metadata). The agent tool, whose output reaches a model, masks it instead.
    provenance: str = ""
    #: Where the escalation WENT (rule R8): the Hrz7 review id, or the local queue reference.
    #: Empty only when the result did not escalate. A caller can tell a routed escalation from a
    #: flag that stopped here, which is the whole point of the rule.
    review_ref: str = ""
    citations: list[CitationModel] = []
    steps: list[PlanStepModel] = []
    findings: list[FindingModel] = []

    @classmethod
    def from_domain(
        cls,
        result: MigrationResult,
        plan: MigrationPlan,
        *,
        review_ref: str = "",
    ) -> MigrationResponse:
        return cls(
            subject=result.subject,
            severity=result.severity.value,
            decision=result.decision.value,
            summary=result.summary,
            requires_human_review=result.requires_human_review,
            framework=result.framework,
            fail_count=result.fail_count,
            needs_info_count=result.needs_info_count,
            step_count=result.step_count,
            blocked=result.blocked,
            provenance=result.provenance,
            review_ref=review_ref,
            citations=[
                CitationModel(source_id=c.source_id, title=c.title, snippet=c.snippet)
                for c in result.citations
            ],
            steps=[
                PlanStepModel(
                    order=s.order,
                    module=s.module,
                    title=s.title,
                    rationale=s.rationale,
                    finding_ids=list(s.finding_ids),
                )
                for s in plan.steps
            ],
            findings=[
                FindingModel(
                    rule_id=f.rule_id,
                    framework=f.framework,
                    status=f.status.value,
                    severity=f.severity.value,
                    path=f.path,
                    line=f.line,
                    symbol=f.symbol,
                    message=f.message,
                )
                for f in plan.findings
            ],
        )


class HealthResponse(BaseModel):
    status: str
    profile: str
    region: str
