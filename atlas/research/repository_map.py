"""Atlas Research — Repository Self-Knowledge Map — Stage A1.

A read-only, machine-readable map of a Python repository: discovered
modules, their AST-extracted import dependencies, structurally-extracted
symbols (top-level classes/functions and their methods, with bounded
signatures and a bounded name-reference count), and pure graph queries
(forward deps, reverse deps, depth-bounded impact sets, deterministic symbol
lookup, and bounded targeted symbol context).

Design contract:

* **Read-only**: ``build()`` reads files through the shared research
  primitives; nothing is ever written, and no git operations exist here.
* **Deterministic**: identical trees produce identical maps.
* **Bounded**: hard caps on modules, errors, file size, and per-module
  imports keep worst-case cost predictable on large trees.
* **Fail-soft**: unreadable or unparsable files become ``errors`` entries —
  never exceptions. An empty or hostile tree yields a valid empty map.
* **No I/O after build**: queries are pure functions over immutable data;
  circular imports are stored as ordinary edges (BFS uses a visited set).

Reuses the existing research vocabulary (``source_catalog`` extensions /
languages) and the shared safe-read primitive — no duplication of language
detection or file reading.

Pure logic. No AI. No gateway. No storage. No kernel access.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from math import log
from pathlib import Path

from atlas.research.source_catalog import LANGUAGE_BY_EXTENSION

# ---------------------------------------------------------------------------
# Boundedness constants (deterministic; audit these, never per-request)
# ---------------------------------------------------------------------------

DEFAULT_EXCLUDES: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
        ".tox",
    }
)

MAX_MODULES: int = 5000
MAX_ERRORS: int = 200
MAX_FILE_BYTES: int = 1_000_000
MAX_IMPORTS_PER_MODULE: int = 64
DEFAULT_IMPACT_DEPTH: int = 3

# --- Symbol-level structure (Stage A2) ------------------------------------
# Aider-style structural intelligence, Atlas-native and deterministic: each
# module's top-level classes/functions and their methods, with bounded
# signatures and a bounded repo-wide name-reference count used only for
# relevance ordering (never for semantics).
MAX_SYMBOLS_PER_MODULE: int = 64
MAX_SYMBOLS_TOTAL: int = 20000
MAX_SIGNATURE_CHARS: int = 120
MAX_SYMBOL_MATCHES: int = 50
MAX_CONTEXT_SYMBOLS: int = 40
MAX_REFERENCES: int = 1_000_000

#: Bounded SOURCE excerpt retained per module, captured from the file text the
#: builder has ALREADY read (no extra I/O). It exists because the downstream
#: authoring contract asks for full replacement content, so a symbol list alone
#: cannot support authoring; a small module's whole source fits here, and a large
#: module keeps a bounded, explicitly-truncated preamble.
MAX_SOURCE_EXCERPT_CHARS: int = 4000

# --- Symbol/region graph (Command 2, A1) ----------------------------------
# Bounded structural relationships derived from the SAME single AST pass: the
# sites where each symbol is referenced, the calls it makes/resolves (ONLY when
# unambiguous), and the bounded source region it spans. Nothing is guessed: an
# ambiguous name resolves to NO edge, an unknown symbol is empty, and every
# collection is capped.
MAX_REFERENCE_SITES_PER_SYMBOL: int = 32
MAX_EDGES_PER_SYMBOL: int = 32
#: Hard cap on one symbol's stored source region.
MAX_REGION_CHARS: int = 2000
#: Hard cap on the TOTAL stored region characters. Regions are allocated in
#: deterministic ``(module, qualified)`` order; past the cap a symbol has no
#: stored region and ``region_of`` returns ``None`` — never a partial guess.
MAX_REGION_TOTAL_CHARS: int = 12_000_000
#: Hard cap on the flat symbol-edge list the map exposes.
MAX_EDGES_TOTAL: int = 40000
#: Default cap for bounded region queries.
MAX_REGION_CONTEXT_CHARS: int = 12000
DEFAULT_REGION_LIMIT: int = 20

# --- Bounded lexical ranking (BM25-style) -------------------------------
# Standard Okapi BM25 free parameters, fixed at module level (never per
# request) so a ranking is reproducible and auditable.
_RANK_K1: float = 1.5
_RANK_B: float = 0.75
#: How many times a module's IDENTITY terms (dotted path / basename) are
#: counted. Identity is what the module is; symbol names are incidental evidence
#: and are capped per module, so raw term counts would otherwise rank a large
#: verbose module above the one actually named after the query.
_RANK_IDENTITY_WEIGHT: int = 3
DEFAULT_RANK_LIMIT: int = 10
MAX_RANK_LIMIT: int = 50

#: Dotted-name prefix of every test module discovered by this map. Test modules
#: are ordinary repository modules here (no ``is_test`` classification exists or
#: is added); the prefix is only used by the bounded projection below.
TEST_MODULE_PREFIX: str = "tests."

#: Default cap on the test modules returned for one module (boundedness).
DEFAULT_MAX_TESTS: int = 20
#: Terms too generic to discriminate one module from another. These are
#: ordinary English/Atlas words, never repository facts; a query made only of
#: them yields nothing rather than an arbitrary ordering.
_RANK_STOP_TERMS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do",
        "does", "for", "from", "how", "i", "if", "in", "into", "is", "it",
        "its", "me", "of", "on", "or", "that", "the", "their", "them", "then",
        "there", "these", "this", "those", "to", "was", "we", "were", "what",
        "when", "where", "which", "who", "why", "will", "with", "you", "your",
    }
)

#: Separator runs inside a dotted path / identifier.
_RANK_SPLIT_RE = re.compile(r"[^0-9A-Za-z]+")
#: camelCase / PascalCase boundary (the same rule the target resolver uses).
_RANK_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _rank_log(value: float) -> float:
    """``log`` kept as a named seam so the ranking formula reads clearly."""
    return log(value)


def _tokenize_for_ranking(text: object) -> tuple[str, ...]:
    """Deterministic, de-duplicated, order-preserving ranking terms."""
    if not isinstance(text, str) or not text.strip():
        return ()
    parts: list[str] = []
    for chunk in _RANK_SPLIT_RE.split(text.strip()):
        if not chunk:
            continue
        for piece in _RANK_CAMEL_RE.split(chunk):
            lowered = piece.strip().lower()
            if lowered and lowered not in _RANK_STOP_TERMS:
                parts.append(lowered)
    return tuple(dict.fromkeys(parts))


def _ranking_terms(info: ModuleInfo) -> tuple[str, ...]:
    """Searchable terms for one module, from data the map already holds.

    Deliberately NOT source text: no file is read and no body is concatenated.
    The corpus is the structural identity Atlas already knows — the dotted path,
    the basename, and symbol names (which for Python are already split on their
    own word boundaries).

    The MODULE IDENTITY terms are repeated so an exact name match outweighs the
    incidental repetition of a common word across many symbols. Without this a
    large module that merely mentions "service" in forty symbol names outranks
    the module actually NAMED ``conversation_service`` — the symbol cap makes
    raw term counts a poor proxy for identity, not for relevance.
    """
    identity: list[str] = []
    for part in _RANK_SPLIT_RE.split(info.module):
        if part:
            identity.append(part.lower())
    basename = info.module.rsplit(".", 1)[-1]
    for part in _RANK_CAMEL_RE.split(basename):
        lowered = part.strip().lower()
        if lowered:
            identity.append(lowered)

    body: list[str] = []
    for symbol in info.symbols:
        for part in _RANK_SPLIT_RE.split(symbol.name):
            if part:
                body.append(part.lower())

    # Identity is what the module IS; body is incidental evidence. Identity terms
    # are repeated (NOT deduplicated) so a module actually NAMED
    # ``conversation_service`` outranks one that merely says "service" in many
    # symbol names. Body terms are deduplicated so verbosity cannot accumulate.
    weighted = identity * _RANK_IDENTITY_WEIGHT + list(
        dict.fromkeys(body)
    )
    return tuple(weighted)


def _matched_terms(terms: tuple[str, ...]) -> tuple[str, ...]:
    """The query terms this module actually matched (explainability)."""
    return tuple(terms)


@dataclass(frozen=True)
class RankedModule:
    """One ranked module with the evidence behind its rank."""

    module: str
    path: str
    score: float
    matched_terms: tuple[str, ...] = ()
    symbol_count: int = 0
    line_count: int = 0

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "path": self.path,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "symbol_count": self.symbol_count,
            "line_count": self.line_count,
        }



# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SymbolKind(str, Enum):
    """The structural kind of one extracted symbol."""

    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"


@dataclass(frozen=True)
class SymbolInfo:
    """One structurally-extracted definition (bounded; deterministic).

    Command 2 (A1) adds the bounded structural relationships — the reference
    SITES, the unambiguous callers/callees and the definition's end line — all
    derived from the SAME single AST pass. Every addition is defaulted, so the
    existing construction contract and every existing caller are unchanged.
    """

    name: str
    qualified: str
    module: str
    kind: SymbolKind
    line: int
    signature: str = ""
    references: int = 0
    #: Last source line of the definition (decorators included); 0 when unknown.
    end_line: int = 0
    #: Bounded, deterministically-ordered sites where the symbol NAME is used.
    reference_sites: tuple["ReferenceSite", ...] = ()
    #: Qualified symbols that call this one, ONLY when resolution is unambiguous.
    callers: tuple[str, ...] = ()
    #: Qualified symbols this one calls, ONLY when resolution is unambiguous.
    callees: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "qualified": self.qualified,
            "module": self.module,
            "kind": self.kind.value,
            "line": self.line,
            "end_line": self.end_line,
            "signature": self.signature,
            "references": self.references,
            "reference_sites": [site.to_dict() for site in self.reference_sites],
            "callers": list(self.callers),
            "callees": list(self.callees),
        }


@dataclass(frozen=True)
class ReferenceSite:
    """One bounded site where a symbol's name is used (module + line)."""

    module: str
    line: int
    symbol: str = ""

    def to_dict(self) -> dict:
        return {"module": self.module, "line": self.line, "symbol": self.symbol}


@dataclass(frozen=True)
class SymbolEdge:
    """One bounded, UNAMBIGUOUS caller -> callee edge (qualified names)."""

    caller: str
    callee: str
    module: str = ""
    line: int = 0

    def to_dict(self) -> dict:
        return {
            "caller": self.caller,
            "callee": self.callee,
            "module": self.module,
            "line": self.line,
        }


@dataclass(frozen=True)
class SymbolRegion:
    """The bounded source region one symbol spans (never a partial guess)."""

    qualified: str
    module: str
    path: str
    start_line: int
    end_line: int
    source: str = ""
    truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "qualified": self.qualified,
            "module": self.module,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "source": self.source,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class ModuleInfo:
    """One discovered Python module and its resolved import edges.

    ``symbols`` carries the module's structurally-extracted definitions
    (top-level classes/functions and their methods), bounded and deterministic.
    """

    module: str
    path: str
    language: str
    is_package: bool
    line_count: int
    internal_imports: tuple[str, ...] = ()
    external_imports: tuple[str, ...] = ()
    symbols: tuple[SymbolInfo, ...] = ()
    #: Bounded SOURCE excerpt (derived from the file text already read at build).
    #: Empty when the file was unreadable. ``source_truncated`` records honestly
    #: whether the excerpt omits part of the file.
    source_excerpt: str = ""
    source_truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "path": self.path,
            "language": self.language,
            "is_package": self.is_package,
            "line_count": self.line_count,
            "internal_imports": list(self.internal_imports),
            "external_imports": list(self.external_imports),
            "symbols": [s.to_dict() for s in self.symbols],
            "source_excerpt": self.source_excerpt,
            "source_truncated": self.source_truncated,
        }


@dataclass(frozen=True)
class RepositoryMap:
    """Immutable, deterministic snapshot of a repository's Python structure."""

    built_at: datetime
    root_label: str
    modules: tuple[ModuleInfo, ...]
    errors: tuple[str, ...] = ()
    truncated: bool = False
    metadata: dict = field(default_factory=dict)
    #: Flat, deterministic symbol index (sorted by qualified name).
    symbols: tuple[SymbolInfo, ...] = ()
    #: Command 2 — bounded symbol REGIONS, allocated in deterministic
    #: ``(module, qualified)`` order (see ``MAX_REGION_TOTAL_CHARS``).
    regions: tuple[SymbolRegion, ...] = ()
    #: Command 2 — bounded, UNAMBIGUOUS caller -> callee edges.
    edges: tuple[SymbolEdge, ...] = ()

    def _module_index(self) -> dict[str, ModuleInfo]:
        return {info.module: info for info in self.modules}

    def _symbol_for(self, symbol: object) -> "SymbolInfo | None":
        """Resolve ``symbol`` (qualified/name/suffix) to ONE symbol, or ``None``."""
        text = str(symbol or "").strip() if isinstance(symbol, str) else ""
        if not text:
            return None
        found = self.find_symbol(text, limit=1)
        return found[0] if found else None

    def _region_index(self) -> dict[str, SymbolRegion]:
        return {region.qualified: region for region in self.regions}

    def references_of(self, symbol: object) -> tuple[ReferenceSite, ...]:
        """Bounded reference SITES for ``symbol`` (empty when unknown)."""
        entry = self._symbol_for(symbol)
        return entry.reference_sites if entry is not None else ()

    def callers_of(self, symbol: object) -> tuple[str, ...]:
        """Qualified symbols that call ``symbol`` (unambiguous only; else ())."""
        entry = self._symbol_for(symbol)
        return entry.callers if entry is not None else ()

    def callees_of(self, symbol: object) -> tuple[str, ...]:
        """Qualified symbols ``symbol`` calls (unambiguous only; else ())."""
        entry = self._symbol_for(symbol)
        return entry.callees if entry is not None else ()

    def region_of(self, symbol: object) -> "SymbolRegion | None":
        """The stored bounded source region for ``symbol`` (or ``None``)."""
        entry = self._symbol_for(symbol)
        if entry is None:
            return None
        return self._region_index().get(entry.qualified)

    def regions_for(
        self, modules: object = (), limit: int = DEFAULT_REGION_LIMIT
    ) -> tuple[SymbolRegion, ...]:
        """Bounded stored regions for ``modules`` (all modules when none given)."""
        names = (
            {m for m in (modules or ()) if isinstance(m, str) and m}
            if modules
            else set()
        )
        cap = max(1, min(int(limit or DEFAULT_REGION_LIMIT), MAX_SYMBOL_MATCHES))
        selected = [
            region
            for region in self.regions
            if not names or region.module in names
        ]
        return tuple(selected[:cap])

    def _reverse_index(self) -> dict[str, tuple[str, ...]]:
        reverse: dict[str, list[str]] = {}
        for info in self.modules:
            for dep in info.internal_imports:
                reverse.setdefault(dep, []).append(info.module)
        return {name: tuple(sorted(set(deps))) for name, deps in reverse.items()}

    def dependencies_of(self, module: str) -> tuple[str, ...]:
        """Internal modules directly imported by ``module``."""
        info = self._module_index().get(module)
        return info.internal_imports if info else ()

    def dependents_of(self, module: str) -> tuple[str, ...]:
        """Internal modules that directly import ``module``."""
        return self._reverse_index().get(module, ())

    def tests_for_module(
        self, module: str, limit: int = DEFAULT_MAX_TESTS
    ) -> tuple[str, ...]:
        """Repo-relative test paths that directly import ``module``.

        A DETERMINISTIC PROJECTION over the EXISTING reverse-import index — the
        same data ``dependents_of`` already exposes — restricted to modules this
        repository actually contains whose dotted name begins with ``tests.``.
        Returns their real ``ModuleInfo.path`` (POSIX, repo-relative), so a
        caller never has to reconstruct a path and no path is ever invented: an
        unknown module, no importer, or a non-positive ``limit`` yields ``()``.

        Nothing is inferred from a filename. A test module is one this map
        discovered that imports the module; the naming convention is not
        consulted, and no ``is_test`` classification is introduced.
        """
        try:
            cap = int(limit)
        except (TypeError, ValueError):
            cap = DEFAULT_MAX_TESTS
        if cap < 1:
            return ()
        module_index = self._module_index()
        paths: list[str] = []
        for dependent in self.dependents_of(module):
            if not dependent.startswith(TEST_MODULE_PREFIX):
                continue
            info = module_index.get(dependent)
            path = str(getattr(info, "path", "") or "")
            if path and path not in paths:
                paths.append(path)
        return tuple(paths[:cap])

    def impact_set(
        self,
        module: str,
        max_depth: int = DEFAULT_IMPACT_DEPTH,
    ) -> frozenset[str]:
        """
        Transitive reverse-dependency closure within ``max_depth`` hops.

        Answers: which modules could be affected if ``module`` changes?
        Circular imports terminate naturally via the visited set.
        """
        if max_depth <= 0:
            return frozenset()
        reverse = self._reverse_index()
        affected: set[str] = set()
        frontier = {module}
        visited = {module}
        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for name in frontier:
                for dependent in reverse.get(name, ()):
                    if dependent not in visited:
                        next_frontier.add(dependent)
            affected |= next_frontier
            visited |= next_frontier
            frontier = next_frontier
            if not frontier:
                break
        return frozenset(affected)

    # ------------------------------------------------------------------
    # Symbol-level structure (deterministic; read-only)
    # ------------------------------------------------------------------

    def symbol_count(self) -> int:
        return len(self.symbols)

    def symbols_in_module(self, module: str) -> tuple[SymbolInfo, ...]:
        """Structurally-extracted symbols defined by ``module`` (bounded)."""
        return tuple(s for s in self.symbols if s.module == module)

    def find_symbol(
        self, query: str, limit: int = MAX_SYMBOL_MATCHES
    ) -> tuple[SymbolInfo, ...]:
        """Deterministic symbol lookup: exact qualified, exact name, then suffix.

        Returns only symbols this repository actually defines, ranked by the
        bounded reference count (then qualified name). An unknown query yields
        an empty tuple — nothing is inferred.
        """
        text = (query or "").strip() if isinstance(query, str) else ""
        if not text or not self.symbols:
            return ()

        def _ranked(items: list[SymbolInfo]) -> tuple[SymbolInfo, ...]:
            return tuple(
                sorted(items, key=lambda s: (-s.references, s.qualified))[: max(1, limit)]
            )

        exact = [s for s in self.symbols if s.qualified == text]
        if exact:
            return _ranked(exact)
        named = [s for s in self.symbols if s.name == text]
        if named:
            return _ranked(named)
        suffix = [s for s in self.symbols if s.qualified.endswith("." + text)]
        if suffix:
            return _ranked(suffix)
        return ()

    def important_symbols(self, limit: int = MAX_SYMBOL_MATCHES) -> tuple[SymbolInfo, ...]:
        """The most reference-connected symbols (deterministic relevance order).

        Relevance is evidence-only: the bounded repo-wide name-reference count
        and the module's inbound-import degree. Never a semantic judgement.
        """
        reverse = self._reverse_index()

        def key(s: SymbolInfo) -> tuple:
            return (-s.references, -len(reverse.get(s.module, ())), s.qualified)

        return tuple(sorted(self.symbols, key=key)[: max(1, limit)])

    def context_for(
        self, modules: object = (), max_symbols: int = MAX_CONTEXT_SYMBOLS
    ) -> tuple[SymbolInfo, ...]:
        """Bounded symbol slice for the given modules (targeted context).

        With no modules supplied this degrades to :meth:`important_symbols`, so
        a caller always receives a bounded, deterministic slice.
        """
        names = {
            m for m in (modules or ()) if isinstance(m, str) and m
        } if modules else set()
        if not names:
            return self.important_symbols(max_symbols)
        selected = [s for s in self.symbols if s.module in names]
        return tuple(
            sorted(selected, key=lambda s: (-s.references, s.qualified))[
                : max(1, max_symbols)
            ]
        )

    def module_count(self) -> int:
        return len(self.modules)

    # ------------------------------------------------------------------
    # Bounded lexical ranking (BM25-style) over the EXISTING map data
    # ------------------------------------------------------------------

    def rank_modules(
        self, query: str, limit: int = DEFAULT_RANK_LIMIT
    ) -> tuple[RankedModule, ...]:
        """Rank this repository's modules against ``query`` (BM25-style).

        A deterministic, read-only LEXICAL ranking over material this map
        already holds — dotted module path, module basename, symbol names and
        bounded signatures. No embeddings, no model, no randomness, no I/O:
        identical input yields an identical ordering, and every returned
        module is one this map actually contains.

        Ranking is evidence-only. It orders candidates; it never asserts that a
        module is the right place to make a change — that remains a governed
        decision made elsewhere.
        """
        terms = _tokenize_for_ranking(query)
        if not terms or not self.modules:
            return ()

        corpus = [(info, _ranking_terms(info)) for info in self.modules]
        total_docs = len(corpus)
        avg_len = sum(len(terms_) for _info, terms_ in corpus) / total_docs or 1.0

        document_frequency: Counter[str] = Counter()
        for _info, terms_ in corpus:
            document_frequency.update(set(terms_))

        scored: list[tuple[float, str, ModuleInfo, tuple[str, ...]]] = []
        for info, terms_ in corpus:
            counts = Counter(terms_)
            length = len(terms_) or 1
            score = 0.0
            for term in terms:
                tf = counts.get(term, 0)
                if not tf:
                    continue
                df = document_frequency.get(term, 0)
                # Okapi BM25 idf, floored at a small positive value so a term
                # present in EVERY document contributes 0 rather than a
                # negative score (which would invert the ordering).
                idf = max(
                    0.0,
                    _rank_log(
                        1.0
                        + (total_docs - df + 0.5) / (df + 0.5)
                    ),
                )
                denominator = tf + _RANK_K1 * (
                    1.0 - _RANK_B + _RANK_B * length / avg_len
                )
                if denominator > 0:
                    score += idf * (tf * (_RANK_K1 + 1.0)) / denominator
            if score > 0.0:
                # Deterministic tie-break: module name, never registry order.
                scored.append((score, info.module, info, _matched_terms(terms_)))

        scored.sort(key=lambda row: (-row[0], row[1]))
        bounded = max(1, min(int(limit or DEFAULT_RANK_LIMIT), MAX_RANK_LIMIT))
        return tuple(
            RankedModule(
                module=info.module,
                path=info.path,
                score=round(score, 6),
                matched_terms=matched,
                symbol_count=len(info.symbols),
                line_count=info.line_count,
            )
            for score, _module, info, matched in scored[:bounded]
        )

    def edge_count(self) -> int:
        return sum(len(info.internal_imports) for info in self.modules)

    def to_dict(self) -> dict:
        """JSON-safe projection of the whole map."""
        return {
            "built_at": self.built_at.isoformat(),
            "root_label": self.root_label,
            "module_count": self.module_count(),
            "edge_count": self.edge_count(),
            "symbol_count": self.symbol_count(),
            "region_count": len(self.regions),
            "symbol_edge_count": len(self.edges),
            "truncated": self.truncated,
            "error_count": len(self.errors),
            "modules": [info.to_dict() for info in self.modules],
            "metadata": dict(self.metadata),
        }


def _empty_map(root_label: str, note: str = "") -> RepositoryMap:
    errors = (f"root: {note}",) if note else ()
    return RepositoryMap(
        built_at=datetime.now(),
        root_label=root_label,
        modules=(),
        errors=errors,
        metadata={"empty": True},
    )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class RepositoryMapBuilder:
    """Builds a :class:`RepositoryMap` from an injected repository root."""

    def __init__(
        self,
        root,
        excludes: frozenset[str] = DEFAULT_EXCLUDES,
        max_modules: int = MAX_MODULES,
        max_errors: int = MAX_ERRORS,
        max_file_bytes: int = MAX_FILE_BYTES,
    ) -> None:
        self._root = Path(root)
        self._excludes = frozenset(excludes) | {
            part for part in excludes if part.startswith(".")
        }
        self._max_modules = max_modules
        self._max_errors = max_errors
        self._max_file_bytes = max_file_bytes

    def build(self) -> RepositoryMap:
        """Scan the tree once and return a deterministic snapshot."""
        label = self._root.name or str(self._root)
        if not self._root.is_dir():
            return _empty_map(label, "repository root is not an existing directory")

        files = self._discover()
        truncated = len(files) > self._max_modules
        files = files[: self._max_modules]

        infos: list[ModuleInfo] = []
        errors: list[str] = []
        parsed: list[tuple[ModuleInfo, ast.Module]] = []
        # Command 2 (A1): the already-read text, kept only to build bounded
        # symbol regions; released when ``build`` returns.
        module_text: dict[str, str] = {}

        for relative in files:
            module_name = self._module_name(relative)
            if not module_name:
                # Root-level __init__.py has no dotted name; skip silently.
                continue
            text, read_error = self._safe_read(relative)
            if read_error:
                errors = self._record_error(errors, f"{module_name}: {read_error}")
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError as exc:
                errors = self._record_error(
                    errors, f"{module_name}: syntax error ({exc.msg})"
                )
                continue

            info = ModuleInfo(
                module=module_name,
                path=relative.as_posix(),
                language=LANGUAGE_BY_EXTENSION.get(relative.suffix.lower(), ""),
                is_package=relative.name == "__init__.py",
                line_count=len(text.splitlines()),
                # Captured from the text ALREADY read above — no extra I/O. A
                # small module's whole source fits; a large module keeps a
                # bounded preamble and records the truncation honestly.
                source_excerpt=text[:MAX_SOURCE_EXCERPT_CHARS],
                source_truncated=len(text) > MAX_SOURCE_EXCERPT_CHARS,
            )
            parsed.append((info, tree))
            module_text[info.module] = text

        known = {info.module for info, _ in parsed}
        package_names: set[str] = set()
        for name in known:
            parts = name.split(".")
            for width in range(1, len(parts)):
                package_names.add(".".join(parts[:width]))
        internal_targets = known | package_names

        # Command 2 (A1) — one deterministic pass over the parsed trees that also
        # gathers the bounded structural relationships this map previously threw
        # away: per-name reference SITES, per-name DEFINITIONS (so an edge can be
        # resolved only when it is unambiguous) and per-definition CALL sites.
        name_freq: Counter[str] = Counter()
        name_sites: dict[str, list[tuple[str, int]]] = {}
        definitions: dict[str, list[str]] = {}
        call_sites: dict[str, list[tuple[str, int]]] = {}
        spans: dict[str, tuple[int, int]] = {}
        qualified_module: dict[str, str] = {}
        for info, tree in parsed:
            self._scan_module(
                info.module,
                tree,
                name_freq,
                name_sites,
                call_sites,
                definitions,
                spans,
                qualified_module,
            )

        # A name resolves to an edge ONLY when exactly one repo-defined symbol
        # carries it; an ambiguous name yields NO edge (never a guess).
        unambiguous = {
            name: quals[0]
            for name, quals in definitions.items()
            if len(set(quals)) == 1
        }

        # Reverse index built ONCE (never per symbol): callee name → bounded,
        # deterministically-ordered callers. An AMBIGUOUS callee name is skipped
        # entirely, so a caller is never attributed to a symbol it might not call.
        caller_index: dict[str, list[str]] = {}
        for caller in sorted(call_sites):
            for callee_name, _line in call_sites[caller]:
                resolved = unambiguous.get(callee_name)
                if not resolved or resolved == caller:
                    continue
                bucket = caller_index.setdefault(callee_name, [])
                if caller not in bucket and len(bucket) < MAX_EDGES_PER_SYMBOL:
                    bucket.append(caller)

        final_infos: list[ModuleInfo] = []
        all_symbols: list[SymbolInfo] = []
        for info, tree in parsed:
            internal, external = self._resolve_imports(
                info.module, self._extract_raw_imports(tree), internal_targets
            )
            symbols = tuple(
                self._build_symbols(
                    info.module, tree, name_freq, name_sites, call_sites,
                    caller_index, unambiguous, spans,
                )
            )
            all_symbols.extend(symbols)
            final_infos.append(
                replace(
                    info,
                    internal_imports=tuple(sorted(internal)),
                    external_imports=tuple(sorted(external)),
                    symbols=symbols,
                )
            )

        final_infos.sort(key=lambda item: item.module)
        all_symbols.sort(key=lambda item: item.qualified)
        if len(all_symbols) > MAX_SYMBOLS_TOTAL:
            all_symbols = all_symbols[:MAX_SYMBOLS_TOTAL]

        module_paths = {item.module: item.path for item in final_infos}

        # Bounded REGIONS, allocated in deterministic (module, qualified) order
        # within one total-character budget; past the budget a symbol simply has
        # no stored region (``region_of`` → None), never a partial guess.
        regions: list[SymbolRegion] = []
        region_budget = MAX_REGION_TOTAL_CHARS
        for symbol in sorted(all_symbols, key=lambda s: (s.module, s.qualified)):
            span = spans.get(symbol.qualified)
            text = module_text.get(symbol.module)
            if span is None or not text:
                continue
            region = self._region(
                symbol, text, span, module_paths.get(symbol.module, ""), region_budget
            )
            if region is None:
                break
            region_budget -= len(region.source)
            regions.append(region)

        # Flat, UNAMBIGUOUS caller → callee edges (deduplicated, deterministic).
        seen_edges: set[tuple[str, str]] = set()
        edges: list[SymbolEdge] = []
        for caller in sorted(call_sites):
            for callee_name, line in call_sites[caller]:
                callee = unambiguous.get(callee_name)
                if not callee or callee == caller:
                    continue
                key = (caller, callee)
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edges.append(
                    SymbolEdge(
                        caller=caller,
                        callee=callee,
                        module=qualified_module.get(caller, ""),
                        line=line,
                    )
                )
                if len(edges) >= MAX_EDGES_TOTAL:
                    break
            if len(edges) >= MAX_EDGES_TOTAL:
                break

        return RepositoryMap(
            built_at=datetime.now(),
            root_label=label,
            modules=tuple(final_infos),
            errors=tuple(errors[: self._max_errors]),
            truncated=truncated,
            metadata={
                "files_scanned": len(parsed) + len(errors),
                "packages": sum(1 for item in final_infos if item.is_package),
                "symbols": len(all_symbols),
                "regions": len(regions),
                "symbol_edges": len(edges),
            },
            symbols=tuple(all_symbols),
            regions=tuple(regions),
            edges=tuple(edges),
        )

    def _discover(self) -> list[Path]:
        discovered: list[Path] = []
        for path in sorted(self._root.rglob("*.py")):
            relative = path.relative_to(self._root)
            parts = relative.parts[:-1]
            if any(
                part in self._excludes or part.startswith(".")
                for part in parts
            ):
                continue
            try:
                if path.stat().st_size > self._max_file_bytes:
                    continue
            except OSError:
                continue
            discovered.append(relative)
        discovered.sort()
        return discovered

    @staticmethod
    def _module_name(relative_path: Path) -> str:
        parts = list(relative_path.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        # A __init__.py directly under the root has no dotted name (the
        # root itself is not a named package in root-relative terms).
        if not parts:
            return ""
        return ".".join(parts)

    def _safe_read(self, relative_path: Path) -> tuple[str, str]:
        from atlas.research.sources._read import safe_read_text

        try:
            text, error = safe_read_text(self._root / relative_path)
        except OSError as exc:
            return "", f"unreadable ({exc})"
        return (text, "") if not error else ("", error)

    def _record_error(self, errors: list[str], entry: str) -> list[str]:
        if len(errors) < self._max_errors:
            errors.append(entry)
        return errors

    @staticmethod
    def _extract_raw_imports(tree: ast.Module) -> list[tuple[int, str]]:
        """Return ``(level, dotted_target)`` pairs. Function-scoped imports
        are seen by ``ast.walk`` regardless of runtime reachability."""
        raw: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    raw.append((0, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    raw.append((node.level, node.module or ""))
                elif node.module:
                    raw.append((0, node.module))
        return raw[:MAX_IMPORTS_PER_MODULE]

    def _scan_module(
        self,
        module: str,
        tree: ast.Module,
        counter: "Counter[str]",
        sites: dict[str, list[tuple[str, int]]],
        call_sites: dict[str, list[tuple[str, int]]],
        definitions: dict[str, list[str]],
        spans: dict[str, tuple[int, int]],
        qualified_module: dict[str, str],
    ) -> None:
        """ONE deterministic traversal: names, reference SITES, definitions,
        spans and CALL sites — preserving the existing symbol order and bounds.

        Name tallies cover the whole tree exactly as before; a call site is
        attributed ONLY to the definition that lexically contains it, and never
        to an unregistered scope (an edge is never guessed).
        """
        defs = self._iter_definitions(module, tree)
        scopes: dict[int, str] = {}
        for qualified, name, _kind, node in defs:
            scopes[id(node)] = qualified
            if qualified in qualified_module:
                continue
            qualified_module[qualified] = module
            definitions.setdefault(name, []).append(qualified)
            span = self._definition_span(node)
            if span is not None:
                spans[qualified] = span

        def _note(name: str, line: int) -> None:
            if not name:
                return
            counter[name] += 1
            bucket = sites.setdefault(name, [])
            if len(bucket) < MAX_REFERENCE_SITES_PER_SYMBOL:
                bucket.append((module, line))

        def _visit(node: "ast.AST", current: str) -> None:
            if isinstance(node, ast.Name):
                _note(node.id, node.lineno)
            elif isinstance(node, ast.Attribute):
                _note(node.attr, node.lineno)
            elif isinstance(node, ast.Call) and current:
                func = node.func
                callee = (
                    func.id
                    if isinstance(func, ast.Name)
                    else func.attr
                    if isinstance(func, ast.Attribute)
                    else ""
                )
                if callee:
                    bucket = call_sites.setdefault(current, [])
                    if len(bucket) < MAX_EDGES_PER_SYMBOL:
                        bucket.append((callee, getattr(node, "lineno", 0)))
            for child in ast.iter_child_nodes(node):
                _visit(child, current)

        def _visit_definition(node: "ast.AST") -> None:
            """Visit a definition (signature + body) WITHOUT entering a nested
            definition's body, which is its own scope."""
            scope = scopes.get(id(node), "")
            for child in ast.iter_child_nodes(node):
                if isinstance(
                    child,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
                ):
                    _visit_definition(child)
                else:
                    _visit(child, scope)

        for node in getattr(tree, "body", ()):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                _visit_definition(node)
            else:
                _visit(node, "")

    def _iter_definitions(
        self, module: str, tree: ast.Module
    ) -> list[tuple[str, str, SymbolKind, "ast.AST"]]:
        """``(qualified, name, kind, node)`` in the SAME order/bounds as the build."""
        out: list[tuple[str, str, SymbolKind, ast.AST]] = []
        for node in getattr(tree, "body", ()):
            if isinstance(node, ast.ClassDef):
                out.append(
                    (f"{module}.{node.name}", node.name, SymbolKind.CLASS, node)
                )
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        out.append(
                            (
                                f"{module}.{node.name}.{sub.name}",
                                sub.name,
                                SymbolKind.METHOD,
                                sub,
                            )
                        )
                        if len(out) >= MAX_SYMBOLS_PER_MODULE:
                            break
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append(
                    (f"{module}.{node.name}", node.name, SymbolKind.FUNCTION, node)
                )
            if len(out) >= MAX_SYMBOLS_PER_MODULE:
                break
        return out[:MAX_SYMBOLS_PER_MODULE]

    @staticmethod
    def _definition_span(node: "ast.AST") -> tuple[int, int] | None:
        """``(start, end)`` source lines of a definition, decorators included."""
        end = getattr(node, "end_lineno", None)
        start = getattr(node, "lineno", None)
        if not isinstance(start, int) or not isinstance(end, int):
            return None
        for decorator in getattr(node, "decorator_list", ()) or ():
            deco_line = getattr(decorator, "lineno", None)
            if isinstance(deco_line, int) and deco_line < start:
                start = deco_line
        return (max(1, start), max(start, end))

    @staticmethod
    def _region(
        symbol: SymbolInfo,
        text: str,
        span: tuple[int, int],
        path: str,
        remaining: int,
    ) -> SymbolRegion | None:
        """Bounded region for one symbol, or ``None`` when the budget is spent."""
        if remaining <= 0:
            return None
        start, end = span
        lines = text.splitlines()
        if start < 1 or end > len(lines) or end < start:
            return None
        piece = "\n".join(lines[start - 1 : end])
        allowed = min(MAX_REGION_CHARS, remaining)
        return SymbolRegion(
            qualified=symbol.qualified,
            module=symbol.module,
            path=path,
            start_line=start,
            end_line=end,
            source=piece[:allowed],
            truncated=len(piece) > allowed,
        )

    def _build_symbols(
        self,
        module: str,
        tree: ast.Module,
        name_freq: "Counter[str]",
        name_sites: dict[str, list[tuple[str, int]]],
        call_sites: dict[str, list[tuple[str, int]]],
        caller_index: dict[str, list[str]],
        unambiguous: dict[str, str],
        spans: dict[str, tuple[int, int]],
    ) -> list[SymbolInfo]:
        """Extract top-level classes/functions (+ methods) with bounded signatures."""
        out: list[SymbolInfo] = []

        def _add(
            name: str, kind: SymbolKind, line: int, signature: str, parent: str = ""
        ) -> None:
            qualified = f"{module}.{parent}.{name}" if parent else f"{module}.{name}"
            span = spans.get(qualified)
            callers = sorted(
                caller
                for caller in caller_index.get(name, ())
                if caller != qualified
            )
            callees = sorted(
                {
                    callee
                    for callee_name, _line in call_sites.get(qualified, ())
                    if (callee := unambiguous.get(callee_name))
                    and callee != qualified
                }
            )
            out.append(
                SymbolInfo(
                    name=name,
                    qualified=qualified,
                    module=module,
                    kind=kind,
                    line=line,
                    signature=signature,
                    references=min(name_freq.get(name, 0), MAX_REFERENCES),
                    end_line=span[1] if span else 0,
                    reference_sites=tuple(
                        ReferenceSite(module=site_module, line=site_line, symbol=name)
                        for site_module, site_line in sorted(
                            name_sites.get(name, ())
                        )[:MAX_REFERENCE_SITES_PER_SYMBOL]
                    ),
                    callers=tuple(callers[:MAX_EDGES_PER_SYMBOL]),
                    callees=tuple(callees[:MAX_EDGES_PER_SYMBOL]),
                )
            )

        for node in getattr(tree, "body", ()):
            if isinstance(node, ast.ClassDef):
                _add(node.name, SymbolKind.CLASS, node.lineno, _class_signature(node))
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        _add(
                            sub.name,
                            SymbolKind.METHOD,
                            sub.lineno,
                            _function_signature(sub),
                            parent=node.name,
                        )
                        if len(out) >= MAX_SYMBOLS_PER_MODULE:
                            break
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _add(
                    node.name,
                    SymbolKind.FUNCTION,
                    node.lineno,
                    _function_signature(node),
                )
            if len(out) >= MAX_SYMBOLS_PER_MODULE:
                break
        return out[:MAX_SYMBOLS_PER_MODULE]

    def _resolve_imports(
        self,
        module: str,
        raw_imports: list[tuple[int, str]],
        internal_targets: set[str],
    ) -> tuple[set[str], set[str]]:
        """Resolve raw imports into internal matches and external roots."""
        internal: set[str] = set()
        external: set[str] = set()
        package_parts = module.split(".")[:-1]

        for level, target in raw_imports:
            if level:
                drop = level - 1
                base = (
                    package_parts[: len(package_parts) - drop]
                    if drop <= len(package_parts)
                    else []
                )
                candidate = ".".join(base + ([target] if target else []))
                matched = _longest_prefix_match(candidate, internal_targets)
                if matched:
                    internal.add(matched)
                # Unresolvable relative imports are ignored (hostile input).
                continue

            matched = _longest_prefix_match(target, internal_targets)
            if matched:
                internal.add(matched)
            else:
                top = target.split(".")[0]
                if top:
                    external.add(top)

        internal.discard(module)
        return internal, external


def _longest_prefix_match(candidate: str, targets: set[str]) -> str:
    """Longest known-module/package prefix of ``candidate``, or ''."""
    parts = [part for part in candidate.split(".") if part]
    for width in range(len(parts), 0, -1):
        prefix = ".".join(parts[:width])
        if prefix in targets:
            return prefix
    return ""


def _function_signature(node: "ast.FunctionDef | ast.AsyncFunctionDef") -> str:
    """Bounded, deterministic signature text for a function/method definition."""
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    try:
        args = ast.unparse(node.args)
    except Exception:
        args = ""
    return (f"{prefix}({args})")[:MAX_SIGNATURE_CHARS]


def _class_signature(node: ast.ClassDef) -> str:
    """Bounded, deterministic base-class signature text for a class definition."""
    try:
        bases = ", ".join(ast.unparse(base) for base in node.bases)
    except Exception:
        bases = ""
    return (f"({bases})" if bases else "")[:MAX_SIGNATURE_CHARS]