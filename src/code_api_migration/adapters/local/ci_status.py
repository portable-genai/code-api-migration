"""Local CiStatusPort: return a deterministic fixture CI status, offline.

CI reads are advisory and read-only, so the offline family answers with a canned green status for
any ref. Deterministic by construction: the same ref yields the same status every run.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import CiStatus


class LocalCiStatus:
    """A fixture CI status source for the SDK-free ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def latest_status(self, repo_id: str, ref: str) -> CiStatus:
        return CiStatus(
            repo_id=repo_id,
            ref=ref,
            state="success",
            detail="fixture CI: all checks green (synthetic)",
        )
