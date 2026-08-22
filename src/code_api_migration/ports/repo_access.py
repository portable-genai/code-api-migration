"""RepoAccessPort: the CONSEQUENTIAL write boundary (open a branch / PR on a target repo).

This is the one port that mutates a target repository, so it is the port rule R8 protects: a
migration's proposed changes are pushed ONLY after its review is approved. The service never
calls :meth:`open_pull_request` for a result still pending review, and the review-safety tests
assert exactly that (a consequential fixture push yields zero adapter writes while unapproved).

The local adapter records the write to an in-memory log so a test and the demo can prove a write
DID happen once approved, and prove none happened while pending. The managed adapter performs a
real MCP/tool call (lazy SDK import); the on-prem adapter refuses.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import PullRequestIntent


@runtime_checkable
class RepoAccessPort(Protocol):
    def open_pull_request(self, intent: PullRequestIntent) -> str:
        """Open a branch/PR carrying the migration and return its reference. Consequential."""
        ...
