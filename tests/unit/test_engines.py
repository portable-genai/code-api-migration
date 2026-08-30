"""The pure engines: AST facts, dependency topology, breaking-change rules, plan, patches.

These are the consequential core. Every test here runs with no adapter, no model and no network,
because the whole point of the split is that the numbers come from stdlib code that is trivially
replayable. Each rule kind is shown able to reach each of its verdicts, so a rule that could only
ever say one thing (a metric that cannot go red) is caught here rather than in production.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_api_migration.domain.ast_engine import (
    ParsedModule,
    analyze_files,
    module_name,
    parse_module,
)
from code_api_migration.domain.breaking_change_engine import (
    Rule,
    evaluate_rule,
    version_below,
)
from code_api_migration.domain.dependency_graph import (
    build_dependency_analysis,
)
from code_api_migration.domain.kernel import Severity
from code_api_migration.domain.migration_service import analyze
from code_api_migration.domain.models import RepoCheckout, RuleStatus, SourceFile
from code_api_migration.domain.pack_loader import PackError
from code_api_migration.domain.patch_engine import (
    PatchApplyError,
    apply_unified_diff,
    validate_patch,
)
from code_api_migration.domain.plan_engine import plan_is_complete
from code_api_migration.packs import available_frameworks, load_packs_for, pack_resolver

_PACKS = Path("config") / "packs"


# --------------------------------------------------------------------------- #
# AST engine
# --------------------------------------------------------------------------- #
def test_module_name_collapses_init_and_strips_suffix() -> None:
    assert module_name("pkg/mod.py") == "pkg.mod"
    assert module_name("pkg/__init__.py") == "pkg"


def test_ast_facts_capture_imports_calls_arities_and_versions() -> None:
    source = SourceFile(
        path="app.py",
        content=(
            "import flask\n"
            "from a.b import c\n"
            "__requires__ = {'flask': '1.1'}\n"
            "def go():\n"
            "    app.run('h', 8080)\n"
        ),
    )
    facts = parse_module(source).facts
    assert "flask" in facts.imported_modules
    assert "a.b" in facts.imported_modules
    assert "app.run" in facts.call_targets
    assert ("app.run", 2) in facts.call_arities
    assert ("flask", "1.1") in facts.declared_versions


def test_an_unparseable_module_is_flagged_not_guessed() -> None:
    parsed = parse_module(SourceFile(path="broken.py", content="def (:\n"))
    assert parsed.parsed is False
    assert parsed.error


# --------------------------------------------------------------------------- #
# Dependency graph
# --------------------------------------------------------------------------- #
def test_topological_order_is_dependency_first_and_deterministic() -> None:
    files = (
        SourceFile(path="app.py", content="import util\n"),
        SourceFile(path="views.py", content="import app\n"),
        SourceFile(path="util.py", content="x = 1\n"),
    )
    analysis = build_dependency_analysis(analyze_files(files))
    assert analysis.is_cyclic is False
    assert analysis.order.index("util") < analysis.order.index("app")
    assert analysis.order.index("app") < analysis.order.index("views")


def test_a_cycle_is_reported_rather_than_ordered() -> None:
    files = (
        SourceFile(path="alpha.py", content="import beta\n"),
        SourceFile(path="beta.py", content="import alpha\n"),
    )
    analysis = build_dependency_analysis(analyze_files(files))
    assert analysis.is_cyclic is True
    assert set(analysis.cycle) == {"alpha", "beta"}
    assert analysis.order == ()


# --------------------------------------------------------------------------- #
# Breaking-change rules: each verdict is reachable (each rule can go red)
# --------------------------------------------------------------------------- #
def _module(content: str) -> ParsedModule:
    return parse_module(SourceFile(path="m.py", content=content))


def test_deprecated_call_rule_reaches_fail_and_not_applicable() -> None:
    rule = Rule(
        id="R",
        kind="deprecated_call",
        framework="f",
        severity=Severity.MEDIUM,
        message="m",
        source_id="s",
        source_title="t",
        target="flask.json.jsonify",
    )
    assert evaluate_rule(rule, _module("import flask\nflask.json.jsonify({})\n")) is RuleStatus.FAIL
    assert evaluate_rule(rule, _module("x = 1\n")) is RuleStatus.NOT_APPLICABLE


def test_signature_change_rule_separates_broken_fixed_and_ambiguous() -> None:
    rule = Rule(
        id="R",
        kind="signature_change",
        framework="f",
        severity=Severity.HIGH,
        message="m",
        source_id="s",
        source_title="t",
        target="app.run",
        old_arity=2,
        new_arity=0,
    )
    assert evaluate_rule(rule, _module("app.run('h', 80)\n")) is RuleStatus.FAIL
    assert evaluate_rule(rule, _module("app.run()\n")) is RuleStatus.PASS
    assert evaluate_rule(rule, _module("app.run('h')\n")) is RuleStatus.NEEDS_INFO
    assert evaluate_rule(rule, _module("x = 1\n")) is RuleStatus.NOT_APPLICABLE


def test_semver_rule_reaches_all_four_verdicts() -> None:
    rule = Rule(
        id="R",
        kind="semver_window",
        framework="f",
        severity=Severity.HIGH,
        message="m",
        source_id="s",
        source_title="t",
        package="flask",
        min_version="2.0",
    )
    assert evaluate_rule(rule, _module("import flask\n__requires__={'flask':'1.1'}\n")) is (
        RuleStatus.FAIL
    )
    assert evaluate_rule(rule, _module("import flask\n__requires__={'flask':'2.3'}\n")) is (
        RuleStatus.PASS
    )
    assert evaluate_rule(rule, _module("import flask\n")) is RuleStatus.NEEDS_INFO
    assert evaluate_rule(rule, _module("x = 1\n")) is RuleStatus.NOT_APPLICABLE


def test_version_below_is_numeric_not_lexical() -> None:
    assert version_below("1.9", "1.10") is True
    assert version_below("2.0", "2.0") is False


# --------------------------------------------------------------------------- #
# Pack loader
# --------------------------------------------------------------------------- #
def test_the_shipped_packs_load_and_are_discoverable() -> None:
    assert set(available_frameworks(_PACKS)) >= {"flask", "requests"}
    pack = load_packs_for("flask", _PACKS)
    assert pack.rules and all(rule.framework == "flask" for rule in pack.rules)


def test_an_unknown_framework_is_refused() -> None:
    with pytest.raises(PackError, match="unknown framework"):
        load_packs_for("cobol", _PACKS)


# --------------------------------------------------------------------------- #
# Plan engine
# --------------------------------------------------------------------------- #
def test_every_fail_finding_lands_in_exactly_one_step() -> None:
    checkout = load_checkout("legacy_flask_app")
    plan = analyze(checkout, resolve_pack=pack_resolver(_PACKS))
    assert plan.is_blocked is False
    assert plan_is_complete(plan) is True


def test_a_cyclic_repo_blocks_the_plan_rather_than_ordering_it() -> None:
    checkout = load_checkout("tangled_service")
    plan = analyze(checkout, resolve_pack=pack_resolver(_PACKS))
    assert plan.is_blocked is True
    assert plan.steps == ()


# --------------------------------------------------------------------------- #
# Patch engine
# --------------------------------------------------------------------------- #
def test_a_clean_diff_applies_and_a_corrupted_one_is_refused() -> None:
    original = "a\nb\nc\n"
    good = "@@ -2,1 +2,1 @@\n-b\n+B\n"
    assert apply_unified_diff(original, good) == "a\nB\nc\n"

    corrupt = "@@ -2,1 +2,1 @@\n-NOT_B\n+B\n"
    with pytest.raises(PatchApplyError):
        apply_unified_diff(original, corrupt)


def test_validate_patch_marks_a_cleared_finding_validated_and_a_bad_diff_draft() -> None:
    rule = Rule(
        id="R",
        kind="deprecated_call",
        framework="f",
        severity=Severity.MEDIUM,
        message="m",
        source_id="s",
        source_title="t",
        target="flask.json.jsonify",
    )
    target = SourceFile(path="v.py", content="import flask\nflask.json.jsonify({})\n")
    good = "@@ -2,1 +2,1 @@\n-flask.json.jsonify({})\n+flask.jsonify({})\n"
    ok = validate_patch(1, target, good, rule, expectation="flask.jsonify")
    assert ok.status.value == "validated"
    assert ok.finding_cleared is True

    bad = "@@ -2,1 +2,1 @@\n-NOPE\n+flask.jsonify({})\n"
    draft = validate_patch(1, target, bad, rule)
    assert draft.status.value == "draft"
    assert draft.applies is False


# --------------------------------------------------------------------------- #
# Shared fixture-repo loader for the plan tests
# --------------------------------------------------------------------------- #
def load_checkout(name: str) -> RepoCheckout:
    from code_api_migration.adapters.local.repo_scanner import LocalRepoScanner
    from code_api_migration.config import Settings

    scanner = LocalRepoScanner(Settings(profile="local"))
    manifest = {"legacy_flask_app": "legacy-flask-app", "tangled_service": "tangled-service"}
    return scanner.scan(manifest[name])
