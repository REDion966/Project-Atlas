"""Atlas Evolution — deterministic CHANGE GUARDS (Command 2, W3/A2).

The governed loop already applies a change and then asks pytest whether it
worked. That answers "did the tests pass", never "was the change LEGAL": a
change could touch a second file, delete a definition the tests do not happen to
exercise, or be a no-op that trivially "passes" everything.

This module adds the missing question. :func:`characterise_change` is a pure,
bounded, deterministic characterisation of what a change ACTUALLY did — which
paths moved, whether anything moved outside the one authorized target, the line
delta per file, which top-level definitions disappeared, and which top-level
signatures lost a parameter — and it FAILS CLOSED: malformed input, an
unparseable file, an oversized change, a no-op or any safety violation yields
``ok=False`` with bounded reasons.

It is deliberately NOT a semantic compatibility analyzer. It reads nothing,
writes nothing, runs nothing, and never decides whether a change should be
applied: it produces evidence the loop uses to REFUSE a change before pytest is
asked for a verdict.

Pure logic. Deterministic. Bounded. Fail-closed. Standard library only.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

#: Bounded caps (module-level, audited here — never per request).
MAX_PATHS: int = 8
MAX_REASON_CHARS: int = 200
MAX_REASONS: int = 12
MAX_CONTENT_CHARS: int = 2_000_000
MAX_SIGNATURES: int = 32
MAX_REMOVED_DEFINITIONS: int = 32

#: Metadata keys the loop/diagnostic read for guard evidence.
GUARD_FAILED_KEY: str = "guard_failed"
CHANGE_CHARACTERISATION_KEY: str = "change_characterisation"
#: The loop's ``test_outcome`` for a change the guard refused. It is NOT a
#: verification verdict: no pytest was run, so it can never be attributed as a
#: ``pass_to_fail`` / ``fail_to_fail`` verification transition.
GUARD_FAILED_OUTCOME: str = "guard_failed"


@dataclass(frozen=True, slots=True)
class ChangeCharacterisation:
    """Bounded, deterministic characterisation of one applied change."""

    paths: tuple[str, ...] = ()
    out_of_target: tuple[str, ...] = ()
    per_file_line_delta: tuple[tuple[str, int], ...] = ()
    removed_definitions: tuple[str, ...] = ()
    signature_changes: tuple[str, ...] = ()
    structurally_valid: bool = True
    bounded: bool = True
    ok: bool = False
    reasons: tuple[str, ...] = ()
    #: True when the ONLY finding is that nothing changed. A no-op is REFUSED
    #: (``ok`` is False) but it is not a SAFETY violation: the existing
    #: verification attribution already models it honestly as ``pass_to_pass``,
    #: so the loop records the characterisation without stopping the pipeline.
    no_op: bool = False

    @property
    def refused(self) -> bool:
        """True when the change was characterised AND refused."""
        return not self.ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "paths": list(self.paths),
            "out_of_target": list(self.out_of_target),
            "per_file_line_delta": [list(item) for item in self.per_file_line_delta],
            "removed_definitions": list(self.removed_definitions),
            "signature_changes": list(self.signature_changes),
            "structurally_valid": self.structurally_valid,
            "bounded": self.bounded,
            "ok": self.ok,
            "no_op": self.no_op,
            "reasons": list(self.reasons),
        }


def _refuse(
    reasons: list[str],
    *,
    structurally_valid: bool = True,
    bounded: bool = True,
    paths: tuple[str, ...] = (),
    out_of_target: tuple[str, ...] = (),
    deltas: tuple[tuple[str, int], ...] = (),
    removed: tuple[str, ...] = (),
    signatures: tuple[str, ...] = (),
    no_op: bool = False,
) -> ChangeCharacterisation:
    return ChangeCharacterisation(
        paths=paths,
        out_of_target=out_of_target,
        per_file_line_delta=deltas,
        removed_definitions=removed,
        signature_changes=signatures,
        structurally_valid=structurally_valid,
        bounded=bounded,
        ok=False,
        reasons=tuple(reason[:MAX_REASON_CHARS] for reason in reasons[:MAX_REASONS]),
        no_op=no_op,
    )


def _pairs(source: Any) -> dict[str, str] | None:
    """Normalize a before/after payload into ``{path: content}`` (or ``None``)."""
    if source is None:
        return {}
    if isinstance(source, dict):
        out: dict[str, str] = {}
        for path, content in source.items():
            if not isinstance(path, str) or not isinstance(content, str):
                return None
            key = path.strip().replace("\\", "/")
            if not key:
                return None
            out[key] = content
        return out
    if isinstance(source, (list, tuple)):
        out = {}
        for item in source:
            if isinstance(item, dict):
                path = item.get("path")
                content = item.get("content")
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                path, content = item
            else:
                return None
            if not isinstance(path, str) or not isinstance(content, str):
                return None
            key = path.strip().replace("\\", "/")
            if not key:
                return None
            out[key] = content
        return out
    return None


def _top_level_definitions(source: str) -> dict[str, str] | None:
    """``name -> signature`` for top-level definitions, or ``None`` if unparseable."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, TypeError, MemoryError):
        return None
    found: dict[str, str] = {}
    for node in getattr(tree, "body", ()):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found[node.name] = _signature(node)
        elif isinstance(node, ast.ClassDef):
            found[node.name] = _class_signature(node)
    return found


def _signature(node: "ast.FunctionDef | ast.AsyncFunctionDef") -> str:
    """Parameter NAMES only (a removed parameter is a breaking change)."""
    names: list[str] = []
    args = getattr(node, "args", None)
    if args is not None:
        for group in ("posonlyargs", "args", "kwonlyargs"):
            for arg in getattr(args, group, ()) or ():
                name = str(getattr(arg, "arg", "") or "")
                if name:
                    names.append(name)
    return ",".join(names)


def _class_signature(node: ast.ClassDef) -> str:
    try:
        return ", ".join(ast.unparse(base) for base in node.bases)
    except Exception:  # noqa: BLE001 — an unrenderable base is not a change
        return ""


def _line_delta(before: str, after: str) -> int:
    return len(after.splitlines()) - len(before.splitlines())


def characterise_change(
    *,
    base: Any,
    applied: Any,
    target: str = "",
    max_paths: int = MAX_PATHS,
    max_reason_chars: int = MAX_REASON_CHARS,
) -> ChangeCharacterisation:
    """Characterise the change from ``base`` to ``applied`` (pure; fail-closed).

    ``base`` is the PRE-change content per path (the original repository content
    the loop already seeds) and ``applied`` is the change's content per path.
    ``target`` is the ONE authorized path; an empty ``target`` means the caller
    declares no containment claim and only the structural checks apply.
    """
    del max_reason_chars  # bounded by the module constant; part of the surface
    if not isinstance(max_paths, int) or max_paths <= 0:
        max_paths = MAX_PATHS

    before = _pairs(base)
    after = _pairs(applied)
    if before is None or after is None:
        return _refuse(["malformed change input (expected path -> content)"])

    if not after:
        return _refuse(["no applied content was supplied"])

    if len(after) > max_paths:
        return _refuse(
            [f"change touches {len(after)} paths (bound {max_paths})"],
            bounded=False,
            paths=tuple(sorted(after)),
        )

    for path, content in after.items():
        if len(content) > MAX_CONTENT_CHARS:
            return _refuse(
                [f"content for {path!r} exceeds the size bound"],
                bounded=False,
                paths=tuple(sorted(after)),
            )

    authorized = str(target or "").strip().replace("\\", "/")
    out_of_target = tuple(
        sorted(path for path in after if authorized and path != authorized)
    )

    changed = tuple(
        sorted(path for path, content in after.items() if before.get(path) != content)
    )
    deltas = tuple(
        (path, _line_delta(before.get(path, ""), after[path])) for path in changed
    )

    reasons: list[str] = []
    if out_of_target:
        reasons.append(
            "the change modifies path(s) outside the single authorized target: "
            + ", ".join(out_of_target)
        )

    if not changed:
        return _refuse(
            ["the change is a no-op (no path content differs)"],
            paths=tuple(sorted(after)),
            out_of_target=out_of_target,
            deltas=deltas,
            no_op=True,
        )

    removed: list[str] = []
    signatures: list[str] = []
    for path in changed:
        original = before.get(path)
        if original is None:
            # A NEW file: nothing to remove or break, nothing to compare.
            continue
        base_defs = _top_level_definitions(original)
        new_defs = _top_level_definitions(after[path])
        if base_defs is None or new_defs is None:
            return _refuse(
                [f"{path!r} does not parse before or after the change"],
                structurally_valid=False,
                paths=tuple(sorted(after)),
                out_of_target=out_of_target,
                deltas=deltas,
            )
        for name in sorted(base_defs):
            if name not in new_defs:
                removed.append(f"{path}::{name}")
                continue
            old_names = {part for part in base_defs[name].split(",") if part}
            new_names = {part for part in new_defs[name].split(",") if part}
            lost = old_names - new_names
            if lost:
                signatures.append(
                    f"{path}::{name} lost parameter(s) {', '.join(sorted(lost))}"
                )

    if removed:
        reasons.append(
            "the change removes top-level definition(s): " + ", ".join(removed[:MAX_REMOVED_DEFINITIONS])
        )
    if signatures:
        reasons.append(
            "the change removes parameter(s) from an existing top-level "
            "definition: " + "; ".join(signatures[:MAX_SIGNATURES])
        )

    if reasons:
        return _refuse(
            reasons,
            paths=tuple(sorted(after)),
            out_of_target=out_of_target,
            deltas=deltas,
            removed=tuple(removed[:MAX_REMOVED_DEFINITIONS]),
            signatures=tuple(signatures[:MAX_SIGNATURES]),
        )

    return ChangeCharacterisation(
        paths=tuple(sorted(after)),
        out_of_target=(),
        per_file_line_delta=deltas,
        removed_definitions=(),
        signature_changes=(),
        structurally_valid=True,
        bounded=True,
        ok=True,
        reasons=(),
    )


def guard_metadata(characterisation: ChangeCharacterisation) -> dict[str, Any]:
    """The bounded metadata a refused change contributes to its outcome."""
    return {
        GUARD_FAILED_KEY: True,
        CHANGE_CHARACTERISATION_KEY: characterisation.to_dict(),
    }


def was_guard_refused(outcome: Any) -> bool:
    """True when ``outcome`` records a change the guard refused."""
    metadata = getattr(outcome, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    if metadata.get(GUARD_FAILED_KEY) is True:
        return True
    return str(getattr(outcome, "test_outcome", "") or "").strip() == GUARD_FAILED_OUTCOME


def guard_reasons(outcome: Any) -> tuple[str, ...]:
    """The bounded refusal reasons recorded on ``outcome`` (or ``()``)."""
    metadata = getattr(outcome, "metadata", None)
    if not isinstance(metadata, dict):
        return ()
    payload = metadata.get(CHANGE_CHARACTERISATION_KEY)
    if not isinstance(payload, dict):
        return ()
    reasons = payload.get("reasons")
    if not isinstance(reasons, (list, tuple)):
        return ()
    return tuple(str(item)[:MAX_REASON_CHARS] for item in reasons[:MAX_REASONS])


__all__ = [
    "CHANGE_CHARACTERISATION_KEY",
    "GUARD_FAILED_KEY",
    "GUARD_FAILED_OUTCOME",
    "ChangeCharacterisation",
    "characterise_change",
    "guard_metadata",
    "guard_reasons",
    "was_guard_refused",
]
