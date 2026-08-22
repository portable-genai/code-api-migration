"""GCP RepoAccessPort: open a branch/PR via the repo MCP/tool integration (SDK imports lazy)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import PullRequestIntent


class CloudRepoAccess:
    """Open a branch/PR on the target repository through the managed tool integration.

    Consequential and lazy-imported: the offline profiles import this module with no GCP SDK.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def open_pull_request(self, intent: PullRequestIntent) -> str:  # pragma: no cover - live GCP
        from google.cloud import source_context  # noqa: F401

        raise NotImplementedError(
            "wire the managed repo write (branch push / PR open) for the migration here"
        )
