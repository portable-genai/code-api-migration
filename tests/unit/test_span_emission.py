"""The migration path opens ONE span, and that span carries no content.

A trace backend is not the WORM audit trail. It has no redaction stage, no retention policy
written against a regulator's requirement, and a far wider read audience than the audit
store. So the value of tracing the migration path depends entirely on the span carrying
structural attributes only: which action, whose, which framework. A repository id, a source
file, a changelog line or a planted identifier reaching a span has left the boundary the
service's ``redact`` call exists to hold, and it has left it silently.

The content case drives the checkout whose changelog carries a planted NRIC, so the check
runs against input that would actually leak if any attribute were content-shaped.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from code_api_migration.config import Settings, build_container
from code_api_migration.domain.migration_service import MigrationService
from code_api_migration.domain.models import RepoCheckout
from code_api_migration.packs import pack_resolver

from tests.fixtures import sample_cases

#: Every attribute key the migration span is allowed to carry. A verdict that started
#: explaining itself on the span (a finding, a repo id, a snippet) would widen this set,
#: which is the point of asserting on the set rather than on the individual keys.
_RUN_KEYS = {"action", "actor", "framework"}


class _RecordingTracer:
    """Captures every span name and attribute so the test can inspect what was emitted."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    @contextmanager
    def span(self, name: str, **attributes: str) -> Iterator[None]:
        self.spans.append((name, dict(attributes)))
        yield

    def record_token_usage(self, usage: object, model: str) -> None:
        return None


def _run(checkout: RepoCheckout) -> _RecordingTracer:
    tracer = _RecordingTracer()
    container = build_container(Settings(profile="local", audit_path=":memory:"))
    service = MigrationService(container.audit, tracer=tracer, resolve_pack=pack_resolver())  # type: ignore[arg-type]
    service.run(checkout, actor=sample_cases.ACTOR)
    return tracer


def _emitted(tracer: _RecordingTracer) -> str:
    """Every attribute KEY and VALUE that was emitted, as one searchable blob."""
    parts: list[str] = []
    for name, attributes in tracer.spans:
        parts.append(name)
        parts.extend(attributes)
        parts.extend(attributes.values())
    return " ".join(parts)


def test_running_an_analysis_opens_exactly_one_named_span() -> None:
    tracer = _run(sample_cases.ROUTINE_CHECKOUT)
    assert [name for name, _ in tracer.spans] == ["migration.run"]


def test_the_span_carries_the_structural_attributes_an_operator_needs() -> None:
    """Enough to answer "whose analysis is slow, on which framework", and nothing more."""
    _, attributes = _run(sample_cases.ROUTINE_CHECKOUT).spans[0]
    assert attributes["action"] == "run"
    assert attributes["actor"] == sample_cases.ACTOR
    assert attributes["framework"] == sample_cases.ROUTINE_CHECKOUT.framework


@pytest.mark.parametrize(
    "checkout",
    [sample_cases.ROUTINE_CHECKOUT, sample_cases.ESCALATING_CHECKOUT],
    ids=["routine", "escalating"],
)
def test_the_attribute_set_is_a_fixed_allowlist_whatever_the_verdict(
    checkout: RepoCheckout,
) -> None:
    """An escalating checkout must not start attaching its findings, or its repo, to the span."""
    for _, attributes in _run(checkout).spans:
        assert set(attributes) == _RUN_KEYS, (
            "a new span attribute appeared; confirm it is structural, then widen "
            "_RUN_KEYS here deliberately"
        )


def test_no_span_attribute_carries_checkout_content_or_the_planted_identifier() -> None:
    """The checkout used here has an NRIC planted in its changelog, so a leak would show."""
    emitted = _emitted(_run(sample_cases.ESCALATING_CHECKOUT)).lower()
    checkout = sample_cases.ESCALATING_CHECKOUT
    forbidden = [
        sample_cases.PLANTED_NRIC,
        checkout.repo_id,
        checkout.changelog,
        "ops@gamma.example",
        *(source.content for source in checkout.files),
    ]
    for literal in forbidden:
        assert literal, "an empty needle would pass this test for the wrong reason"
        assert literal.lower() not in emitted, f"a span attribute carried {literal!r}"


def test_every_emitted_attribute_value_is_a_string_the_port_declares() -> None:
    """``span(name, **attributes: str)``: a non-string would serialise however the SDK felt."""
    tracer = _run(sample_cases.ESCALATING_CHECKOUT)
    values = [v for _, attributes in tracer.spans for v in attributes.values()]
    assert values
    assert all(isinstance(value, str) for value in values)
