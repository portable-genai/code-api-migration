"""On-prem CiStatusPort: fail-fast portability placeholder (the sovereign-exit proof, P-12)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import CiStatus


class OnPremCiStatus:
    """Satisfies CiStatusPort but refuses: the client binds its own CI status read."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def latest_status(self, repo_id: str, ref: str) -> CiStatus:
        raise NotImplementedError(
            "on-prem CI status is a portability placeholder: bind the client's own CI read "
            "(see docs/onprem-migration.md)"
        )
