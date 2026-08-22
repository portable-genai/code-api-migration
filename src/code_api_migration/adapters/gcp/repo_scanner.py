"""GCP RepoScannerPort: read a Cloud Source Repository checkout (SDK imports stay lazy)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import RepoCheckout


class CloudRepoScanner:
    """Fetch a target repo checkout from a managed source repository.

    The ``google.cloud`` import lives inside the method so the offline profiles import this module
    with no GCP SDK installed (the portability proof).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def scan(self, target: str) -> RepoCheckout:  # pragma: no cover - needs live GCP
        from google.cloud import source_context  # noqa: F401

        raise NotImplementedError(
            "wire the managed source-repository fetch for the target checkout here"
        )
