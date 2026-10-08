"""Atlas Evolution — bounded structural source editing (STEP 2F/2G).

A narrow, Atlas-owned structural editing capability, adapted from the researched
mechanisms (ast-grep structural rewriting, Tree-sitter/CST "surgical edit"
concepts, LibCST codemod ideas) WITHOUT embedding any of them. It is deliberately
small: one deterministic, AST-anchored transformation set over Python source.

What it does
------------
Given the EXISTING source text of one module and a bounded :class:`StructuralEdit`,
it produces the module's new full text by operating on the *syntax tree* — never
by textual search/replace:

* ``replace`` — replace one named definition (top-level function/class, a method
  inside a class, or a module-level assignment) with new source;
* ``insert_after`` — insert new source immediately after a named definition;
* ``delete`` — remove a named definition.

Guarantees (all fail-closed)
----------------------------
* **syntax preservation** — the edit is refused unless ``ast.parse`` accepts the
  RESULT, so an unparseable rewrite can never be produced;
* **exact anchor** — the target must resolve to exactly ONE definition; an
  unknown or ambiguous symbol is refused, never guessed;
* **no unrelated changes** — only the anchored line span is touched; the rest of
  the module is preserved byte-for-byte;
* **bounded** — input size, replacement size and edit count all have hard caps;
* **deterministic** — identical input yields identical output.

It writes nothing: the caller receives source text, which must still become a
``CodeChangeSet`` and pass the existing validation, sandbox and governance.
No model, no network, no I/O, standard library only.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum
from typing import Any

from atlas.evolution.development_cycle import DevelopmentNeed, SuppliedChanges

#: Hard bounds (a malformed request can never produce unbounded work).
MAX_SOURCE_CHARS: int = 400_000
MAX_REPLACEMENT_CHARS: int = 20_000
MAX_EDITS: int = 8
MAX_SYMBOL_CHARS: int = 128


class EditKind(str, Enum):
    """The bounded structural transformation vocabulary."""

    REPLACE = "replace"
    INSERT_AFTER = "insert_after"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class StructuralEdit:
    """One bounded, anchored structural edit."""

    path: str
    symbol: str
    kind: EditKind = EditKind.REPLACE
    source: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "symbol": self.symbol,
            "kind": self.kind.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class StructuralEditResult:
    """The bounded outcome of applying structural edits to one module."""

    ok: bool
    content: str = ""
    reason: str = ""
    applied: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "applied": list(self.applied),
        }


def _find_definitions(tree: ast.Module) -> dict[str, ast.AST]:
    """Map every addressable definition name to its node (deterministic).

    Addressable names are the top-level function/class/assignment names and, for
    top-level classes, their direct methods as ``Class.method``. The FIRST
    definition wins, so a name is never silently overwritten.
    """
    found: dict[str, ast.AST] = {}

    def _record(name: str, node: ast.AST) -> None:
        if name and name not in found:
            found[name] = node

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _record(node.name, node)
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        _record(f"{node.name}.{sub.name}", sub)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    _record(target.id, node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            _record(node.target.id, node)
    return found


def _span(node: ast.AST) -> tuple[int, int] | None:
    """The 1-based inclusive line span of ``node`` (``None`` when unavailable)."""
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if not isinstance(start, int) or not isinstance(end, int) or end < start:
        return None
    decorators = getattr(node, "decorator_list", None) or ()
    for decorator in decorators:
        line = getattr(decorator, "lineno", None)
        if isinstance(line, int) and line < start:
            start = line
    return start, end


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _reindent(replacement: str, indent: str) -> list[str]:
    """Apply ``indent`` to the replacement's non-empty lines (deterministic).

    The replacement's OWN relative indentation is preserved: the common base
    indentation of its first non-empty line is rebased onto ``indent``, and every
    other line keeps its offset from that base. Blank lines stay blank. When the
    replacement has no base indentation it is inserted verbatim under ``indent``
    — its internal structure (a function body, for example) is never flattened.
    """
    lines = replacement.splitlines()
    if not lines:
        return []
    base = _indent_of(next((line for line in lines if line.strip()), ""))
    out: list[str] = []
    for line in lines:
        if not line.strip():
            out.append("")
        elif base and line.startswith(base):
            out.append(indent + line[len(base):])
        else:
            out.append(indent + line)
    return out


def apply_structural_edits(
    source: Any,
    edits: Any,
    *,
    max_edits: int = MAX_EDITS,
) -> StructuralEditResult:
    """Apply bounded structural ``edits`` to ``source`` (fail-closed).

    Returns a :class:`StructuralEditResult`; on any refusal ``ok`` is ``False``
    and the caller must fall back. The original text is never returned as a
    silent success: a refusal is always explicit.
    """
    if not isinstance(source, str):
        return StructuralEditResult(False, reason="source must be a string")
    if len(source) > MAX_SOURCE_CHARS:
        return StructuralEditResult(False, reason="source exceeds the size bound")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return StructuralEditResult(False, reason=f"source does not parse ({exc.msg})")

    if edits is None:
        return StructuralEditResult(False, reason="no edits supplied")
    items = tuple(edits) if isinstance(edits, (list, tuple)) else (edits,)
    if not items:
        return StructuralEditResult(False, reason="no edits supplied")
    if len(items) > max(1, int(max_edits)):
        return StructuralEditResult(False, reason="too many edits")

    lines = source.splitlines()
    # Apply from the BOTTOM up so earlier spans stay valid.
    planned: list[tuple[int, int, str, str]] = []
    for item in items:
        if not isinstance(item, StructuralEdit):
            return StructuralEditResult(False, reason="edit must be a StructuralEdit")
        symbol = str(item.symbol or "").strip()[:MAX_SYMBOL_CHARS]
        if not symbol:
            return StructuralEditResult(False, reason="edit needs a symbol")
        replacement = item.source if isinstance(item.source, str) else ""
        if len(replacement) > MAX_REPLACEMENT_CHARS:
            return StructuralEditResult(False, reason="replacement exceeds the size bound")
        if item.kind is not EditKind.DELETE and not replacement.strip():
            return StructuralEditResult(False, reason="edit needs replacement source")
        definitions = _find_definitions(tree)
        node = definitions.get(symbol)
        if node is None:
            return StructuralEditResult(False, reason=f"symbol {symbol!r} was not found")
        span = _span(node)
        if span is None:
            return StructuralEditResult(False, reason=f"symbol {symbol!r} has no span")
        planned.append((span[0], span[1], item.kind.value, replacement))

    planned.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    applied: list[str] = []
    for start, end, kind, replacement in planned:
        indent = _indent_of(lines[start - 1]) if 0 < start <= len(lines) else ""
        if kind == EditKind.DELETE.value:
            del lines[start - 1 : end]
        elif kind == EditKind.INSERT_AFTER.value:
            lines[end:end] = _reindent(replacement, indent)
        else:
            lines[start - 1 : end] = _reindent(replacement, indent)
        applied.append(kind)

    result = "\n".join(lines)
    if source.endswith("\n"):
        result += "\n"
    try:
        ast.parse(result)
    except SyntaxError as exc:
        return StructuralEditResult(
            False, reason=f"edit would produce invalid syntax ({exc.msg})"
        )
    return StructuralEditResult(True, content=result, applied=tuple(applied))


# ---------------------------------------------------------------------------
# The supplier over the EXISTING metadata convention
# ---------------------------------------------------------------------------

#: Metadata key read by :class:`StructuralChangeSupplier`.
STRUCTURAL_KEY: str = "structural"

#: Provenance marker stamped on structurally authored changes.
STRUCTURAL_ORIGIN: str = "deterministic-structural"


class StructuralChangeSupplier:
    """Deterministic ``ChangeSupplier`` for localized existing-code edits.

    Reads ``need.metadata["structural"]`` — a list of
    ``{"path", "symbol", "kind", "source"}`` mappings, or a single mapping — and
    produces the module's new FULL text by applying the bounded structural edits
    to the current on-disk source. Nothing else in the file changes.

    Fail-closed: an unreadable path, an unresolvable symbol, an unsafe path, an
    oversized payload or an edit that would break syntax raises ``ValueError``
    so the controller refuses the whole change rather than shipping a broken
    file. It never writes anything itself.
    """

    #: Maximum authored files (bounded; the controller additionally bounds them).
    MAX_FILES: int = 4

    @property
    def origin(self) -> str:
        return STRUCTURAL_ORIGIN

    def __init__(self, root: Any | None = None, *, base_source: Any | None = None) -> None:
        self._root = root
        #: Command 2 (W6) — optional explicit base source per path. When a path is
        #: present here, ITS text is edited instead of the on-disk file, which is
        #: what a REPAIR needs (the CURRENT failing content, not the pristine
        #: repository content). Absent or empty keeps today's behaviour exactly.
        self._base_source = base_source if isinstance(base_source, dict) else None

    def _repository_root(self):
        import pathlib

        if self._root is not None:
            return pathlib.Path(self._root)
        return pathlib.Path(__file__).resolve().parents[2]

    def supply_changes(self, need: DevelopmentNeed) -> SuppliedChanges | None:
        metadata = getattr(need, "metadata", None)
        if not isinstance(metadata, dict):
            return None
        raw = metadata.get(STRUCTURAL_KEY)
        if raw is None:
            return None
        items = tuple(raw) if isinstance(raw, (list, tuple)) else (raw,)
        if not items:
            return None
        if len(items) > self.MAX_FILES:
            raise ValueError("too many structural changes")

        from atlas.evolution.autonomy.code_sandbox import CodeChangeSet

        root = self._repository_root()
        by_path: dict[str, list[StructuralEdit]] = {}
        order: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("malformed 'structural' entry (must be an object)")
            path = str(item.get("path") or "").strip().replace("\\", "/")
            symbol = str(item.get("symbol") or "").strip()
            if not path or not symbol:
                raise ValueError("structural entry needs 'path' and 'symbol'")
            CodeChangeSet.validate_path(path)
            if path not in by_path:
                by_path[path] = []
                order.append(path)
            try:
                kind = EditKind(str(item.get("kind") or "replace").strip().lower())
            except ValueError as exc:
                raise ValueError(f"unsupported structural kind {item.get('kind')!r}") from exc
            by_path[path].append(
                StructuralEdit(
                    path=path,
                    symbol=symbol,
                    kind=kind,
                    source=str(item.get("source") or ""),
                    reason=str(item.get("reason") or "")[:200],
                )
            )

        changes: list[tuple[str, str]] = []
        for path in order:
            explicit = (
                self._base_source.get(path) if self._base_source is not None else None
            )
            if isinstance(explicit, str) and explicit.strip():
                # An explicitly supplied base is authoritative: a REPAIR edits the
                # CURRENT failing content, never the pristine repository file.
                original = explicit
            else:
                target = (root / path).resolve()
                try:
                    target.relative_to(root.resolve())
                except ValueError as exc:
                    raise ValueError(f"path escapes the repository: {path}") from exc
                try:
                    original = target.read_text(
                        encoding="utf-8", errors="surrogateescape"
                    )
                except OSError as exc:
                    raise ValueError(f"cannot read {path}: {type(exc).__name__}") from exc
            result = apply_structural_edits(original, by_path[path])
            if not result.ok:
                raise ValueError(f"structural edit refused for {path}: {result.reason}")
            changes.append((path, result.content))

        # The plan's already-selected verification tests travel the SAME
        # convention the deterministic sibling uses (``metadata["test_files"]``),
        # so the governed verification leg receives the exact tests the plan
        # selected instead of falling through to the empty sandbox default.
        # Bounded by the controller's existing ``max_test_files``; malformed
        # payloads raise so the whole change fails closed.
        raw_tests = metadata.get("test_files", {})
        tests: list[tuple[str, str]] = []
        if isinstance(raw_tests, dict):
            tests = [(str(path), str(content)) for path, content in raw_tests.items()]
        elif isinstance(raw_tests, list):
            for item in raw_tests:
                if (
                    not isinstance(item, dict)
                    or "path" not in item
                    or "content" not in item
                ):
                    raise ValueError("malformed test_files entry")
                tests.append((str(item["path"]), str(item["content"])))
        elif raw_tests:
            raise ValueError("malformed test_files payload")

        raw_context = metadata.get("repository_context", {})
        context: list[tuple[str, str]] = []
        if isinstance(raw_context, dict):
            context = [(str(p), str(c)) for p, c in raw_context.items()]
        elif isinstance(raw_context, list):
            for item in raw_context:
                if (
                    not isinstance(item, dict)
                    or "path" not in item
                    or "content" not in item
                ):
                    raise ValueError("malformed repository_context entry")
                context.append((str(item["path"]), str(item["content"])))
        elif raw_context:
            raise ValueError("malformed repository_context payload")

        return SuppliedChanges(
            code_changes=tuple(changes),
            test_files=tuple(tests),
            repository_context=tuple(context),
            origin=self.origin,
            confidence=1.0,
            notes="deterministic structural edit",
        )


def structural_spec(path: str, symbol: str, source: str, *, kind: str = "replace") -> dict:
    """Convenience builder for one structural metadata entry."""
    return {"path": path, "symbol": symbol, "kind": kind, "source": source}


__all__ = [
    "EditKind",
    "STRUCTURAL_KEY",
    "STRUCTURAL_ORIGIN",
    "StructuralChangeSupplier",
    "StructuralEdit",
    "StructuralEditResult",
    "apply_structural_edits",
    "structural_spec",
]
