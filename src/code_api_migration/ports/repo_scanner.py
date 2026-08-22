"""RepoScannerPort: a source of a target repository checkout for the analyzer to read.

Generalises the architecture validator's ``IaCScannerPort.scan(target)`` from IaC resources to a
whole repo checkout: a target name in, a :class:`RepoCheckout` out, file-based and offline. The
managed adapter reads a cloud source repository (lazy SDK import); the local adapter reads a
bundled synthetic fixture repo; the on-prem adapter is a fail-fast portability placeholder.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import RepoCheckout


@runtime_checkable
class RepoScannerPort(Protocol):
    def scan(self, target: str) -> RepoCheckout:
        """Return the checkout named by ``target`` (a repo id), with its source and test files."""
        ...
