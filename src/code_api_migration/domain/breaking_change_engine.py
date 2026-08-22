"""The deterministic breaking-change engine: per-framework packs of falsifiable machine rules.

Pure stdlib. Each rule is one small, falsifiable comparison against the AST facts, returning one
of the four :class:`RuleStatus` values, never a probability and never a model opinion. Three
rule kinds cover the migrations this copilot plans:

* ``deprecated_call`` - a call target or import that a later framework version removed. Present
  in the checkout means FAIL; absent means NOT_APPLICABLE.
* ``signature_change`` - a call whose positional arity changed. A call site using the old arity
  is FAIL; the same target at the new arity is PASS; the target unused is NOT_APPLICABLE.
* ``semver_window`` - a package pin below the version the migration targets. Below is FAIL, at
  or above is PASS, imported-but-unpinned is NEEDS_INFO, not imported is NOT_APPLICABLE.

The engine owns every verdict. The model may later narrate a finding, but it never produces one:
with the generation adapter stubbed, the finding set is identical. Rules are DATA (the YAML packs
under ``config/packs/``); this module is the pure evaluator the loader feeds them to.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ast_engine import ParsedModule
from .kernel import Citation, Severity
from .models import Finding, RuleStatus

_KINDS = frozenset({"deprecated_call", "signature_change", "semver_window"})


@dataclass(frozen=True, slots=True)
class Rule:
    """One falsifiable breaking-change rule. Kind-specific fields are validated at load time."""

    id: str
    kind: str
    framework: str
    severity: Severity
    message: str
    source_id: str
    source_title: str
    #: ``deprecated_call`` / ``signature_change``: the dotted call target the rule watches.
    target: str = ""
    #: ``signature_change``: the positional arity that is now broken, and its replacement.
    old_arity: int = -1
    new_arity: int = -1
    #: ``semver_window``: the package and the minimum version the migration requires.
    package: str = ""
    min_version: str = ""
    #: A human-readable fix hint carried into the finding message and the plan step.
    replacement: str = ""


@dataclass(frozen=True, slots=True)
class RulePack:
    """A framework's rule set, loaded from one validated YAML pack."""

    framework: str
    version: str
    rules: tuple[Rule, ...]


def finding_id(rule_id: str, path: str, line: int) -> str:
    """A stable identifier for a finding: rule at a location. Links plan steps to findings."""
    return f"{rule_id}@{path}:{line}"


def _parse_version(raw: str) -> tuple[int, ...]:
    """Parse a dotted numeric version into a comparable tuple; non-numeric parts sort as 0."""
    parts: list[int] = []
    for chunk in raw.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def version_below(declared: str, minimum: str) -> bool:
    """True when ``declared`` is strictly below ``minimum`` under numeric dotted comparison."""
    return _parse_version(declared) < _parse_version(minimum)


def _line_of(module: ParsedModule, needle: str) -> int:
    """The 1-based source line the target first appears on, from the facts, or 1 if unknown.

    Falls back to the earliest submodule line when the target matched an import by prefix (a rule
    watching ``flask.ext`` that fired on ``flask.ext.login``).
    """
    lines = dict(module.facts.symbol_lines)
    if needle in lines:
        return lines[needle]
    prefix = f"{needle}."
    submatches = [ln for name, ln in module.facts.symbol_lines if name.startswith(prefix)]
    return min(submatches) if submatches else 1


def _evaluate_deprecated(rule: Rule, module: ParsedModule) -> RuleStatus:
    # A call target must match exactly (calls are already fully dotted). An import matches the
    # target OR a submodule of it, so a rule watching ``flask.ext`` fires on ``flask.ext.login``.
    called = rule.target in module.facts.call_targets
    imported = any(
        imp == rule.target or imp.startswith(f"{rule.target}.")
        for imp in module.facts.imported_modules
    )
    return RuleStatus.FAIL if (called or imported) else RuleStatus.NOT_APPLICABLE


def _evaluate_signature(rule: Rule, module: ParsedModule) -> RuleStatus:
    arities = [count for target, count in module.facts.call_arities if target == rule.target]
    if not arities:
        return RuleStatus.NOT_APPLICABLE
    if any(count == rule.old_arity for count in arities):
        return RuleStatus.FAIL
    if all(count == rule.new_arity for count in arities):
        return RuleStatus.PASS
    # Called, but at neither the broken nor the fixed arity: the rule cannot decide.
    return RuleStatus.NEEDS_INFO


def _evaluate_semver(rule: Rule, module: ParsedModule) -> RuleStatus:
    imports_pkg = any(
        imp == rule.package or imp.startswith(f"{rule.package}.")
        for imp in module.facts.imported_modules
    )
    if not imports_pkg:
        return RuleStatus.NOT_APPLICABLE
    declared = dict(module.facts.declared_versions).get(rule.package)
    if declared is None:
        return RuleStatus.NEEDS_INFO
    return RuleStatus.FAIL if version_below(declared, rule.min_version) else RuleStatus.PASS


_EVALUATORS = {
    "deprecated_call": _evaluate_deprecated,
    "signature_change": _evaluate_signature,
    "semver_window": _evaluate_semver,
}


def evaluate_rule(rule: Rule, module: ParsedModule) -> RuleStatus:
    """Evaluate one rule against one module. An unparseable module is NEEDS_INFO for any rule."""
    if not module.parsed:
        return RuleStatus.NEEDS_INFO
    return _EVALUATORS[rule.kind](rule, module)


def evaluate_pack(pack: RulePack, parsed: tuple[ParsedModule, ...]) -> tuple[Finding, ...]:
    """Apply every rule in a pack to every module, producing the full four-valued finding set."""
    findings: list[Finding] = []
    for module in sorted(parsed, key=lambda m: m.facts.module):
        path = f"{module.facts.module.replace('.', '/')}.py"
        for rule in pack.rules:
            status = evaluate_rule(rule, module)
            line = _line_of(module, rule.target or rule.package)
            findings.append(
                Finding(
                    rule_id=rule.id,
                    framework=rule.framework,
                    status=status,
                    severity=rule.severity,
                    path=path,
                    line=line,
                    symbol=rule.target or rule.package,
                    message=_message(rule, status, module),
                    citation=Citation(
                        source_id=rule.source_id,
                        title=rule.source_title,
                        snippet=rule.message,
                    ),
                )
            )
    return tuple(findings)


def _message(rule: Rule, status: RuleStatus, module: ParsedModule) -> str:
    base = f"[{status.value}] {rule.message}"
    if status is RuleStatus.NEEDS_INFO and not module.parsed:
        return f"{base} (module did not parse)"
    if rule.replacement and status is RuleStatus.FAIL:
        return f"{base} -> use {rule.replacement}"
    return base
