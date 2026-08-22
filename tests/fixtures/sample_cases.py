"""Canonical synthetic checkouts and results, shared by the unit and contract suites.

Every repository, party and identifier is obviously fictional. One canonical escalating checkout
(it carries a real Flask breaking change, so a migration is proposed and rule R8 applies) and one
routine checkout (already clean, so a router that manufactured a review here would be lying) are
enough for the contract suite: parity means the SAME request through every implementation, so the
request has one home rather than being retyped per test.
"""

from __future__ import annotations

from code_api_migration.domain.kernel import (
    Citation,
    Decision,
    Severity,
)
from code_api_migration.domain.models import (
    MigrationResult,
    RepoCheckout,
    SourceFile,
)

#: The verified principal the tests attribute work to (never a client-asserted actor).
ACTOR = "engineer@bank.example"

#: A tenant partition, so the outbound-review assertions are not all on the empty string.
TENANT = "demo-bank"

#: The bundled fixture repo the scanner/demo load (see ``fixtures/repos/legacy_flask_app``).
ESCALATING_REPO_ID = "legacy-flask-app"

#: A planted identifier, so a redaction assertion has an independent literal to look for rather
#: than trusting the pattern pack to agree with itself.
PLANTED_NRIC = "S1234567D"

#: A checkout that MUST escalate: ``app.run`` is called with the removed positional signature, so
#: the deterministic engine raises a FAIL finding and a migration is proposed.
ESCALATING_CHECKOUT = RepoCheckout(
    repo_id="acme-legacy (FICTIONAL)",
    framework="flask",
    files=(
        SourceFile(
            path="app.py",
            content=(
                "import flask\n"
                "app = flask.Flask(__name__)\n"
                "def start():\n"
                '    app.run("0.0.0.0", 8080)\n'
            ),
        ),
    ),
    # The changelog is the PII path: an author email and a synthetic NRIC that must be redacted
    # before the audit write and before the agent hands the result to a model.
    changelog=f"authored by ops@gamma.example, NRIC {PLANTED_NRIC} in the release note",
)

#: A checkout that must NOT escalate: no framework coupling, so every rule is not-applicable.
ROUTINE_CHECKOUT = RepoCheckout(
    repo_id="beta-tidy (FICTIONAL)",
    framework="flask",
    files=(SourceFile(path="calc.py", content="def add(a, b):\n    return a + b\n"),),
)

#: A result whose narrative carries personal data, for the redact-before-anything proofs. Commit
#: metadata (author email) and an id string reach the summary when a changelog is summarised; the
#: payload converter must scrub both before anything leaves the process.
PII_RESULT = MigrationResult(
    subject="Gamma LLP (FICTIONAL)",
    severity=Severity.HIGH,
    decision=Decision.ESCALATED,
    summary=f"migration authored by ops@gamma.example, NRIC {PLANTED_NRIC} in a changelog note",
    requires_human_review=True,
    framework="flask",
    fail_count=1,
    needs_info_count=0,
    step_count=1,
    blocked=False,
    citations=(
        Citation(
            source_id="flask-2x-migration-notes",
            title="Flask 2.x migration notes (synthetic)",
            snippet=f"reported by ops@gamma.example, NRIC {PLANTED_NRIC}",
        ),
    ),
)
