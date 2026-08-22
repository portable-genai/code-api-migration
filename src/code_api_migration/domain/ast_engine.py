"""The deterministic AST analyzer: pure stdlib ``ast``, no framework, no cloud, no model.

This is the first half of the migration copilot's consequential engine. It walks each Python
source file in a checkout and reduces it to :class:`ModuleFacts`: the modules it imports, the
dotted call targets it invokes, the positional arity at each call site, and any version pins it
declares. Everything downstream (the breaking-change rules, the dependency graph, the plan)
reads these facts, never a live AST node, so a rule is a small data comparison and the whole
analysis is replayable: the same checkout yields byte-identical facts every run.

A file that does not parse is not guessed at. It becomes a NEEDS_INFO signal carried on
:class:`ModuleFacts` via an empty fact set plus a recorded syntax error, so the breaking-change
engine can raise NEEDS_INFO rather than silently passing an unparseable module.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from .models import ModuleFacts, SourceFile


@dataclass(frozen=True, slots=True)
class ParsedModule:
    """A module's facts plus whether it parsed. An unparseable module has empty facts."""

    facts: ModuleFacts
    parsed: bool
    error: str = ""


def module_name(path: str) -> str:
    """Derive a dotted module name from a repo-relative path (``a/b/c.py`` -> ``a.b.c``).

    ``__init__.py`` collapses to its package, matching how the import system names it, so an
    edge to ``pkg`` and an edge to ``pkg/__init__.py`` are the same node in the graph.
    """
    trimmed = path[:-3] if path.endswith(".py") else path
    parts = [p for p in trimmed.split("/") if p]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _dotted(node: ast.expr) -> str:
    """Render an attribute/name chain (``a.b.c``) as a dotted string, or ``""`` if it is neither."""
    parts: list[str] = []
    current: ast.expr | None = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        parts.reverse()
        return ".".join(parts)
    return ""


class _FactVisitor(ast.NodeVisitor):
    """Collect imports, call targets, call arities and declared versions from one module."""

    def __init__(self) -> None:
        self.imports: list[str] = []
        self.calls: list[str] = []
        self.arities: list[tuple[str, int]] = []
        self.versions: list[tuple[str, str]] = []
        self.lines: dict[str, int] = {}

    def _mark(self, name: str, lineno: int) -> None:
        """Record the FIRST line a dotted name appears on, so citations are stable."""
        if name and name not in self.lines:
            self.lines[name] = lineno

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)
            self._mark(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # A relative import (level > 0) has no module of its own worth an edge here; an absolute
        # one contributes its module. Imported names are appended so a `from x import y` used as
        # a bare call still resolves to a target the rules can match.
        if node.module and node.level == 0:
            self.imports.append(node.module)
            self._mark(node.module, node.lineno)
            for alias in node.names:
                qualified = f"{node.module}.{alias.name}"
                self.imports.append(qualified)
                self._mark(qualified, node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        target = _dotted(node.func)
        if target:
            self.calls.append(target)
            self.arities.append((target, len(node.args)))
            self._mark(target, node.lineno)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # A module-level `__requires__ = {"flask": "1.1"}` or `REQUIREMENTS = {...}` declares the
        # version window the semver rules read. Only string->string dict literals are honoured;
        # anything dynamic is ignored rather than guessed.
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in {"__requires__", "REQUIREMENTS"}:
                self._collect_versions(node.value)
        self.generic_visit(node)

    def _collect_versions(self, value: ast.expr) -> None:
        if not isinstance(value, ast.Dict):
            return
        for key, val in zip(value.keys, value.values, strict=True):
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and isinstance(val, ast.Constant)
                and isinstance(val.value, str)
            ):
                self.versions.append((key.value, val.value))


def parse_module(source: SourceFile) -> ParsedModule:
    """Reduce one source file to :class:`ModuleFacts`, or record why it did not parse."""
    name = module_name(source.path)
    try:
        tree = ast.parse(source.content, filename=source.path)
    except SyntaxError as exc:
        return ParsedModule(
            facts=ModuleFacts(module=name),
            parsed=False,
            error=f"{source.path}: {exc.msg} (line {exc.lineno})",
        )
    visitor = _FactVisitor()
    visitor.visit(tree)
    facts = ModuleFacts(
        module=name,
        imported_modules=tuple(dict.fromkeys(visitor.imports)),
        call_targets=tuple(dict.fromkeys(visitor.calls)),
        call_arities=tuple(visitor.arities),
        declared_versions=tuple(visitor.versions),
        symbol_lines=tuple(sorted(visitor.lines.items())),
    )
    return ParsedModule(facts=facts, parsed=True)


def analyze_files(files: tuple[SourceFile, ...]) -> tuple[ParsedModule, ...]:
    """Parse every Python file in a checkout, in a stable path order."""
    ordered = sorted((f for f in files if f.path.endswith(".py")), key=lambda f: f.path)
    return tuple(parse_module(f) for f in ordered)
