# Portability FAQ

For architecture, cloud and exit-planning reviewers who want to know how real the "no lock-in"
claim is, how an off-cloud or sovereign exit would work, and what this repo does NOT claim.
Cross-references: [`ARCHITECTURE.md`](../../ARCHITECTURE.md),
[`../onprem-migration.md`](../onprem-migration.md), [`../runbook.md`](../runbook.md).

### What is the no-lock-in claim, concretely?

`src/code_api_migration/domain/` is standard library plus the stdlib-only catalog commons:
no web framework, no cloud SDK, no HTTP client. Every boundary is a `@runtime_checkable` Protocol
in `ports/`, and which adapter implements it is a line in `config/settings.yaml` rather than a
code edit. `tests/unit/test_core_purity.py` enforces the claim by walking the core's AST rather
than by grepping, and it fails the build on any import the core does not own.

### Is the domain literally pure stdlib?

Not quite, and the exception is written down. There is exactly ONE recorded exemption:
`domain/pack_loader.py` imports `yaml` to parse the migration packs, with extraction to the
configuration boundary queued. The exemption names one file and one import root, so a second
foreign import in the same module still fails the build, and a companion test forces the row to be
DELETED once the import goes away, so it cannot silently cover the next violation. Treat this as a
recorded, queued item rather than a claim that the domain is unqualifiedly pure.

### What are the three profiles?

`CODEMIGRATION_PROFILE` selects the whole adapter stack for all eight bound ports (audit,
identity, review_router, repo_scanner, repo_access, ci_status, tracer, evaluation):

- **`local`**: a real, working, SDK-free offline stack. It ANSWERS rather than merely not raising:
  the fixture repo scanner, the hash-chained SQLite WORM audit, the seeded dev personas, the
  review outbox. This is the dev, test and CI default and the working proof that the domain runs
  entirely off-cloud.
- **`gcp`**: the managed services (Cloud Logging WORM audit, IAP identity, Cloud Trace or the `agent-observability`
  OTLP collector, the `model-quality-gate` promotion gate), each importing its SDK LAZILY inside the method so the
  other two profiles import the same module tree with no cloud SDK installed.
- **`onprem`**: fail-fast placeholders that satisfy the same Protocols and RAISE rather than
  pretending. That is the reversibility proof (P-12): a placeholder that returned successfully
  would be a false portability claim.

The profile is resolved once, at import, into a `ProfileChoice`. Unset is NO CHOICE rather than a
silent `local`; set-and-empty and set-and-unknown both raise before the process can serve.

### Is the portability claim tested, or just asserted?

Executable. `make portability` runs eight named checks and exits non-zero on any failure: port map
complete, adapters construct and conform, the offline family answers, the exit family refuses, an
in-place rewrite is detected, a truncation is detected when anchored, the record leaves this
codebase intact (a JSON Lines export reloaded by a foreign reader), and no cloud SDK was imported.
It also prints what it does NOT prove. The contract suite backs it up:
`tests/contract/test_port_parity.py` asserts set equality across all five homes of a port, and
`tests/contract/test_behavioral_parity.py` proves the offline family answers, the exit family
raises and the managed family refuses rather than silently succeeding.

### How would a sovereign or on-premises exit actually go?

The `onprem` family is the scaffold: one placeholder per port, each marking the seam where a
client supplies their own component (their source-control access, their CI system, their IdP,
their audit store, their review console). Because the domain never changes, the exit is an adapter
exercise rather than a rewrite. The audit trail exports to and restores from JSON Lines, so the
data half of the exit is a file copy. The written path is
[`../onprem-migration.md`](../onprem-migration.md).

### How is data residency handled?

At deploy time, not by documentation. The region is chosen once and carried by three files that
must agree: `config/settings.yaml` (`region: ${GCP_REGION:-asia-southeast1}`),
`infra/terraform/render.tf.json` (`local.render_region`), and the Terraform pair `var.region` and
`var.allowed_regions`, whose cross-variable validation fails at `terraform plan` if the effective
region is off the allowlist. On top of that the stack applies a `gcp.resourceLocations` Org Policy
allowlist, a REGIONAL CMEK key ring, a regional locked WORM log bucket and a dry-run-first VPC-SC
perimeter. Moving to a second in-country region is a tfvars change, not a fork. See
[compliance-faq.md](compliance-faq.md) for which of those the offline gate can and cannot guard.

### What is honestly NOT portable, or not finished?

Three things, all named in the repo rather than discovered later:

1. **Three managed operations are still placeholders**: `repo_scanner.CloudRepoScanner.scan`,
   `repo_access.CloudRepoAccess.open_pull_request` and `ci_status.CloudCiStatus.latest_status`, all
   listed in `managed_readiness.py`, which refuses API startup on a managed profile while any of
   them is bound. The offline product is complete; the managed one is not.
2. **Tamper evidence is scoped to what the local sink can prove.** `make portability` says so
   explicitly. Production tamper evidence is the managed WORM sink's job (`agent-observability`, or the locked
   Cloud Logging bucket in `infra/terraform/logging_worm.tf`).
3. **The Terraform stack is not exercised by the offline gate.** `make gate` is deliberately
   offline and credential-free, so the residency posture is reviewed by reading the stack and by
   `infra/terraform/production_edge.tftest.hcl`, which needs a `terraform test` run that no
   in-repo gate performs today.
