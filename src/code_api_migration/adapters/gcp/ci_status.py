"""GCP CiStatusPort: read the latest CI state from Cloud Build (SDK imports stay lazy)."""

from __future__ import annotations

from ...config import Settings
from ...domain.models import CiStatus


class CloudCiStatus:
    """Query the managed CI for the latest state of a ref.

    The ``google.cloud`` import lives inside the method so the offline profiles import this module
    with no GCP SDK installed.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def latest_status(self, repo_id: str, ref: str) -> CiStatus:  # pragma: no cover - live GCP
        from google.cloud.devtools import cloudbuild_v1  # noqa: F401

        raise NotImplementedError("wire the managed CI status read here")
