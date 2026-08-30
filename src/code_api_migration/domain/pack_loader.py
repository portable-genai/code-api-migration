"""STRICTLY validate breaking-change pack documents into frozen :class:`RulePack` objects.

Packs are configuration, never code (the wave's pack convention, mirrored from the HR copilot's
entitlement packs). Validation is the policy half and lives here: it refuses any unknown field,
coerces the typed fields, and hands the engine frozen :class:`RulePack` objects. The other half,
finding a pack file and parsing its YAML, is I/O and lives at the config boundary in
:mod:`code_api_migration.packs`; this module is handed a document that is already a plain
mapping. Validation is deterministic (same document -> same pack), so the engine downstream
stays replayable.

Fail closed: an unknown framework, an unknown rule kind, a missing required field for a kind, or
any stray key raises at load. A pack that does not validate never reaches the engine, so a
malformed rule cannot silently degrade into a false PASS.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .breaking_change_engine import Rule, RulePack
from .kernel import Severity

_PACK_KEYS = frozenset({"framework", "version", "source", "rules"})
_SOURCE_KEYS = frozenset({"id", "title"})
_COMMON_RULE_KEYS = frozenset({"id", "kind", "severity", "message", "replacement"})
_KIND_KEYS: dict[str, frozenset[str]] = {
    "deprecated_call": frozenset({"target"}),
    "signature_change": frozenset({"target", "old_arity", "new_arity"}),
    "semver_window": frozenset({"package", "min_version"}),
}

#: How the core asks for a pack. The boundary supplies one; the core never goes looking.
#: Taking a resolver rather than a directory is what keeps every filesystem fact outside the
#: hexagon : a caller with packs in a config map, a database or a fixture satisfies this too.
PackResolver = Callable[[str], RulePack]


class PackError(ValueError):
    """A pack failed strict validation. The message names the pack and the offending field."""


def _require_mapping(node: object, where: str) -> dict[str, object]:
    if not isinstance(node, dict):
        raise PackError(f"{where}: expected a mapping, got {type(node).__name__}")
    return {str(k): v for k, v in node.items()}


def _reject_unknown(data: dict[str, object], allowed: frozenset[str], where: str) -> None:
    extra = set(data) - allowed
    if extra:
        raise PackError(f"{where}: unknown field(s) {sorted(extra)}; packs refuse stray keys")


def _rule_from(raw: dict[str, object], framework: str, source: dict[str, object]) -> Rule:
    kind = str(raw.get("kind", ""))
    if kind not in _KIND_KEYS:
        raise PackError(f"{framework}: rule {raw.get('id')!r} has unknown kind {kind!r}")
    allowed = _COMMON_RULE_KEYS | _KIND_KEYS[kind]
    _reject_unknown(raw, allowed, f"{framework} rule {raw.get('id')!r}")
    for required in ("id", "severity", "message"):
        if required not in raw:
            raise PackError(f"{framework}: rule is missing required field {required!r}")
    for required in _KIND_KEYS[kind]:
        if required not in raw:
            raise PackError(f"{framework}: {kind} rule {raw['id']!r} needs {required!r}")
    return Rule(
        id=str(raw["id"]),
        kind=kind,
        framework=framework,
        severity=Severity(str(raw["severity"])),
        message=str(raw["message"]),
        source_id=str(source["id"]),
        source_title=str(source["title"]),
        target=str(raw.get("target", "")),
        old_arity=int(str(raw["old_arity"])) if "old_arity" in raw else -1,
        new_arity=int(str(raw["new_arity"])) if "new_arity" in raw else -1,
        package=str(raw.get("package", "")),
        min_version=str(raw.get("min_version", "")),
        replacement=str(raw.get("replacement", "")),
    )


def build_pack(document: Any, source: str) -> RulePack:
    """Validate one already-parsed pack document into a :class:`RulePack`.

    ``source`` names where the document came from, so every refusal below points somewhere a
    reader can open. An empty document is treated as an empty mapping and then refused by the
    required-field check, rather than being special-cased into a different message.
    """
    data = _require_mapping(document or {}, source)
    _reject_unknown(data, _PACK_KEYS, source)
    for required in _PACK_KEYS:
        if required not in data:
            raise PackError(f"{source}: pack is missing required field {required!r}")
    framework = str(data["framework"])
    # ``source`` is where the DOCUMENT came from; ``source_block`` is the citation the pack
    # declares inside itself. Two different things that were one name while the location was
    # always a path, and are told apart now that the location is a caller-supplied string.
    source_block = _require_mapping(data["source"], f"{source}:source")
    _reject_unknown(source_block, _SOURCE_KEYS, f"{source}:source")
    raw_rules = data["rules"]
    if not isinstance(raw_rules, list) or not raw_rules:
        raise PackError(f"{source}: 'rules' must be a non-empty list")
    rules = tuple(
        _rule_from(_require_mapping(raw, f"{source}:rule[{i}]"), framework, source_block)
        for i, raw in enumerate(raw_rules)
    )
    ids = [rule.id for rule in rules]
    if len(set(ids)) != len(ids):
        raise PackError(f"{source}: duplicate rule ids in pack")
    return RulePack(framework=framework, version=str(data["version"]), rules=rules)
