"""Local RepoAccessPort: record a proposed PR to an in-memory log (no real repository write).

The consequential write happens against a fixture, so a test and the demo can prove two things
the review-safety story rests on: that NO write is recorded while a migration is still pending
review, and that a write IS recorded once its review is approved and the intent is submitted. A
silent no-op would let a repo ship with the consequential path unproven.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import PullRequestIntent


class LocalRepoAccess:
    """Append proposed PRs to an in-memory log for the SDK-free ``local`` profile."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._opened: list[PullRequestIntent] = []

    def open_pull_request(self, intent: PullRequestIntent) -> str:
        self._opened.append(intent)
        return f"local-pr:{intent.repo_id}:{intent.branch}:{len(self._opened)}"

    @property
    def opened(self) -> tuple[PullRequestIntent, ...]:
        """The PRs opened so far, for inspection in tests, the eval and the demo."""
        return tuple(self._opened)
