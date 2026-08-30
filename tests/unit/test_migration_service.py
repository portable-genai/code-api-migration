"""The deterministic migration service: severity bands, soft escalation, redact-before-audit.

Mirrors the invariants the fleet asserts on every deterministic engine: the consequential
verdicts are pure and replayable, PII is masked before the audit write, and a consequential
result escalates softly rather than auto-executing.
"""

from __future__ import annotations

from code_api_migration.adapters.local.audit import (
    LocalAuditAdapter,
)
from code_api_migration.adapters.local.tracer import (
    LocalNoopTracerAdapter,
)
from code_api_migration.config import (
    Settings,
)
from code_api_migration.domain.kernel import (
    Decision,
    Severity,
)
from code_api_migration.domain.migration_service import (
    MigrationService,
)
from code_api_migration.packs import pack_resolver

from tests.fixtures import sample_cases


def _service() -> tuple[MigrationService, LocalAuditAdapter]:
    settings = Settings(profile="local", audit_path=":memory:")
    audit = LocalAuditAdapter(settings)
    return MigrationService(
        audit, tracer=LocalNoopTracerAdapter(settings), resolve_pack=pack_resolver()
    ), audit


def test_a_breaking_change_escalates_with_a_high_band() -> None:
    service, _ = _service()
    result, plan = service.run(sample_cases.ESCALATING_CHECKOUT, actor="a")
    assert result.severity is Severity.HIGH
    assert result.decision is Decision.ESCALATED
    assert result.requires_human_review is True
    assert result.fail_count >= 1
    assert plan.steps, "a proposed migration must carry ordered steps"


def test_a_clean_repo_does_not_escalate() -> None:
    service, _ = _service()
    result, plan = service.run(sample_cases.ROUTINE_CHECKOUT, actor="a")
    assert result.severity is Severity.LOW
    assert result.decision is Decision.ALLOWED
    assert result.requires_human_review is False
    assert result.fail_count == 0
    assert plan.steps == ()


def test_the_analysis_is_deterministic_and_replayable() -> None:
    service, _ = _service()
    first, _ = service.run(sample_cases.ESCALATING_CHECKOUT, actor="a")
    second, _ = service.run(sample_cases.ESCALATING_CHECKOUT, actor="a")
    assert first == second, "the same checkout must yield an identical result every run"


def test_pii_from_the_changelog_is_redacted_before_the_audit_write() -> None:
    service, audit = _service()
    service.run(sample_cases.ESCALATING_CHECKOUT, actor="engineer@bank.example")
    records = audit.log.read_all()
    assert records, "an audit event should have been recorded"
    summary = records[-1]["redacted_summary"]
    assert sample_cases.PLANTED_NRIC not in summary
    assert "REDACTED" in summary
    assert records[-1]["actor"] == "engineer@bank.example"
    assert audit.log.verify_chain().ok


def test_every_escalated_result_carries_a_citation() -> None:
    service, _ = _service()
    result, _plan = service.run(sample_cases.ESCALATING_CHECKOUT, actor="a")
    assert result.citations, "a claim with no provenance is not shippable"
