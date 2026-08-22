"""Deterministic patch application and validation: a drafted diff is proven, never trusted.

Pure stdlib. The model may draft a patch for a plan step, but a drafted patch is not a validated
one. This engine applies a unified diff to the target file IN MEMORY (a scratch copy, never the
real checkout), then re-runs the analyzer against the patched content and checks the fixture's
own expectation. A patch that does not apply cleanly, does not clear its finding, or breaks the
module is demoted to DRAFT and is never presented to a reviewer as validated.

The unified-diff applier is intentionally small and strict: it matches every context and removed
line against the original exactly, so a stale or corrupted diff FAILS to apply rather than
producing a plausible-looking wrong file. That strictness is what the patch-validity eval leans
on: a corrupted-diff fixture must go red.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ast_engine import parse_module
from .breaking_change_engine import Rule, evaluate_rule
from .models import PatchStatus, PatchValidation, RuleStatus, SourceFile


class PatchApplyError(ValueError):
    """A unified diff did not apply cleanly to the target content."""


@dataclass(frozen=True, slots=True)
class _Hunk:
    old_start: int
    lines: tuple[str, ...]


def _parse_hunks(diff: str) -> tuple[_Hunk, ...]:
    hunks: list[_Hunk] = []
    current: list[str] | None = None
    old_start = 0
    for raw in diff.splitlines():
        if raw.startswith("@@"):
            if current is not None:
                hunks.append(_Hunk(old_start=old_start, lines=tuple(current)))
            old_start = _hunk_old_start(raw)
            current = []
        elif raw.startswith(("---", "+++")):
            continue
        elif current is not None:
            current.append(raw)
    if current is not None:
        hunks.append(_Hunk(old_start=old_start, lines=tuple(current)))
    if not hunks:
        raise PatchApplyError("diff contains no @@ hunks")
    return tuple(hunks)


def _hunk_old_start(header: str) -> int:
    # Header form: @@ -old_start,old_len +new_start,new_len @@
    try:
        old_span = header.split("-", 1)[1].split(" ", 1)[0]
        return int(old_span.split(",", 1)[0])
    except (IndexError, ValueError) as exc:
        raise PatchApplyError(f"malformed hunk header {header!r}") from exc


def apply_unified_diff(original: str, diff: str) -> str:
    """Apply a unified diff to ``original`` and return the patched text, strictly.

    Context (`` `` prefix) and removed (``-``) lines must match the original exactly at the
    hunk's declared position; a mismatch raises :class:`PatchApplyError`. Added (``+``) lines are
    inserted. This is a single-file applier: the diff must target one file.
    """
    original_lines = original.splitlines()
    result: list[str] = []
    cursor = 0  # 0-based index into original_lines
    for hunk in _parse_hunks(diff):
        target = hunk.old_start - 1  # unified diff line numbers are 1-based
        if target < cursor or target > len(original_lines):
            raise PatchApplyError(f"hunk at line {hunk.old_start} is out of range or overlaps")
        result.extend(original_lines[cursor:target])
        cursor = target
        for line in hunk.lines:
            tag, text = line[:1], line[1:]
            if tag == " ":
                _expect(original_lines, cursor, text)
                result.append(text)
                cursor += 1
            elif tag == "-":
                _expect(original_lines, cursor, text)
                cursor += 1
            elif tag == "+":
                result.append(text)
            elif line == "":
                # A bare empty line in a diff body is an empty context line.
                _expect(original_lines, cursor, "")
                result.append("")
                cursor += 1
            else:
                raise PatchApplyError(f"unexpected diff line {line!r}")
    result.extend(original_lines[cursor:])
    trailing = "\n" if original.endswith("\n") else ""
    return "\n".join(result) + trailing


def _expect(lines: list[str], index: int, text: str) -> None:
    if index >= len(lines) or lines[index] != text:
        found = lines[index] if index < len(lines) else "<end of file>"
        raise PatchApplyError(
            f"context mismatch at line {index + 1}: expected {text!r}, found {found!r}"
        )


def validate_patch(
    step_order: int,
    target: SourceFile,
    diff: str,
    rule: Rule,
    *,
    expectation: str = "",
) -> PatchValidation:
    """Apply a drafted patch, then prove it clears the finding without breaking the module.

    ``expectation``, when given, is a substring the patched content MUST contain (typically the
    replacement symbol), a cheap stand-in for the fixture repo's own test asserting the migration
    landed. A validated patch applies cleanly, re-analyses to a non-FAIL status for its rule, and
    still parses with the expectation present.
    """
    try:
        patched = apply_unified_diff(target.content, diff)
    except PatchApplyError as exc:
        return PatchValidation(
            step_order=step_order,
            applies=False,
            finding_cleared=False,
            tests_green=False,
            status=PatchStatus.DRAFT,
            detail=f"patch did not apply: {exc}",
        )

    parsed = parse_module(SourceFile(path=target.path, content=patched))
    finding_cleared = parsed.parsed and evaluate_rule(rule, parsed) is not RuleStatus.FAIL
    tests_green = parsed.parsed and (expectation in patched if expectation else True)
    validated = finding_cleared and tests_green
    return PatchValidation(
        step_order=step_order,
        applies=True,
        finding_cleared=finding_cleared,
        tests_green=tests_green,
        status=PatchStatus.VALIDATED if validated else PatchStatus.DRAFT,
        detail=(
            "patch validated: applies, finding cleared, module parses"
            if validated
            else "patch applied but did not clear the finding or broke the module"
        ),
    )
