"""Atlas Evolution — the plan -> authoring bridge for EXPLICITLY SUPPLIED edits.

The demonstrated gap was:

    resolved ChangePlan
        -> NO existing plan -> author bridge

:class:`~atlas.evolution.structural_editor.StructuralChangeSupplier` can already
apply bounded structural edits, but only when
``need.metadata["structural"]`` is populated — and nothing populated it from a
request. This module is that bridge, and it is deliberately NARROW.

Supported class (the ONLY class)
--------------------------------
A request that explicitly SUPPLIES its own replacement content in a fenced code
block and names the symbol to change::

    Update the explicitly named helper `add` in widget.py:

    ```python
    def add(a, b):
        return a + b
    ```

Nothing is inferred and nothing is generated: the replacement body is copied
verbatim from the request, and the symbol/edit-kind come from the request's own
cues. Turning prose WITHOUT supplied code into an implementation stays out of
scope.

Fail-closed
-----------
Refused, with an explicit reason, whenever:

* the localization is not RESOLVED (ambiguous or unresolved);
* the request supplies no code block, or more than one;
* the request names no target symbol, or more than one;
* the supplied symbol is not part of the localized target;
* the edit kind is unsupported or the replacement is empty for a non-delete.

A refusal returns NO entry, so no authoring can happen at all.

Authority
---------
The result is a PROPOSAL input, never permission. It authorizes nothing, writes
nothing, executes nothing and is never auto-promoted; the produced change still
has to pass ``CodeChangeSet`` validation, the sandbox, verification, approval and
promotion. No model, no network, no I/O, standard library only, deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from atlas.evolution.structural_editor import STRUCTURAL_KEY, EditKind, structural_spec

#: Bounds.
MAX_BLOCKS: int = 1
MAX_SYMBOLS: int = 8
MAX_BACKTICK_CHARS: int = 128

#: A fenced code block; the language tag is accepted but not required to be python.
_FENCE_RE = re.compile(
    r"```[ \t]*(?P<lang>[A-Za-z0-9_+\-]*)[ \t]*\r?\n(?P<body>.*?)```",
    re.DOTALL,
)
#: Backticked spans — the request's own way of naming a symbol.
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
#: Delete cues.
_DELETE_CUES: tuple[str, ...] = ("delete", "remove", "drop")
#: Insert-after cues.
_INSERT_CUES: tuple[str, ...] = ("insert after", "insert immediately after", "add after")


@dataclass(frozen=True, slots=True)
class SuppliedEdit:
    """The outcome of reading an explicit supplied edit out of a request.

    ``ok`` is True only when every required piece was present AND the supplied
    symbol belongs to the localized target. ``entry`` is the
    ``metadata["structural"]`` mapping the existing supplier already reads.
    """

    ok: bool
    reason: str = ""
    entry: dict[str, Any] | None = None
    symbol: str = ""
    kind: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "symbol": self.symbol,
            "kind": self.kind,
            "entry": dict(self.entry) if self.entry else None,
            # A bridge result is a proposal input, never permission.
            "authorized": False,
            "executed": False,
        }


def _code_blocks(request: str) -> list[str]:
    return [match.group("body") for match in _FENCE_RE.finditer(request)]


def _named_symbols(request: str) -> list[str]:
    """Backticked symbols the request names, in order (deterministic)."""
    without_blocks = _FENCE_RE.sub(" ", request)
    out: list[str] = []
    for raw in _BACKTICK_RE.findall(without_blocks):
        token = raw.strip()[:MAX_BACKTICK_CHARS]
        if token and token not in out:
            out.append(token)
    return out[:MAX_SYMBOLS]


def _kind_for(request: str) -> EditKind:
    lowered = request.lower()
    if any(cue in lowered for cue in _DELETE_CUES):
        return EditKind.DELETE
    if any(cue in lowered for cue in _INSERT_CUES):
        return EditKind.INSERT_AFTER
    return EditKind.REPLACE


def _matches(supplied: str, localization: Any) -> bool:
    """Whether ``supplied`` names a symbol of the localized target.

    Matches the symbol's short name or its qualified form's tail, exactly — no
    fuzzy matching, so a near-miss can never be accepted.
    """
    context = getattr(localization, "context", None)
    candidates = list(getattr(context, "symbols", ()) or ())
    resolved = getattr(localization, "symbol", None)
    if resolved is not None:
        candidates.append(resolved)
    for item in candidates:
        name = str(getattr(item, "name", "") or "")
        qualified = str(getattr(item, "qualified", "") or "")
        tail = qualified.rsplit(".", 1)[-1] if qualified else ""
        if supplied in (name, qualified, tail):
            return True
    return False


def supplied_structural_edit(
    request: Any,
    localization: Any = None,
) -> SuppliedEdit:
    """Read an EXPLICIT supplied structural edit out of ``request`` (fail-closed).

    Returns a :class:`SuppliedEdit`. Anything missing, ambiguous or mismatched
    yields ``ok=False`` with an explicit reason and NO entry.
    """
    if not isinstance(request, str) or not request.strip():
        return SuppliedEdit(False, "the request is empty")

    blocks = _code_blocks(request)
    if not blocks:
        return SuppliedEdit(False, "the request supplies no code block")
    if len(blocks) > MAX_BLOCKS:
        return SuppliedEdit(
            False, "the request supplies more than one code block"
        )
    source = blocks[0]
    kind = _kind_for(request)
    if kind is not EditKind.DELETE and not source.strip():
        return SuppliedEdit(False, "the supplied replacement is empty")

    if localization is None:
        return SuppliedEdit(False, "no localization was supplied")
    status = str(getattr(getattr(localization, "status", None), "value", "") or "")
    if status != "resolved" or not getattr(localization, "target", ""):
        return SuppliedEdit(
            False,
            f"the target could not be localized with evidence ({status or 'unresolved'})",
        )

    path = ""
    candidates = list(getattr(localization, "candidates", ()) or ())
    if candidates:
        path = str(getattr(candidates[0], "path", "") or "")
    if not path:
        return SuppliedEdit(False, "the localized target has no repository path")

    supplied_symbols = [
        token for token in _named_symbols(request) if not token.endswith(".py")
    ]
    matched = [token for token in supplied_symbols if _matches(token, localization)]
    if not matched:
        if len(supplied_symbols) == 1:
            return SuppliedEdit(
                False,
                f"supplied symbol {supplied_symbols[0]!r} is not part of the "
                f"localized target {getattr(localization, 'target', '')!r}",
            )
        if not supplied_symbols:
            return SuppliedEdit(False, "the request names no target symbol")
        return SuppliedEdit(
            False, "the request names more than one target symbol"
        )
    if len(matched) > 1:
        return SuppliedEdit(False, "the request names more than one target symbol")
    symbol = matched[0].rsplit(".", 1)[-1]

    return SuppliedEdit(
        True,
        reason="explicit supplied structural edit",
        entry=structural_spec(path, symbol, source, kind=kind.value),
        symbol=symbol,
        kind=kind.value,
    )


__all__ = ["SuppliedEdit", "STRUCTURAL_KEY", "supplied_structural_edit"]
