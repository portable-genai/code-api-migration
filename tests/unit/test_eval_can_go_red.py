"""Every eval metric must be able to go RED, or it is not a metric.

A metric that cannot fail proves nothing on the day the engine regresses. Each scorer below is
shown red on a deliberately broken input and green on a correct one, using the shared
``assert_can_go_red`` harness. ``pii_safety`` is proved the same way in
``tests/unit/test_not_falsely_green.py``.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from agent_eval_kit import assert_can_go_red

from code_api_migration.domain.migration_service import analyze
from code_api_migration.domain.models import MigrationPlan, RuleStatus
from code_api_migration.domain.plan_engine import plan_is_complete
from code_api_migration.packs import pack_resolver

from tests.unit.test_engines import load_checkout

_PACKS = Path("config") / "packs"


def _detection_score(found: frozenset[str]) -> float:
    """1.0 iff the detected FAIL rule set equals the independently expected set."""
    expected = frozenset(
        {"FLASK-DEP-EXT-IMPORT", "FLASK-SEMVER", "FLASK-SIG-RUN", "FLASK-DEP-JSONIFY"}
    )
    return 1.0 if found == expected else 0.0


def test_detection_accuracy_can_go_red() -> None:
    plan = analyze(load_checkout("legacy_flask_app"), resolve_pack=pack_resolver(_PACKS))
    found = frozenset(f.rule_id for f in plan.findings if f.status is RuleStatus.FAIL)
    missed = frozenset(list(found)[:-1])  # the mutant: one seeded breakage goes undetected
    assert_can_go_red(
        _detection_score,
        green=found,
        red=missed,
        threshold=0.80,
        metric="detection_accuracy",
    )


def _completeness_score(plan: MigrationPlan) -> float:
    return 1.0 if plan_is_complete(plan) else 0.0


def test_plan_completeness_can_go_red() -> None:
    plan = analyze(load_checkout("legacy_flask_app"), resolve_pack=pack_resolver(_PACKS))
    # The mutant: a plan that dropped one of its steps, so a FAIL finding lands in no step.
    dropped = dataclasses.replace(plan, steps=plan.steps[:-1])
    assert_can_go_red(
        _completeness_score,
        green=plan,
        red=dropped,
        threshold=1.0,
        metric="plan_completeness",
    )
