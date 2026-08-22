"""The deterministic dependency graph: intra-repo import edges, topological order, cycles.

Pure stdlib. Given the parsed modules of a checkout, it keeps only the edges BETWEEN modules
that exist in the checkout (a dependency on ``requests`` is a breaking-change concern, not a
graph node), then produces a dependency-first topological order via Kahn's algorithm. Order is
deterministic: ready nodes are always taken in sorted name order, so the same checkout yields
the same plan sequence every run.

A cycle has no safe migration order, and the engine refuses to invent one: it returns the
modules on the cycle instead of a partial order, and the plan engine turns that refusal into a
blocked plan that forces human review rather than shipping steps in an unsound sequence.
"""

from __future__ import annotations

from .ast_engine import ParsedModule
from .models import DependencyAnalysis, ImportEdge


def _internal_edges(
    parsed: tuple[ParsedModule, ...], names: frozenset[str]
) -> tuple[ImportEdge, ...]:
    """Edges from each module to the in-checkout modules it imports (deduped, sorted)."""
    edges: set[ImportEdge] = set()
    for module in parsed:
        importer = module.facts.module
        for imported in module.facts.imported_modules:
            target = _resolve(imported, names)
            if target and target != importer:
                edges.add(ImportEdge(importer=importer, imported=target))
    return tuple(sorted(edges, key=lambda e: (e.importer, e.imported)))


def _resolve(imported: str, names: frozenset[str]) -> str:
    """Map an imported name onto an in-checkout module, longest-prefix first.

    ``pkg.mod.symbol`` imported when the checkout defines ``pkg.mod`` resolves to ``pkg.mod``;
    when it defines only ``pkg`` it resolves to ``pkg``. A name matching nothing in the checkout
    is external and contributes no edge.
    """
    if imported in names:
        return imported
    parts = imported.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:cut])
        if candidate in names:
            return candidate
    return ""


def build_dependency_analysis(parsed: tuple[ParsedModule, ...]) -> DependencyAnalysis:
    """Build the module graph and its topological order (or the cycle that blocks one)."""
    modules = tuple(sorted(m.facts.module for m in parsed if m.facts.module))
    names = frozenset(modules)
    edges = _internal_edges(parsed, names)

    # Kahn's algorithm. `needs[m]` counts the modules m imports; a module is ready once every
    # module it imports has been emitted. Dependency-first: an imported module precedes its
    # importer, which is the order a migration must follow (fix the leaf before its dependents).
    needs: dict[str, set[str]] = {m: set() for m in modules}
    dependents: dict[str, set[str]] = {m: set() for m in modules}
    for edge in edges:
        needs[edge.importer].add(edge.imported)
        dependents[edge.imported].add(edge.importer)

    ready = sorted(m for m in modules if not needs[m])
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        newly_ready: list[str] = []
        for dependent in sorted(dependents[node]):
            needs[dependent].discard(node)
            if not needs[dependent]:
                newly_ready.append(dependent)
        for node_ready in newly_ready:
            _insert_sorted(ready, node_ready)

    if len(order) == len(modules):
        return DependencyAnalysis(modules=modules, edges=edges, order=tuple(order))

    # Whatever was never emitted is on (or downstream of) a cycle. Report the residual set so a
    # reviewer sees exactly which modules block a safe order.
    cycle = tuple(sorted(m for m in modules if m not in set(order)))
    return DependencyAnalysis(modules=modules, edges=edges, order=(), cycle=cycle)


def _insert_sorted(ready: list[str], value: str) -> None:
    """Keep the ready queue sorted so node selection is deterministic without a re-sort."""
    low, high = 0, len(ready)
    while low < high:
        mid = (low + high) // 2
        if ready[mid] < value:
            low = mid + 1
        else:
            high = mid
    ready.insert(low, value)
