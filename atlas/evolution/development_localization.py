"""Atlas Evolution — deterministic development localization.

Answers ONE question, before any authoring or planning:

    "Which repository artifact(s) and symbol(s) does this development request
     refer to, and what bounded surrounding context is relevant?"

It is a COMPOSITION layer, not a new repository model. Every fact it returns
comes from the EXISTING :class:`~atlas.research.repository_map.RepositoryMap`
(BM25 module ranking, the AST-derived symbol index, the reverse-import graph,
the test projection and the bounded source excerpts). No parser, index, model,
embedding or dependency is introduced.

Adapted mechanisms (principles only, no library adopted)
--------------------------------------------------------
* **Agentless-style ladder** — localize at the FILE level first, then narrow to
  the SYMBOL level, then extract precise bounded context.
* **Aider repo-map principles** — a symbol-oriented, dependency-aware,
  budget-bounded context slice built from the map's existing structural data.
* Structural targeting is done on the AST-derived symbol index the repository
  ALREADY built, so ast-grep/Tree-sitter-style structural matching needs no
  second parser and no new dependency (the project is Python-only and the
  standard-library ``ast`` module already produced that index).

Authority
---------
A localization result is EVIDENCE, never truth or authority. A ranked candidate
is explicitly distinguishable from a verified target (``status``), and nothing
here authorizes modification, approval, execution or promotion. Ambiguity is
REPRESENTED (``AMBIGUOUS`` with candidates), never resolved by preference.

Deterministic, bounded, standard-library only. No clock, randomness, I/O,
network, model, kernel or registry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

#: Bounds (a malformed or huge request can never produce unbounded work).
MAX_REQUEST_CHARS: int = 2_000
MAX_SURFACES: int = 32
MAX_CANDIDATES: int = 8
MAX_SYMBOLS: int = 24
MAX_CONTEXT_MODULES: int = 6
MAX_TESTS: int = 8
MAX_DEPENDENCIES: int = 12
MAX_EVIDENCE: int = 12

#: Dotted identifier sequences, longest first during extraction.
_DOTTED_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
#: Repository-relative file paths ("atlas/evolution/development_gap.py").
_PATH_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./\\-]*\.py")
#: A single identifier-shaped run, ORIGINAL CASE preserved.
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
#: Words that are ordinary prose, never symbol candidates on their own.
_PROSE_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "the", "this", "that", "it", "its", "these", "those",
        "change", "changes", "update", "updates", "replace", "replaces", "fix",
        "fixes", "make", "makes", "modify", "modifies", "improve", "improves",
        "add", "adds", "delete", "deletes", "insert", "inserts", "create",
        "creates", "build", "builds", "refactor", "refactors", "extend",
        "extends", "implement", "implements", "helper", "function", "method",
        "class", "module", "file", "files", "code", "test", "tests", "empty",
        "input", "value", "values", "behavior", "behaviour", "interface",
        "please", "your", "you", "atlas", "should", "while", "preserving",
        "preserve", "existing", "current", "public", "signature", "now",
    }
)

#: A surface must look like an identifier to be used for SYMBOL matching:
#: it carries an underscore or an internal capital. This is what keeps ordinary
#: prose ("change", "update") from fabricating symbol candidates.
_IDENTIFIER_SHAPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CAMEL_RE = re.compile(r"[a-z0-9][A-Z]")


class LocalizationStatus(str, Enum):
    """Whether the request localized to one artifact, many, or none."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class LocalizationKind(str, Enum):
    """The kind of repository artifact a localization refers to."""

    MODULE = "module"
    PACKAGE = "package"
    SYMBOL = "symbol"


@dataclass(frozen=True, slots=True)
class LocalizationCandidate:
    """One ranked candidate artifact, with the evidence that ranked it."""

    identifier: str
    kind: LocalizationKind
    path: str = ""
    score: float = 0.0
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "kind": self.kind.value,
            "path": self.path,
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class SymbolCandidate:
    """One symbol the request may refer to (AST-derived, never guessed)."""

    name: str
    qualified: str
    kind: str
    module: str
    path: str = ""
    line: int = 0
    signature: str = ""
    references: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualified": self.qualified,
            "kind": self.kind,
            "module": self.module,
            "path": self.path,
            "line": self.line,
            "signature": self.signature,
            "references": self.references,
        }


@dataclass(frozen=True, slots=True)
class LocalizationContext:
    """The bounded, ranked repository context relevant to the target."""

    modules: tuple[str, ...] = ()
    symbols: tuple[SymbolCandidate, ...] = ()
    tests: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    dependents: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "modules": list(self.modules),
            "symbols": [s.to_dict() for s in self.symbols],
            "tests": list(self.tests),
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
        }


@dataclass(frozen=True, slots=True)
class LocalizationResult:
    """The bounded outcome of localizing ONE development request.

    ``status`` distinguishes a single evidence-backed target (``RESOLVED``) from
    a ranked candidate set (``AMBIGUOUS``) and from no evidence (``UNRESOLVED``).
    A high ``score`` never implies a verified target.
    """

    request: str = ""
    status: LocalizationStatus = LocalizationStatus.UNRESOLVED
    target: str = ""
    target_kind: str = ""
    symbol: SymbolCandidate | None = None
    candidates: tuple[LocalizationCandidate, ...] = ()
    symbol_candidates: tuple[SymbolCandidate, ...] = ()
    context: LocalizationContext = field(default_factory=LocalizationContext)
    evidence: tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.status is LocalizationStatus.RESOLVED and bool(self.target)

    @property
    def ambiguous(self) -> bool:
        return self.status is LocalizationStatus.AMBIGUOUS

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "status": self.status.value,
            "target": self.target,
            "target_kind": self.target_kind,
            "symbol": self.symbol.to_dict() if self.symbol else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "symbol_candidates": [s.to_dict() for s in self.symbol_candidates],
            "context": self.context.to_dict(),
            "evidence": list(self.evidence),
        }


def is_identifier_shaped(surface: Any) -> bool:
    """Whether ``surface`` looks like a code identifier rather than prose.

    An identifier carries an underscore or an internal capital (``some_helper``,
    ``TaskIntake``, ``module.Class.method``). Ordinary prose such as "change" or
    "update" does not — which is exactly the protection that stops a symbol
    candidate being fabricated out of an English word.
    """
    if not isinstance(surface, str):
        return False
    text = surface.strip()
    if not text:
        return False
    if "." in text:
        return all(_IDENTIFIER_SHAPE_RE.match(part) for part in text.split("."))
    if not _IDENTIFIER_SHAPE_RE.match(text):
        return False
    if "_" in text:
        return True
    return bool(_CAMEL_RE.search(text))


def identifier_surfaces(text: Any) -> tuple[str, ...]:
    """Bounded identifier-shaped surfaces of ``text`` (longest first).

    Extracted from the RAW request so ORIGINAL CASE is preserved: a class name
    such as ``RepositoryMap`` or ``TaskIntake`` must reach the symbol index in
    the spelling the repository actually uses. Three sources, in priority order:
    dotted sequences (``a.b.C.m``), identifier-shaped runs, then the request's
    significant words (lowercased) — which are only ever used for MODULE lookup,
    never for symbol matching.

    Deterministic ordering: longest first, then alphabetical.
    """
    if not isinstance(text, str) or not text.strip():
        return ()
    sample = text[:MAX_REQUEST_CHARS]
    found: list[str] = []
    for match in _PATH_RE.findall(sample):
        if match not in found:
            found.append(match)
    for match in _DOTTED_RE.findall(sample):
        if match not in found:
            found.append(match)
    for match in _IDENTIFIER_RE.findall(sample):
        if is_identifier_shaped(match) and match not in found:
            found.append(match)
    try:
        from atlas.research._text import significant_tokens

        for token in significant_tokens(sample):
            if token not in found:
                found.append(token)
    except Exception:
        pass
    found.sort(key=lambda item: (-len(item), item))
    return tuple(found[:MAX_SURFACES])


def _symbol_candidate(info: Any, path: str) -> SymbolCandidate:
    return SymbolCandidate(
        name=str(getattr(info, "name", "") or ""),
        qualified=str(getattr(info, "qualified", "") or ""),
        kind=str(getattr(getattr(info, "kind", None), "value", "") or ""),
        module=str(getattr(info, "module", "") or ""),
        path=path,
        line=int(getattr(info, "line", 0) or 0),
        signature=str(getattr(info, "signature", "") or ""),
        references=int(getattr(info, "references", 0) or 0),
    )


class DevelopmentLocalizer:
    """Deterministic file-then-symbol localization over an EXISTING map.

    Args:
        repository_map: A duck-typed ``RepositoryMap``-like object. With none the
            localizer is inert and every result is ``UNRESOLVED`` — an honest
            empty result, never a guess.
    """

    def __init__(self, repository_map: Any | None = None) -> None:
        self._map = repository_map

    # -- index helpers -----------------------------------------------------

    def _index(self) -> tuple[dict[str, Any], dict[str, Any]]:
        by_module: dict[str, Any] = {}
        by_path: dict[str, Any] = {}
        for info in getattr(self._map, "modules", ()) or ():
            module = str(getattr(info, "module", "") or "")
            path = str(getattr(info, "path", "") or "")
            if module:
                by_module[module] = info
            if path:
                by_path[path] = info
        return by_module, by_path

    @staticmethod
    def _module_name_tokens(module: str) -> frozenset[str]:
        try:
            from atlas.research._text import significant_tokens

            return frozenset(significant_tokens(module.rsplit(".", 1)[-1].replace("_", " ")))
        except Exception:
            return frozenset()

    def _path_for(self, module: str, by_module: dict) -> str:
        info = by_module.get(module)
        return str(getattr(info, "path", "")) if info is not None else ""

    # -- public API --------------------------------------------------------

    def localize(self, request: Any) -> LocalizationResult:
        """Localize ``request`` to a target and, where possible, a symbol."""
        if not isinstance(request, str) or not request.strip():
            return LocalizationResult(request=str(request or "")[:MAX_REQUEST_CHARS])
        text = request[:MAX_REQUEST_CHARS]
        if self._map is None:
            return LocalizationResult(request=text, evidence=("no repository map",))

        by_module, by_path = self._index()
        surfaces = identifier_surfaces(text)

        # 1. EXACT QUALIFIED SYMBOL — the most specific possible match. Matched
        #    against the repository's OWN qualified representation, so
        #    ``module.Class.method`` resolves exactly like ``module.Class``.
        found = self._exact_symbol(surfaces, by_module)
        if found is not None:
            return self._result(
                text, found[0], found[1], found[2], by_module, symbol=found[3]
            )

        # 2. EXACT MODULE / PACKAGE / PATH.
        for surface in (*surfaces, *_lowered_words(text)):
            normalized = surface.replace("\\", "/")
            info = by_path.get(normalized) or by_path.get(normalized + ".py")
            if info is not None:
                return self._result(
                    text, str(getattr(info, "module", "")), LocalizationKind.MODULE,
                    ("exact file path match",), by_module,
                )
            if surface in by_module:
                return self._result(
                    text, surface, LocalizationKind.MODULE,
                    ("exact module match",), by_module,
                )

        # 3. MODULE NAME-TOKEN MATCH (every name token present, >= 2 tokens).
        request_tokens = _word_set(text)
        if request_tokens:
            matches = [
                module
                for module in sorted(by_module)
                if not module.startswith("tests.")
                and len(name_tokens := self._module_name_tokens(module)) >= 2
                and name_tokens <= request_tokens
            ]
            if len(matches) == 1:
                return self._result(
                    text, matches[0], LocalizationKind.MODULE,
                    ("module name tokens present in the request",), by_module,
                )
            if len(matches) > 1:
                return self._ambiguous(
                    text,
                    [(m, LocalizationKind.MODULE, ("module name tokens present",))
                     for m in matches],
                    by_module,
                    ("several modules match the request's name tokens",),
                )

        # 4. UNIQUE SYMBOL NAME — identifier-shaped surfaces only, so prose can
        #    never fabricate a symbol.
        symbol_matches = self._symbols_by_name(surfaces, by_module)
        if len(symbol_matches) == 1:
            module, candidate = symbol_matches[0]
            return self._result(
                text, module, LocalizationKind.SYMBOL,
                ("unique symbol identifier match",), by_module, symbol=candidate,
            )
        if len(symbol_matches) > 1:
            return self._ambiguous(
                text,
                [(module, LocalizationKind.SYMBOL, ("symbol identifier match",))
                 for module, _ in symbol_matches],
                by_module,
                (f"identifier is defined in {len(symbol_matches)} places",),
            )

        # 5. RANKED FALLBACK — a ranking score is NOT a verified target.
        ranked = self._rank(text)
        if ranked:
            return self._ambiguous(
                text,
                [(m, LocalizationKind.MODULE, (f"ranked lexical match {i + 1}",))
                 for i, m in enumerate(ranked)],
                by_module,
                ("no exact identifier matched; ranked candidates only",),
            )
        return LocalizationResult(request=text, evidence=("no candidate found",))

    # -- internals ---------------------------------------------------------

    def _exact_symbol(self, surfaces: Iterable[str], by_module: dict) -> tuple | None:
        """The symbol whose QUALIFIED name is exactly one of ``surfaces``."""
        find = getattr(self._map, "find_symbol", None)
        if not callable(find):
            return None
        qualified_index: dict[str, Any] = {}
        for info in getattr(self._map, "symbols", ()) or ():
            qualified = str(getattr(info, "qualified", "") or "")
            if qualified:
                qualified_index.setdefault(qualified, info)
        for surface in surfaces:
            if "." not in surface:
                continue
            info = qualified_index.get(surface)
            if info is None:
                continue
            module = str(getattr(info, "module", "") or "")
            return (
                module,
                LocalizationKind.SYMBOL,
                ("exact qualified symbol match",),
                _symbol_candidate(info, self._path_for(module, by_module)),
            )
        return None

    def _symbols_by_name(self, surfaces: Iterable[str], by_module: dict) -> list[tuple]:
        """Symbols whose NAME is exactly an identifier-shaped surface."""
        find = getattr(self._map, "find_symbol", None)
        if not callable(find):
            return []
        out: list[tuple] = []
        seen: set[str] = set()
        for surface in surfaces:
            if not is_identifier_shaped(surface) or "." in surface:
                continue
            if surface.lower() in _PROSE_WORDS:
                continue
            try:
                hits = find(surface, limit=MAX_CANDIDATES)
            except Exception:
                continue
            for info in hits:
                if str(getattr(info, "name", "")) != surface:
                    continue
                qualified = str(getattr(info, "qualified", "") or "")
                if not qualified or qualified in seen:
                    continue
                seen.add(qualified)
                module = str(getattr(info, "module", "") or "")
                out.append((module, _symbol_candidate(info, self._path_for(module, by_module))))
        return out

    def _rank(self, text: str) -> tuple[str, ...]:
        rank = getattr(self._map, "rank_modules", None)
        if not callable(rank):
            return ()
        try:
            ranked = tuple(rank(text, limit=MAX_CANDIDATES))
        except Exception:
            return ()
        modules: list[str] = []
        for entry in ranked:
            module = str(getattr(entry, "module", "") or "")
            if not module or module.startswith("tests.") or module in modules:
                continue
            modules.append(module)
        return tuple(modules[:MAX_CANDIDATES])

    def _context(self, module: str, *, symbol: SymbolCandidate | None) -> LocalizationContext:
        by_module, _ = self._index()
        path = self._path_for(module, by_module)

        symbols: list[SymbolCandidate] = []
        getter = getattr(self._map, "symbols_in_module", None)
        if callable(getter):
            try:
                for item in tuple(getter(module))[:MAX_SYMBOLS]:
                    symbols.append(_symbol_candidate(item, path))
            except Exception:
                symbols = []
        if symbol is not None and all(s.qualified != symbol.qualified for s in symbols):
            symbols.insert(0, symbol)

        tests: tuple[str, ...] = ()
        tests_for = getattr(self._map, "tests_for_module", None)
        if callable(tests_for):
            try:
                tests = tuple(tests_for(module, limit=MAX_TESTS))
            except Exception:
                tests = ()

        def _edges(name: str) -> tuple[str, ...]:
            fn = getattr(self._map, name, None)
            if not callable(fn):
                return ()
            try:
                return tuple(str(x) for x in (fn(module) or ()))[:MAX_DEPENDENCIES]
            except Exception:
                return ()

        return LocalizationContext(
            modules=(module,),
            symbols=tuple(symbols[:MAX_SYMBOLS]),
            tests=tests,
            dependencies=_edges("dependencies_of"),
            dependents=_edges("dependents_of"),
        )

    def _result(
        self,
        text: str,
        target: str,
        kind: LocalizationKind,
        reasons: tuple[str, ...],
        by_module: dict,
        *,
        symbol: SymbolCandidate | None = None,
    ) -> LocalizationResult:
        return LocalizationResult(
            request=text,
            status=LocalizationStatus.RESOLVED,
            target=target,
            target_kind=kind.value,
            symbol=symbol,
            candidates=(LocalizationCandidate(target, kind, score=1.0, reasons=reasons),),
            symbol_candidates=(symbol,) if symbol is not None else (),
            context=self._context(target, symbol=symbol) if target else LocalizationContext(),
            evidence=reasons,
        )

    def _ambiguous(
        self,
        text: str,
        entries: list[tuple[str, LocalizationKind, tuple[str, ...]]],
        by_module: dict,
        evidence: tuple[str, ...],
    ) -> LocalizationResult:
        candidates = tuple(
            LocalizationCandidate(
                identifier=identifier,
                kind=kind,
                path=self._path_for(identifier, by_module),
                reasons=reasons,
            )
            for identifier, kind, reasons in entries[:MAX_CANDIDATES]
            if identifier
        )
        symbols: list[SymbolCandidate] = []
        for candidate in candidates:
            if candidate.kind is not LocalizationKind.SYMBOL:
                continue
            for item in self._context(candidate.identifier, symbol=None).symbols:
                if all(s.qualified != item.qualified for s in symbols):
                    symbols.append(item)
        return LocalizationResult(
            request=text,
            status=LocalizationStatus.AMBIGUOUS,
            candidates=candidates,
            symbol_candidates=tuple(symbols[:MAX_SYMBOLS]),
            evidence=evidence[:MAX_EVIDENCE],
        )


def _lowered_words(text: str) -> tuple[str, ...]:
    """Lower-cased words of ``text`` (used for MODULE lookup only)."""
    try:
        from atlas.research._text import significant_tokens

        return tuple(sorted(significant_tokens(text), key=lambda t: (-len(t), t)))
    except Exception:
        return ()


def _word_set(text: str) -> frozenset[str]:
    """Significant words of ``text``, split on identifiers too (module lookup)."""
    try:
        from atlas.research._text import significant_tokens

        return frozenset(significant_tokens(text)) | frozenset(
            significant_tokens(text.replace("_", " ").replace(".", " "))
        )
    except Exception:
        return frozenset()


__all__ = [
    "DevelopmentLocalizer",
    "LocalizationCandidate",
    "LocalizationContext",
    "LocalizationKind",
    "LocalizationResult",
    "LocalizationStatus",
    "SymbolCandidate",
    "identifier_surfaces",
    "is_identifier_shaped",
]
