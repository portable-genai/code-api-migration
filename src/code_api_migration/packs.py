"""The config boundary for breaking-change packs: the only place a pack file is parsed.

A pack is the framework's published policy, so validating one is domain logic and lives in
:mod:`code_api_migration.domain.pack_loader`. What lives HERE is the half that touches the world
outside the hexagon: where packs sit on disk, which frameworks have one, reading those bytes,
and turning YAML into a plain Python mapping.

The core asks for a pack through a
:data:`~code_api_migration.domain.pack_loader.PackResolver` rather than through a directory, so
a caller whose packs live in a config map, a database or a test fixture satisfies the same
contract with no filesystem in sight. :func:`pack_resolver` is the on-disk implementation of it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .domain.breaking_change_engine import RulePack
from .domain.pack_loader import PackError, PackResolver, build_pack

__all__ = [
    "DEFAULT_PACKS_DIR",
    "available_frameworks",
    "load_pack",
    "load_packs_for",
    "pack_resolver",
    "read_pack_document",
]

#: The default location packs are read from, relative to the process working directory (the repo
#: root under ``make`` targets and ``/app`` in the image). Overridable by passing an explicit
#: path; never read from the environment here, so the caller owns any override.
DEFAULT_PACKS_DIR = Path("config") / "packs"


def read_pack_document(path: Path) -> Any:
    """Parse one pack file into a plain Python object, validating nothing."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_pack(path: Path) -> RulePack:
    """Read and validate one YAML pack file into a :class:`RulePack`."""
    return build_pack(read_pack_document(path), str(path))


def load_packs_for(framework: str, packs_dir: Path | None = None) -> RulePack:
    """Load the single pack for a framework, refusing an unknown or missing framework.

    The refusal names what IS available, because "unknown framework" without the list is a dead
    end for whoever typed the name.
    """
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


def pack_resolver(packs_dir: Path | None = None) -> PackResolver:
    """The on-disk resolver the surfaces hand the core: framework name in, validated pack out."""

    def resolve(framework: str) -> RulePack:
        return load_packs_for(framework, packs_dir)

    return resolve
