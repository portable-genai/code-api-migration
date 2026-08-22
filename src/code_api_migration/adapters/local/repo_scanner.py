"""Local RepoScannerPort: read a bundled synthetic fixture repository, offline and deterministic.

The fixture repos live under ``fixtures/repos/<dir>/``, each with a ``repo.yaml`` manifest naming
its ``repo_id`` and the framework pack that applies. This adapter maps a requested repo id to its
fixture directory and assembles a :class:`RepoCheckout`, so the whole analyzer, plan and demo run
with no network, no clone and no cloud SDK. Obviously synthetic code only.
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

import yaml

from ...config import Settings
from ...domain.models import RepoCheckout, SourceFile


def _find_fixtures_root() -> Path:
    """Locate ``fixtures/repos`` by walking up from this file, falling back to the cwd."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "fixtures" / "repos"
        if candidate.is_dir():
            return candidate
    return Path("fixtures") / "repos"


class LocalRepoScanner:
    """Assemble a checkout from a bundled fixture repo for the SDK-free ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @cached_property
    def _root(self) -> Path:
        return _find_fixtures_root()

    @cached_property
    def _by_id(self) -> dict[str, Path]:
        index: dict[str, Path] = {}
        if not self._root.is_dir():
            return index
        for child in sorted(self._root.iterdir()):
            manifest = child / "repo.yaml"
            if manifest.is_file():
                data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
                index[str(data.get("repo_id", child.name))] = child
        return index

    def scan(self, target: str) -> RepoCheckout:
        directory = self._by_id.get(target)
        if directory is None:
            available = sorted(self._by_id)
            raise FileNotFoundError(f"no fixture repo named {target!r}; available: {available}")
        manifest = yaml.safe_load((directory / "repo.yaml").read_text(encoding="utf-8")) or {}
        files: list[SourceFile] = []
        tests: list[SourceFile] = []
        for path in sorted(directory.rglob("*.py")):
            rel = path.relative_to(directory).as_posix()
            source = SourceFile(path=rel, content=path.read_text(encoding="utf-8"))
            (tests if _is_test(rel) else files).append(source)
        changelog_path = directory / "CHANGELOG.txt"
        changelog = changelog_path.read_text(encoding="utf-8") if changelog_path.is_file() else ""
        return RepoCheckout(
            repo_id=str(manifest.get("repo_id", target)),
            framework=str(manifest["framework"]),
            files=tuple(files),
            test_files=tuple(tests),
            changelog=changelog,
        )


def _is_test(rel: str) -> bool:
    return rel.startswith("tests/") or Path(rel).name.startswith("test_")
