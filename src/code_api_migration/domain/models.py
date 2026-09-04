"""Vertical artifact models: the migration copilot's own request and result types.

The artifacts THIS vertical produces, as opposed to the vertical-neutral machinery in
``kernel.py``. The service's own name is deliberately not substituted into this docstring: a
rendered line whose length depends on ``friendly_name`` fails the repo's own format check for
no reason but the length of its name.

Everything here is a frozen, slotted dataclass or a ``StrEnum`` whose member IS its wire value,
so the whole analysis is hashable, comparable and replayable. The consequential objects are the
:class:`Finding` set, the :class:`MigrationPlan` and the :class:`MigrationResult` that routes to
human-review-console; the model never constructs any of them, it only narrates them.

A fork building a different vertical rewrites this module and keeps ``kernel.py`` untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hex_service_kit.enums import LenientStrEnum

from .kernel import Citation, Decision, Severity


class RuleStatus(LenientStrEnum):
    """The four-valued verdict a single breaking-change machine rule returns.

    The set is cribbed from the architecture validator's principle evaluation, because a
    migration rule needs the same honesty: a rule that cannot say NEEDS_INFO turns every gap in
    the checkout into a false PASS, and a rule that cannot say NOT_APPLICABLE fires on
    frameworks it was never written for.
    """

    PASS = "pass"  # the rule is satisfied by the target as it stands
    FAIL = "fail"  # a hard, unambiguous breaking change the migration must resolve
    NEEDS_INFO = "needs_info"  # the checkout omits what the rule needs to decide
    NOT_APPLICABLE = "not_applicable"  # the rule does not bind this target


class PatchStatus(LenientStrEnum):
    """The disposition of a drafted patch after the analyzer re-runs against it."""

    VALIDATED = "validated"  # applies cleanly, clears its finding, fixture tests still green
    DRAFT = "draft"  # anything less; never presented to a reviewer as validated


@dataclass(frozen=True, slots=True)
class SourceFile:
    """One file in the target repository checkout: a path and its full text."""

    path: str
    content: str


@dataclass(frozen=True, slots=True)
class RepoCheckout:
    """A synthetic, offline snapshot of a target repository the analyzer runs over.

    ``repo_id`` is the subject the whole analysis is attributed to (and the review case ref).
    ``framework`` names the migration pack set to apply. ``files`` is the ordered file set; the
    analyzer sorts by path internally so the result never depends on iteration order.
    """

    repo_id: str
    framework: str
    files: tuple[SourceFile, ...] = ()
    #: The fixture repo's own test files, kept separate so patch validation can re-run them.
    test_files: tuple[SourceFile, ...] = ()
    #: Recent commit / changelog text. This is the field author names and emails arrive on, so it
    #: is the PII path the redactor guards before any audit write or model hand-off.
    changelog: str = ""


@dataclass(frozen=True, slots=True)
class ImportEdge:
    """One intra-repo module dependency: ``importer`` imports ``imported``."""

    importer: str
    imported: str


@dataclass(frozen=True, slots=True)
class ModuleFacts:
    """The pure AST facts one module contributes: imports, calls, and callable signatures.

    Deliberately small and stringly-typed: it is the boundary between the ``ast`` walk (which
    knows Python syntax) and the breaking-change rules (which know a framework's API surface),
    and everything a rule needs to fire is a name or a count, never a live AST node.
    """

    module: str
    imported_modules: tuple[str, ...] = ()
    #: Dotted attribute call targets, e.g. ``requests.get`` or ``db.session.query``.
    call_targets: tuple[str, ...] = ()
    #: Callable name -> the positional argument count declared at its call sites.
    call_arities: tuple[tuple[str, int], ...] = ()
    #: Version pins this module declares (from a ``__requires__`` / ``REQUIREMENTS`` mapping).
    declared_versions: tuple[tuple[str, str], ...] = ()
    #: Dotted name (call target or import) -> the first 1-based source line it appears on, so a
    #: finding can cite a real location rather than the top of the file.
    symbol_lines: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class Finding:
    """One breaking-change finding: a rule verdict located in the checkout, with a citation.

    A finding is consequential only when ``status`` is FAIL; the plan engine orders exactly the
    FAIL findings into steps. ``rule_id`` and ``framework`` name the pack rule that fired, and
    ``severity`` maps the finding onto the shared kernel band so the migration's overall risk
    (and the dual-control threshold) is computed from data, not guessed.
    """

    rule_id: str
    framework: str
    status: RuleStatus
    severity: Severity
    path: str
    line: int
    symbol: str
    message: str
    citation: Citation


@dataclass(frozen=True, slots=True)
class DependencyAnalysis:
    """The module dependency graph plus its topological order (or the cycle that blocks one)."""

    modules: tuple[str, ...]
    edges: tuple[ImportEdge, ...]
    #: A dependency-first order (a module appears after everything it imports). Empty on a cycle.
    order: tuple[str, ...]
    #: The modules on a detected import cycle, sorted; empty when the graph is acyclic.
    cycle: tuple[str, ...] = ()

    @property
    def is_cyclic(self) -> bool:
        return bool(self.cycle)


@dataclass(frozen=True, slots=True)
class PlanStep:
    """One ordered step of a migration plan, each citing the findings it resolves."""

    order: int
    module: str
    title: str
    rationale: str
    finding_ids: tuple[str, ...]
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """The ordered, cited plan: every FAIL finding lands in exactly one step, or refusal.

    ``blocked_reason`` is non-empty precisely when the dependency graph is cyclic and no safe
    order exists; a blocked plan carries no steps and forces human review. ``findings`` is the
    full four-valued finding set (not only the FAILs), so the audit view can show what passed
    and what needs info alongside what must change.
    """

    repo_id: str
    framework: str
    steps: tuple[PlanStep, ...]
    findings: tuple[Finding, ...]
    dependency: DependencyAnalysis
    blocked_reason: str = ""

    @property
    def is_blocked(self) -> bool:
        return bool(self.blocked_reason)


@dataclass(frozen=True, slots=True)
class PatchValidation:
    """The disposition of one drafted patch after deterministic re-analysis."""

    step_order: int
    applies: bool
    finding_cleared: bool
    tests_green: bool
    status: PatchStatus
    detail: str


@dataclass(frozen=True, slots=True)
class MigrationRequest:
    """One migration analysis request: which checkout, and who asked."""

    repo_id: str
    framework: str


@dataclass(frozen=True, slots=True)
class CiStatus:
    """The latest CI state for a ref in a target repo, as reported through the CI status port."""

    repo_id: str
    ref: str
    state: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class PullRequestIntent:
    """A consequential write to a target repo: open a branch/PR carrying the migration.

    Constructed by the caller ONLY after the migration's review is approved. It is deliberately a
    request object, not a set of loose arguments, so the review-safety tests can assert that no
    such intent reaches the repo-access adapter while the result is still pending review.
    """

    repo_id: str
    branch: str
    title: str
    body: str
    review_ref: str = ""


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """The consequential result routed to human-review-console (rule R8) when a migration is
    proposed.

    It carries the same contract every routed result in this fleet does (``subject``,
    ``severity``, ``decision``, ``summary``, ``requires_human_review``, ``citations``) so the
    review router, the API and the CLI treat it uniformly, plus the migration-specific counts a
    reviewer needs at a glance. Proposing changes to a repository is always consequential, so a
    result with any FAIL finding sets ``requires_human_review`` and never auto-executes.
    """

    subject: str
    severity: Severity
    decision: Decision
    summary: str
    requires_human_review: bool
    framework: str
    fail_count: int
    needs_info_count: int
    step_count: int
    blocked: bool
    #: A short changelog/commit-metadata excerpt for context. It may carry author names or emails,
    #: so every surface that hands it onward (the audit sink, the agent tool) redacts it first.
    provenance: str = ""
    citations: tuple[Citation, ...] = field(default=())
