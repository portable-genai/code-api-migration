#!/usr/bin/env python3
"""Evaluation gate for Code and API Migration Copilot (H5).

Two named layers via ``--mode`` (the scaffold is ``agent_eval_kit.eval_main``):

* **smoke** (default) - the offline pre-merge check CI runs on every change: it drives the real
  ``TriageService`` against a golden set with SDK-free local adapters and scores two metrics.
* **gate** - the promotion verdict from the shared Hrz4 authority (requires the ``gcp``
  profile), via ``agent_eval_kit.PromotionGateClient``.

Exit is ``0`` iff every metric meets its threshold (and, in gate mode, the authority agrees).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent_eval_kit import EvalMetricResult, EvalReport, PromotionGateClient, eval_main
from pii_kit import pack_leak

from code_api_migration.adapters.local.audit import (
    LocalAuditAdapter,
)
from code_api_migration.adapters.local.tracer import (
    LocalNoopTracerAdapter,
)
from code_api_migration.config import (
    Settings,
)
from code_api_migration.domain.migration_service import (
    MigrationService,
)
from code_api_migration.domain.models import (
    RepoCheckout,
    RuleStatus,
    SourceFile,
)
from code_api_migration.domain.pii import (
    PII_PATTERNS,
)
from code_api_migration.domain.plan_engine import (
    plan_is_complete,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"
_PACKS_DIR = _REPO_ROOT / "config" / "packs"

THRESHOLDS: dict[str, float] = {
    "detection_accuracy": 0.80,
    "plan_completeness": 1.0,
    "pii_safety": 0.99,
}
#: The registered Hrz4 metric bundle for this vertical (Hrz4 owns the metrics + thresholds).
_BUNDLE = "code-api-migration"


def _load(path: Path) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    if not cases:
        raise SystemExit(f"{path}: golden dataset is empty")
    return cases


def _mean(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _checkout(case: dict[str, Any]) -> RepoCheckout:
    files = tuple(
        SourceFile(path=path, content=content)
        for path, content in sorted(case.get("files", {}).items())
    )
    return RepoCheckout(
        repo_id=case["repo_id"],
        framework=case["framework"],
        files=files,
        changelog=case.get("changelog", ""),
    )


def run_smoke(dataset: Path) -> EvalReport:
    cases = _load(dataset)
    settings = Settings(profile="local", audit_path=":memory:")
    audit = LocalAuditAdapter(settings)
    tracer = LocalNoopTracerAdapter(settings)
    service = MigrationService(audit, tracer=tracer, packs_dir=_PACKS_DIR)

    detection_scores: list[float] = []
    completeness_scores: list[float] = []
    for case in cases:
        _result, plan = service.run(_checkout(case), actor="eval-bot")
        # detection_accuracy scores the engine's FAIL rule set against the dataset's OWN
        # independently hand-derived expected set (the oracle), never against the pipeline's own
        # verdict. A rule that fires where it should not, or misses a seeded breakage, is caught.
        found = {f.rule_id for f in plan.findings if f.status is RuleStatus.FAIL}
        expected = set(case.get("expected_fail_rules", []))
        detection_scores.append(1.0 if found == expected else 0.0)
        # plan_completeness: every FAIL finding lands in exactly one step (or the plan is blocked
        # and the dataset expects it). Both are scored against the dataset, not the engine.
        if case.get("expected_blocked"):
            completeness_scores.append(1.0 if plan.is_blocked else 0.0)
        else:
            completeness_scores.append(1.0 if plan_is_complete(plan) else 0.0)

    # pii_safety: no raw identifier may survive into any audit record. The pack scan uses the
    # same rows the redactor masks with; the planted-literal check is an independent oracle that
    # fires even if a row is broken (the two-part scorer lesson from the C4 rollout).
    records = [str(e.get("redacted_summary", "")) for e in audit.log.read_all()]
    planted = [case["planted"] for case in cases if case.get("planted")]
    pack_leaked = any(pack_leak(text, PII_PATTERNS) for text in records)
    literal_leaked = any(token in text for token in planted for text in records)
    pii_safety = 0.0 if (pack_leaked or literal_leaked) else 1.0

    results = (
        EvalMetricResult.scored(
            "detection_accuracy", _mean(detection_scores), THRESHOLDS["detection_accuracy"]
        ),
        EvalMetricResult.scored(
            "plan_completeness", _mean(completeness_scores), THRESHOLDS["plan_completeness"]
        ),
        EvalMetricResult.scored("pii_safety", pii_safety, THRESHOLDS["pii_safety"]),
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(cases))


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    settings = Settings.load()
    if settings.profile != "gcp":
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            f"CODEMIGRATION_PROFILE=gcp (got {settings.profile!r}); "
            "run --mode smoke for the offline pre-merge check."
        )
    client = PromotionGateClient(
        os.environ.get("CODEMIGRATION_QUALITY_URL", "http://localhost:8084"),
        bundle=_BUNDLE,
        model="gemini-3.5-flash",
    )
    return client.evaluate(str(dataset)), client.gate(str(dataset))


if __name__ == "__main__":
    raise SystemExit(
        eval_main(
            smoke=run_smoke,
            gate=run_gate,
            default_dataset=DEFAULT_DATASET,
            description="Offline / Hrz4 evaluation gate for H5.",
        )
    )
