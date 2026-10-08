"""Atlas Evolution — ONE bounded repository context builder (Command 2, W2).

Before this module, two authoring seams built repository context for a model
independently: :mod:`~atlas.evolution.model_assisted_supplier` (a
lexically-ranked module list with bounded source excerpts) and
:mod:`~atlas.evolution.development_repair` (the specialist author's own private
``_build_context``). Two algorithms means two behaviours and two chances to
disagree about what the repository says.

This module is the single, reusable, deterministic context-construction
authority over the EXISTING :class:`~atlas.research.repository_map.RepositoryMap`.
It adds no repository source of its own, no retrieval framework, no embeddings
and no I/O: every region, symbol, dependency, dependent and test it reports is
data the map already holds.

Selection order (fixed, auditable, never re-ordered per request)
---------------------------------------------------------------
1. the DECLARED target's symbol region (the ``SymbolRegion`` the map stored);
2. its unambiguous callers/callees (structural neighbours);
3. dependency-aware neighbours (the target module's resolved internal imports
   and its reverse-import dependents);
4. the repository-derived tests for the target module;
5. the EXISTING lexical module ranking — used ONLY when the declared target
   cannot be resolved, never to override a target that was declared.

Everything must fit inside one hard character budget, and every inclusion
carries a bounded rationale naming the evidence it came from. Unknown input
fails closed to an empty, unresolved context.

Read-only. Deterministic. Bounded. No model. No I/O. Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Default character budget for the SELECTED SOURCE a context may carry.
DEFAULT_CONTEXT_CHARS: int = 16000
#: Hard ceiling on a caller-declared budget (boundedness is not negotiable).
MAX_CONTEXT_CHARS_LIMIT: int = 200_000
#: Bounded collections (deterministic caps, never per-request).
MAX_CONTEXT_REGIONS: int = 6
MAX_CONTEXT_SYMBOLS: int = 24
MAX_CONTEXT_NEIGHBOURS: int = 12
MAX_CONTEXT_TESTS: int = 8
MAX_CONTEXT_DEPENDENCIES: int = 12
MAX_CONTEXT_REASONS: int = 12
MAX_REASON_CHARS: int = 200


@dataclass(frozen=True, slots=True)
class RepositoryContextRequest:
    """A bounded, read-only request for repository context.

    ``module`` is the DECLARED target (dotted module or repository path);
    ``symbol`` optionally narrows it to one qualified symbol; ``query`` carries
    the request's own words and is used ONLY by the fallback ranking step.
    """

    module: str = ""
    symbol: str = ""
    query: str = ""
    max_chars: int = DEFAULT_CONTEXT_CHARS


@dataclass(frozen=True, slots=True)
class RepositoryContext:
    """The bounded result: evidence only, never an instruction."""

    module: str = ""
    regions: tuple[Any, ...] = ()
    symbols: tuple[Any, ...] = ()
    tests: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    dependents: tuple[str, ...] = ()
    rationale: tuple[str, ...] = ()
    source: str = ""
    truncated: bool = False
    #: True when ``module`` names a resolved target (declared or ranked).
    resolved: bool = False
    #: True when the module list came from the lexical FALLBACK ranking.
    fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "regions": [str(getattr(r, "qualified", "") or "") for r in self.regions],
            "symbols": [str(getattr(s, "qualified", "") or "") for s in self.symbols],
            "tests": list(self.tests),
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
            "rationale": list(self.rationale),
            "truncated": self.truncated,
            "resolved": self.resolved,
            "fallback": self.fallback,
        }


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalise_module(target: Any) -> str:
    """Normalize a target (dotted module or repository path) to a dotted module."""
    value = _text(target).replace("\\", "/")
    if value.endswith(".py"):
        value = value[:-3]
    return value.strip(".").replace("/", ".")


def _bounded_strs(values: Any, limit: int) -> tuple[str, ...]:
    out: list[str] = []
    for value in values or ():
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return tuple(out)


def _module_index(repository_map: Any) -> dict[str, Any]:
    index: dict[str, Any] = {}
    for info in getattr(repository_map, "modules", ()) or ():
        name = str(getattr(info, "module", "") or "")
        if name:
            index[name] = info
    return index


def _call(repository_map: Any, name: str, *args: Any) -> Any:
    """Call an optional map query, returning ``None`` on any failure."""
    method = getattr(repository_map, name, None)
    if not callable(method):
        return None
    try:
        return method(*args)
    except Exception:  # noqa: BLE001 — a broken query is absent evidence
        return None


def _resolve_symbol(repository_map: Any, symbol: str) -> Any | None:
    if not symbol:
        return None
    found = _call(repository_map, "find_symbol", symbol, 1)
    try:
        items = tuple(found or ())
    except TypeError:
        return None
    return items[0] if items else None


def build_repository_context(
    repository_map: Any, request: RepositoryContextRequest
) -> RepositoryContext:
    """Build the bounded repository context for ``request`` (pure, deterministic).

    Never raises: an absent, hostile or unqueryable map yields an empty,
    unresolved context, which callers must treat as "no evidence available".
    """
    if not isinstance(request, RepositoryContextRequest):
        request = RepositoryContextRequest()

    budget = request.max_chars
    if not isinstance(budget, int) or budget <= 0:
        budget = DEFAULT_CONTEXT_CHARS
    budget = min(budget, MAX_CONTEXT_CHARS_LIMIT)

    if repository_map is None:
        return RepositoryContext(rationale=("no repository map is available",))

    reasons: list[str] = []
    requested = normalise_module(request.module)
    index = _module_index(repository_map)

    # -- 1/2. the declared target's region + structural neighbours ------------
    regions: list[Any] = []
    symbols: list[Any] = []
    module = requested if requested in index else ""

    symbol_entry = _resolve_symbol(repository_map, _text(request.symbol))
    if symbol_entry is not None:
        module = str(getattr(symbol_entry, "module", "") or module)
        reasons.append(f"target symbol {request.symbol!r} resolved in the repository map")
    elif requested:
        reasons.append(f"declared target module {requested!r}")

    if symbol_entry is not None:
        region = _call(repository_map, "region_of", getattr(symbol_entry, "qualified", ""))
        if region is not None:
            regions.append(region)
            reasons.append(
                "target symbol region selected first "
                f"(lines {getattr(region, 'start_line', 0)}-"
                f"{getattr(region, 'end_line', 0)})"
            )
        for neighbour in _bounded_strs(
            _call(repository_map, "callers_of", getattr(symbol_entry, "qualified", "")),
            MAX_CONTEXT_NEIGHBOURS,
        ):
            entry = _resolve_symbol(repository_map, neighbour)
            if entry is not None:
                symbols.append(entry)
        for neighbour in _bounded_strs(
            _call(repository_map, "callees_of", getattr(symbol_entry, "qualified", "")),
            MAX_CONTEXT_NEIGHBOURS,
        ):
            entry = _resolve_symbol(repository_map, neighbour)
            if entry is not None:
                symbols.append(entry)
        if symbols:
            reasons.append(
                f"{len(symbols)} unambiguous structural neighbour(s) "
                "(callers/callees) added"
            )
    elif module:
        for region in tuple(_call(repository_map, "regions_for", (module,), MAX_CONTEXT_REGIONS) or ()):
            regions.append(region)
        if regions:
            reasons.append(
                f"{len(regions)} bounded symbol region(s) selected for {module!r}"
            )

    # -- 3. dependency-aware neighbours ---------------------------------------
    dependencies: tuple[str, ...] = ()
    dependents: tuple[str, ...] = ()
    if module:
        info = index.get(module)
        if info is not None:
            dependencies = _bounded_strs(
                getattr(info, "internal_imports", ()) or (), MAX_CONTEXT_DEPENDENCIES
            )
            if dependencies:
                reasons.append(
                    f"{len(dependencies)} resolved internal dependency/ies reported"
                )
        direct = _call(repository_map, "dependencies_of", module)
        if direct is not None:
            dependencies = dependencies or _bounded_strs(direct, MAX_CONTEXT_DEPENDENCIES)
        reverse = _bounded_strs(
            _call(repository_map, "dependents_of", module), MAX_CONTEXT_DEPENDENCIES
        )
        production = tuple(item for item in reverse if not item.startswith("tests."))
        dependents = production or reverse
        if dependents:
            reasons.append(f"{len(dependents)} dependent module(s) reported as change impact")

    # -- 4. repository-derived tests -----------------------------------------
    tests: tuple[str, ...] = ()
    if module:
        tests = _bounded_strs(
            _call(repository_map, "tests_for_module", module), MAX_CONTEXT_TESTS
        )
        if tests:
            reasons.append(
                f"{len(tests)} repository-derived test module(s) related to {module!r}"
            )

    # -- 5. lexical module ranking: FALLBACK ONLY ----------------------------
    fallback = False
    if not module and requested:
        reasons.append(
            f"declared target {requested!r} could not be resolved; the existing "
            "module ranking is used as a bounded fallback"
        )
    if not module:
        query = _text(request.query)
        if query:
            ranked = tuple(_call(repository_map, "rank_modules", query, 1) or ())
            top = str(getattr(ranked[0], "module", "") or "") if ranked else ""
            if top:
                module = top
                fallback = True
                reasons.append(
                    f"module ranking fallback selected {top!r} (no target was resolved)"
                )
        elif requested:
            fallback = True

    if not regions and module and not symbol_entry:
        for region in tuple(_call(repository_map, "regions_for", (module,), MAX_CONTEXT_REGIONS) or ()):
            regions.append(region)

    regions = regions[:MAX_CONTEXT_REGIONS]

    # -- hard character budget over the SELECTED SOURCE ----------------------
    source, truncated = _select_source(regions, budget)

    return RepositoryContext(
        module=module,
        regions=tuple(regions),
        symbols=tuple(symbols[:MAX_CONTEXT_SYMBOLS]),
        tests=tests,
        dependencies=dependencies,
        dependents=dependents,
        rationale=tuple(reason[:MAX_REASON_CHARS] for reason in reasons[:MAX_CONTEXT_REASONS]),
        source=source,
        truncated=truncated,
        resolved=bool(module),
        fallback=fallback,
    )


def _select_source(regions: tuple[Any, ...] | list[Any], budget: int) -> tuple[str, bool]:
    """Join the selected regions' source within ``budget`` (deterministic)."""
    chunks: list[str] = []
    remaining = budget
    truncated = False
    for region in regions:
        text = str(getattr(region, "source", "") or "")
        if not text:
            continue
        if remaining <= 0:
            truncated = True
            break
        allowed = min(len(text), remaining)
        if allowed < len(text):
            truncated = True
        chunks.append(text[:allowed])
        remaining -= allowed
    return "\n".join(chunks), truncated


def context_sources(
    repository_map: Any, request: RepositoryContextRequest
) -> dict[str, str]:
    """Bounded ``path -> source`` mapping for one request (authoring evidence).

    The single reusable entry point for a caller that needs the DECLARED
    target's source as evidence rather than a rendered block. Returns ``{}``
    when the target does not resolve, so the caller's prompt stays exactly what
    it was before the context existed.
    """
    context = build_repository_context(repository_map, request)
    source = context.source
    if not source:
        return {}
    path = _path_for_module(repository_map, context.module)
    if not path:
        return {}
    return {path: source}


def _path_for_module(repository_map: Any, module: str) -> str:
    if not module:
        return ""
    info = _module_index(repository_map).get(module)
    path = str(getattr(info, "path", "") or "") if info is not None else ""
    return path or (module.replace(".", "/") + ".py")


__all__ = [
    "DEFAULT_CONTEXT_CHARS",
    "MAX_CONTEXT_CHARS_LIMIT",
    "RepositoryContext",
    "RepositoryContextRequest",
    "build_repository_context",
    "context_sources",
    "normalise_module",
]
