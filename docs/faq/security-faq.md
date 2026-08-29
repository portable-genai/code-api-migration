# Security FAQ

For an AppSec reviewer sizing up this repo. It explains what the attack surface is, what is
deliberately out of scope (and why that is honest rather than a gap), and where the evidence
lives. Cross-references: [`COMPLIANCE.md`](../../COMPLIANCE.md),
[`../practices-audit.md`](../practices-audit.md).

## What does this system actually process?

A target repository checkout: source files and their text, the import graph they imply, and the
changelog and commit metadata that comes with them. It produces breaking-change findings, a
migration plan and drafted patches. It holds no customer records, but source control is not
PII-free either: commit metadata carries author emails and, in the fixtures, a planted national
id exists precisely so the redaction check has an independent literal to look for.

## Where does redaction happen?

Before every boundary, not once. `domain/migration_service.py` masks with the shared `pii-kit`
before the audit write; `adapters/_review_payload.py` masks again before the review payload leaves
the process, against EVERY jurisdiction's rows because the console is a shared sink; and agent
tool results are masked before they return, because a tool result becomes model context. The
jurisdictions and their ORDER are chosen in `domain/pii.py` (`SG`, `HK`, `JP`, `AU`, national
rows first and the universal email and phone rows last). `tests/unit/test_not_falsely_green.py`
proves the safety metric can actually go red.

## Can a caller spoof the actor?

No. `api/schemas.py::MigrationRequestModel` carries only `repo_id`: there is no `actor` field to
supply. The audit actor and the review maker are both the server-resolved `Principal`. Under
`local` the personas are seeded dev identities behind `X-Dev-Persona`, offline demo and test only;
under `gcp` the IAP-injected assertion is verified; under `onprem` the adapter refuses rather than
pretending.

The one adapter that declares `VERIFIED` earns it: `adapters/gcp/identity.py` calls
`id_token.verify_token` with the configured `CODEMIGRATION_IAP_AUDIENCE` (unset or emptied
REFUSES, because `audience=None` means the audience is not verified at all and would accept any
Google-signed token from any project), with IAP's own key set rather than google-auth's OAuth2
default, and it checks the issuer itself because `verify_token` does not. Caller faults answer
401; deployment faults answer 503 naming the fix. `tests/unit/test_iap_identity.py` runs in every
gate and `tests/unit/test_iap_crypto_matrix.py` runs the real verifier over locally minted
assertions in a CI job that fails if it skips.

## What stops an unauthenticated peer reaching the service?

A module-scope loopback exposure guard on the app object itself, so it also runs when the
Dockerfile `CMD` or `make run-api` serves the app object rather than calling `main()`. Its posture
is derived from the IDENTITY BINDING and from nothing else: an end-user route counts as
authenticated only when the bound adapter can produce a verified principal without trusting a
header the client wrote. `CODEMIGRATION_S2S_TOKEN` authenticates a calling SERVICE and no end
user, so it takes no part in that decision. `tests/unit/test_serving_path_exposure.py` and
`tests/unit/test_end_user_auth_posture.py` are the standing gates. Interactive docs (`/docs`,
`/redoc`, `/openapi.json`) are ABSENT outside the deliberate `local` exposure profile rather than
guarded, because a guard the profile has switched off is no guard.

## What about the consequential write path?

`RepoAccessPort` is the only port that mutates a target repository. Opening a branch or a pull
request is reserved for an approved review (rule R8), no shipped surface calls it while a result
is pending, and the managed implementation is one of the three operations listed in
`managed_readiness.py`, which refuses API startup on a managed profile while any of them is still
a placeholder. That refusal is the mechanism that stops "production ready" becoming a label.

## Are there secrets in the repo?

No secret value is committed. `config/settings.yaml` and `.env.example` carry variable NAMES and
non-secret defaults; `.env.secrets.example` carries placeholders. Inbound and outbound credentials
are deliberately distinct variables: this service's own inbound `CODEMIGRATION_S2S_TOKEN` is not
the outbound `HUMAN_REVIEW_S2S_TOKEN` it presents to the review console.

## What is the supply-chain posture?

Committed `requirements-dev.lock` and `requirements-gcp.lock`, installed with `--no-deps` by
`make install`, by CI and by the Dockerfile; the catalog commons pinned to 40-character COMMIT
shas rather than tags, because a tag can be moved and a commit cannot; a digest-pinned,
multi-stage, non-root (uid 10001) image with a `HEALTHCHECK`; SHA-pinned GitHub Actions;
dependabot per ecosystem; and `pip-audit` over both lockfiles as a hard failure
(`make audit`). `tests/unit/test_repo_artifacts.py` asserts each of these from inside the repo.

## Is the audit trail tamper-evident?

Yes, and with an honest limit named. The local trail is append-only and hash-chained, AND
externally anchored: `CODEMIGRATION_AUDIT_ANCHOR` points at a file on a different volume that
every append writes the chain head to. The chain alone catches an edit, a deletion or a reorder;
only the anchor catches a TRUNCATED TAIL, because a shorter chain still verifies perfectly. Once
store and anchor disagree the service refuses to append rather than re-anchoring, so an ordinary
write cannot launder a divergence. `tests/unit/test_audit_anchor.py` proves the detection, proves
the control case goes undetected without an anchor, and proves the refusal. The enterprise WORM
store is **Hrz5**; the in-repo chain is the offline stand-in, and the managed profile writes to a
locked Cloud Logging bucket instead (`infra/terraform/logging_worm.tf`).

## Is the domain really dependency-free?

Almost, and the exception is recorded rather than hidden. `tests/unit/test_core_purity.py` walks
the AST of the core and fails the build on any import the core does not own. It carries exactly
ONE written exemption: `domain/pack_loader.py` imports `yaml`, because the migration packs are
parsed inside the core today, with extraction to the configuration boundary queued. The exemption
is narrow (it silences that file and that import root only, and a second import in the same file
still fails), and a companion test deletes it from under you if the import ever goes away, so a
stale row cannot quietly cover the next violation. Read it as a recorded, queued item, not as an
unqualified pure-stdlib claim.

## What is explicitly out of scope for this repo?

The prompt-injection and output-filtering guardrail (**Hrz1**, not wired: there is no model
boundary to screen yet), the governed knowledge base (**Hrz2**), the agent registry (**Hrz3**,
the card is published but registration is owed), the AI-quality and promotion gate (**Hrz4**, the
client half only), the shared WORM audit and trace sink (**Hrz5**, tracing only), and the
human-review console (**Hrz7**, wired). This repo integrates those rather than re-implementing
them. See [features-faq.md](features-faq.md) for the full boundary map and
[compliance-faq.md](compliance-faq.md) for what is still owed.
