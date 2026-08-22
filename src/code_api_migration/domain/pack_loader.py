"""Load and STRICTLY validate the YAML breaking-change packs under ``config/packs/``.

Packs are configuration, never code (the wave's pack convention, mirrored from the HR copilot's
entitlement packs). This loader is the boundary between the file on disk and the pure engine: it
parses the YAML, refuses any unknown field, coerces the typed fields, and hands the engine
frozen :class:`RulePack` objects. Loading is deterministic (same files -> same packs), so the
engine downstream stays replayable.

Fail closed: an unknown framework, an unknown rule kind, a missing required field for a kind, or
any stray key raises at load. A pack that does not validate never reaches the engine, so a
malformed rule cannot silently degrade into a false PASS.
"""

from __future__ import annotations

from pathlib import Path

import yaml

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

DEFAULT_PACKS_DIR = Path("config") / "packs"


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


def load_pack(path: Path) -> RulePack:
    """Load and validate one YAML pack file into a :class:`RulePack`."""
    data = _require_mapping(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, str(path))
    _reject_unknown(data, _PACK_KEYS, str(path))
    for required in _PACK_KEYS:
        if required not in data:
            raise PackError(f"{path}: pack is missing required field {required!r}")
    framework = str(data["framework"])
    source = _require_mapping(data["source"], f"{path}:source")
    _reject_unknown(source, _SOURCE_KEYS, f"{path}:source")
    raw_rules = data["rules"]
    if not isinstance(raw_rules, list) or not raw_rules:
        raise PackError(f"{path}: 'rules' must be a non-empty list")
    rules = tuple(
        _rule_from(_require_mapping(raw, f"{path}:rule[{i}]"), framework, source)
        for i, raw in enumerate(raw_rules)
    )
    ids = [rule.id for rule in rules]
    if len(set(ids)) != len(ids):
        raise PackError(f"{path}: duplicate rule ids in pack")
    return RulePack(framework=framework, version=str(data["version"]), rules=rules)


def load_packs_for(framework: str, packs_dir: Path | None = None) -> RulePack:
    """Load the single pack for a framework, refusing an unknown or missing framework."""
    root = packs_dir or DEFAULT_PACKS_DIR
    pack_path = root / framework / "pack.yaml"
    if not pack_path.is_file():
        available = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
        raise PackError(f"unknown framework {framework!r}; available packs: {available}")
    return load_pack(pack_path)


def available_frameworks(packs_dir: Path | None = None) -> tuple[str, ...]:
    """The frameworks with a pack on disk, sorted."""
    root = packs_dir or DEFAULT_PACKS_DIR
    if not root.is_dir():
        return ()
    return tuple(sorted(p.name for p in root.iterdir() if (p / "pack.yaml").is_file()))
