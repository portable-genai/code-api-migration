"""CiStatusPort: read the latest CI state for a ref on a target repo (read-only, advisory).

The migration loop reads CI to decide whether a validated patch's branch is green before it
proposes a PR. Reading is not consequential, so the local adapter returns a deterministic fixture
status; the managed adapter queries the real CI (lazy SDK import); the on-prem adapter refuses.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import CiStatus


@runtime_checkable
class CiStatusPort(Protocol):
    def latest_status(self, repo_id: str, ref: str) -> CiStatus:
        """Return the latest CI state for ``ref`` in ``repo_id``."""
        ...
