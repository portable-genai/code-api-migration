"""Rule R8: a consequential result is ROUTED to Hrz7, not left in a per-repo boolean.

This is the standing gate for the failure the rule exists to prevent. A repo can set
``requires_human_review = True``, pass every other test, and still auto-execute in practice
because nothing ever reads the flag. So the assertions here are about the ROUTING, not the flag:
a proposed migration produces an outbound review, a clean repo produces none, the payload leaves
redacted, and the on-prem placeholder refuses rather than swallowing the escalation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from code_api_migration.adapters.gcp.review_router import (
    CloudReviewRouter,
)
from code_api_migration.adapters.local.review_router import (
    LocalReviewRouter,
)
from code_api_migration.adapters.onprem.review_router import (
    OnPremReviewRouter,
)
from code_api_migration.api.app import (
    app,
)
from code_api_migration.config import (
    Settings,
    build_container,
)
from code_api_migration.domain.kernel import (
    Severity,
)
from code_api_migration.domain.migration_service import (
    MigrationService,
)
from code_api_migration.domain.models import (
    MigrationResult,
    RepoCheckout,
    SourceFile,
)
from code_api_migration.packs import pack_resolver

from tests.fixtures import sample_cases


def _settings(profile: str = "local") -> Settings:
    return Settings(profile=profile, audit_path=":memory:", tenant="demo-bank")


def _run(checkout: RepoCheckout) -> MigrationResult:
    container = build_container(_settings())
    service = MigrationService(
        container.audit, tracer=container.tracer, resolve_pack=pack_resolver()
    )
    result, _plan = service.run(checkout, actor=sample_cases.ACTOR)
    return result


#: A blocked (cyclic) checkout, so the overall severity is CRITICAL and dual control applies.
_CYCLIC_CHECKOUT = RepoCheckout(
    repo_id="tangled (FICTIONAL)",
    framework="requests",
    files=(
        SourceFile(path="alpha.py", content="import beta\n"),
        SourceFile(
            path="beta.py",
            content="import alpha\nimport requests\ndef b():\n    requests.session()\n",
        ),
    ),
)


def test_a_proposed_migration_produces_an_outbound_review() -> None:
    router = LocalReviewRouter(_settings())
    ref = router.route(_run(sample_cases.ESCALATING_CHECKOUT), maker=sample_cases.ACTOR)
    assert ref, "routing must return a reference, so the caller can record where it went"
    pending = router.outbox.pending()
    assert len(pending) == 1
    review = pending[0].review
    assert review.maker == sample_cases.ACTOR
    assert review.tenant == "demo-bank"
    assert review.severity == Severity.HIGH.value
    assert review.source_key, "a durable outbox needs an idempotency key"


def test_a_blocked_migration_is_critical_and_demands_dual_control() -> None:
    router = LocalReviewRouter(_settings())
    result = _run(_CYCLIC_CHECKOUT)
    assert result.blocked is True
    assert result.severity is Severity.CRITICAL
    router.route(result, maker=sample_cases.ACTOR)
    assert router.outbox.pending()[0].review.required_approvals == 2


def test_the_payload_is_redacted_before_it_leaves_the_process() -> None:
    """Hrz7 is a shared sink; a raw identifier must never reach the wire."""
    router = LocalReviewRouter(_settings())
    router.route(sample_cases.PII_RESULT, maker=sample_cases.ACTOR)
    review = router.outbox.pending()[0].review
    wire = repr(review.to_payload())
    assert sample_cases.PLANTED_NRIC not in wire
    assert "REDACTED" in wire


def test_the_managed_router_refuses_when_no_console_is_configured() -> None:
    """An escalation with nowhere to go must fail loudly, not return as if it were reviewed."""
    router = CloudReviewRouter(Settings(profile="gcp", audit_path=":memory:", review_url=""))
    with pytest.raises(RuntimeError, match="R8"):
        router.route(sample_cases.PII_RESULT, maker=sample_cases.ACTOR)


def test_the_onprem_placeholder_refuses_rather_than_dropping_the_escalation() -> None:
    router = OnPremReviewRouter(_settings("onprem"))
    with pytest.raises(NotImplementedError, match="R8"):
        router.route(sample_cases.PII_RESULT, maker=sample_cases.ACTOR)


def test_the_api_routes_the_escalation_in_the_same_request() -> None:
    """The serving path, not just the adapter: an escalation must not depend on a later job."""
    client = TestClient(app, client=("127.0.0.1", 50000))
    escalated = client.post(
        "/v1/migrations",
        json={"repo_id": "legacy-flask-app"},
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    assert escalated["requires_human_review"] is True
    assert escalated["review_ref"], "an escalation with no routing reference went nowhere"

    routine = client.post(
        "/v1/migrations",
        json={"repo_id": "tidy-app"},
        headers={"X-Dev-Persona": "auditor"},
    ).json()
    assert routine["requires_human_review"] is False
    assert routine["review_ref"] == "", "a non-escalation must not manufacture a review"
