"""On-prem RepoAccessPort: fail-fast portability placeholder (the sovereign-exit proof, P-12)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import PullRequestIntent


class OnPremRepoAccess:
    """Satisfies RepoAccessPort but refuses: the client wires its own repository write path."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def open_pull_request(self, intent: PullRequestIntent) -> str:
        raise NotImplementedError(
            "on-prem repo write is a portability placeholder: bind the client's own branch/PR "
            "integration (see docs/onprem-migration.md). The consequential action still requires "
            "an approved review first (rule R8)."
        )
