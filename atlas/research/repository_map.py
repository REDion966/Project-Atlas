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
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
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
    """One structurally-extracted definition (bounded; deterministic)."""

    name: str
    qualified: str
    module: str
    kind: SymbolKind
    line: int
    signature: str = ""
    references: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "qualified": self.qualified,
            "module": self.module,
            "kind": self.kind.value,
            "line": self.line,
            "signature": self.signature,
            "references": self.references,
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

    def _module_index(self) -> dict[str, ModuleInfo]:
        return {info.module: info for info in self.modules}

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
            )
            parsed.append((info, tree))

        known = {info.module for info, _ in parsed}
        package_names: set[str] = set()
        for name in known:
            parts = name.split(".")
            for width in range(1, len(parts)):
                package_names.add(".".join(parts[:width]))
        internal_targets = known | package_names

        # Bounded repo-wide name-reference frequency (one deterministic pass),
        # used only to ORDER symbols by relevance — never for semantics.
        name_freq: Counter[str] = Counter()
        for _info, tree in parsed:
            self._tally_names(tree, name_freq)

        final_infos: list[ModuleInfo] = []
        all_symbols: list[SymbolInfo] = []
        for info, tree in parsed:
            internal, external = self._resolve_imports(
                info.module, self._extract_raw_imports(tree), internal_targets
            )
            symbols = tuple(self._build_symbols(info.module, tree, name_freq))
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
            },
            symbols=tuple(all_symbols),
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

    @staticmethod
    def _tally_names(tree: ast.Module, counter: "Counter[str]") -> None:
        """Tally identifier occurrences (bounded, deterministic relevance signal)."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                counter[node.id] += 1
            elif isinstance(node, ast.Attribute):
                counter[node.attr] += 1

    def _build_symbols(
        self,
        module: str,
        tree: ast.Module,
        name_freq: "Counter[str]",
    ) -> list[SymbolInfo]:
        """Extract top-level classes/functions (+ methods) with bounded signatures."""
        out: list[SymbolInfo] = []

        def _add(
            name: str, kind: SymbolKind, line: int, signature: str, parent: str = ""
        ) -> None:
            qualified = f"{module}.{parent}.{name}" if parent else f"{module}.{name}"
            out.append(
                SymbolInfo(
                    name=name,
                    qualified=qualified,
                    module=module,
                    kind=kind,
                    line=line,
                    signature=signature,
                    references=min(name_freq.get(name, 0), MAX_REFERENCES),
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