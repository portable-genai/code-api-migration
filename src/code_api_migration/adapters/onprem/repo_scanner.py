"""On-prem RepoScannerPort: fail-fast portability placeholder (the sovereign-exit proof, P-12)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import RepoCheckout


class OnPremRepoScanner:
    """Satisfies RepoScannerPort but refuses: the client binds its own source-control read."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def scan(self, target: str) -> RepoCheckout:
        raise NotImplementedError(
            "on-prem repo scanning is a portability placeholder: bind the client's own "
            "source-control checkout (see docs/onprem-migration.md)"
        )
