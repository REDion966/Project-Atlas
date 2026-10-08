"""Atlas Evolution — bounded, deterministic FAULT LOCALIZATION (Command 4).

When a governed change fails verification, Atlas already knows a great deal:
which paths the change touched (the change guard), whether the failure is even
the change's fault (verification attribution), which tests judged it (the plan's
held-out verification set), and the whole structural neighbourhood of the
touched modules (symbol regions, callers/callees, import relations). What it did
NOT have is a way to turn that evidence into a RANKED list of suspect locations.

This module is that missing step, and nothing more. It is pure, bounded,
read-only and model-free: it reads evidence Atlas already holds and returns
SUSPECTS WITH REASONS. It is not a decision, not a diagnosis, not a repair, and
not permission — the repair path still authors a bounded change, the sandbox
still verifies it, and approval and promotion are untouched.

Why the ranking is honest
-------------------------
Every suspect carries the EVIDENCE that produced it (a changed symbol beats a
changed module beats a caller beats a callee beats an import neighbour), so the
ordering is auditable rather than mysterious, and an empty input fails closed to
an empty result rather than inventing a suspect.

Deliberately NOT implemented: SBFL/Ochiai spectra, mutation testing, or a
model-based ranker. Those would add machinery Atlas has no evidence it needs;
the deterministic graph + change evidence is the bounded mechanism.

Standard library only. No I/O. Deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

#: Bounds (audit here, never per request).
DEFAULT_MAX_SUSPECTS: int = 8
MAX_SUSPECTS_LIMIT: int = 32
MAX_CHANGED_PATHS: int = 16
MAX_REASONS: int = 6
MAX_REASON_CHARS: int = 200

#: Deterministic evidence weights. A changed symbol is the strongest signal
#: available; each further relationship is weaker, and the weights are fixed here
#: so a ranking is reproducible and auditable.
_W_CHANGED_SYMBOL: float = 1.00
_W_CHANGED_MODULE: float = 0.60
_W_CALLER: float = 0.45
_W_CALLEE: float = 0.35
_W_TEST_REFERENCED: float = 0.30
_W_IMPORT_NEIGHBOUR: float = 0.20

#: Bounded reason vocabulary (a caller never has to parse prose).
REASON_CHANGED_SYMBOL: str = "the change modified this symbol"
REASON_CHANGED_MODULE: str = "the change modified this module"
REASON_CALLER: str = "this symbol calls the changed symbol"
REASON_CALLEE: str = "the changed symbol calls this symbol"
REASON_TEST_REFERENCED: str = "a selected verification test imports this module"
REASON_NEIGHBOUR: str = "this module is an import neighbour of a changed module"


class SuspectKind(str, Enum):
    """WHY a location is suspect (bounded, auditable evidence classes)."""

    CHANGED_SYMBOL = "changed_symbol"
    CHANGED_MODULE = "changed_module"
    CALLER_OF_CHANGED = "caller_of_changed"
    CALLEE_OF_CHANGED = "callee_of_changed"
    TEST_REFERENCED = "test_referenced"
    IMPORT_NEIGHBOUR = "import_neighbour"


@dataclass(frozen=True, slots=True)
class SuspectLocation:
    """One ranked suspect location with the evidence that produced it."""

    qualified: str = ""
    module: str = ""
    path: str = ""
    score: float = 0.0
    kinds: tuple[SuspectKind, ...] = ()
    reasons: tuple[str, ...] = ()
    start_line: int = 0
    end_line: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "qualified": self.qualified,
            "module": self.module,
            "path": self.path,
            "score": round(self.score, 6),
            "kinds": [kind.value for kind in self.kinds],
            "reasons": list(self.reasons),
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


@dataclass(frozen=True, slots=True)
class FaultLocalization:
    """The bounded result: ranked suspects, with the inputs they came from."""

    suspects: tuple[SuspectLocation, ...] = ()
    changed_modules: tuple[str, ...] = ()
    failure_category: str = ""
    verify_target: str = ""
    truncated: bool = False
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def available(self) -> bool:
        return bool(self.suspects)

    def top(self) -> SuspectLocation | None:
        return self.suspects[0] if self.suspects else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "suspects": [suspect.to_dict() for suspect in self.suspects],
            "changed_modules": list(self.changed_modules),
            "failure_category": self.failure_category,
            "verify_target": self.verify_target,
            "truncated": self.truncated,
            "reasons": list(self.reasons),
            "available": self.available,
        }


def module_of_path(path: Any) -> str:
    """A repository path's dotted module name (``""`` when it is not a module)."""
    text = str(path or "").strip().replace("\\", "/")
    if not text.endswith(".py"):
        return ""
    text = text[:-3]
    if text.endswith("/__init__"):
        text = text[: -len("/__init__")]
    return text.strip("/").replace("/", ".")


def _seq(value: Any, limit: int = MAX_CHANGED_PATHS) -> tuple:
    """A bounded, iterable view of ``value`` that NEVER raises.

    A string is one item (not a sequence of characters), a non-iterable is empty,
    and a long/generated input is stopped at ``limit`` so a hostile caller cannot
    force unbounded work.
    """
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    try:
        iterator = iter(value)
    except TypeError:
        return ()
    out: list[Any] = []
    for item in iterator:
        out.append(item)
        if len(out) >= limit:
            break
    return tuple(out)


def _call(repository_map: Any, name: str, *args: Any) -> Any:
    """Call an optional map query, returning ``None`` on any failure."""
    method = getattr(repository_map, name, None)
    if not callable(method):
        return None
    try:
        return method(*args)
    except Exception:  # noqa: BLE001 — a broken query is absent evidence
        return None


def _module_path(repository_map: Any, module: str) -> str:
    for info in getattr(repository_map, "modules", ()) or ():
        if str(getattr(info, "module", "") or "") == module:
            return str(getattr(info, "path", "") or "")
    return ""


class _Accumulator:
    """Deterministic suspect accumulation (scores add, evidence is deduped)."""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}

    def add(
        self,
        qualified: str,
        *,
        module: str = "",
        weight: float,
        kind: SuspectKind,
        reason: str,
    ) -> None:
        key = qualified or module
        if not key:
            return
        entry = self._entries.get(key)
        if entry is None:
            entry = {
                "qualified": qualified,
                "module": module,
                "score": 0.0,
                "kinds": [],
                "reasons": [],
            }
            self._entries[key] = entry
        entry["score"] += weight
        if kind not in entry["kinds"]:
            entry["kinds"].append(kind)
        if reason not in entry["reasons"]:
            entry["reasons"].append(reason)

    def ranked(self) -> list[dict[str, Any]]:
        # Deterministic: strongest first, then qualified name, then module.
        return sorted(
            self._entries.values(),
            key=lambda item: (
                -item["score"],
                str(item["qualified"]),
                str(item["module"]),
            ),
        )


def localize_fault(
    *,
    repository_map: Any = None,
    changed_paths: Any = (),
    changed_symbols: Any = (),
    failure_category: str = "",
    verify_target: str = "",
    max_suspects: int = DEFAULT_MAX_SUSPECTS,
) -> FaultLocalization:
    """Rank suspect locations for a failed change (pure; never raises).

    ``changed_paths`` / ``changed_symbols`` are the change-guard evidence;
    ``verify_target`` is the plan's bounded verification test; everything else is
    derived from the repository graph the map already holds. With no evidence the
    result is empty (``available`` is False) — a suspect is never invented.
    """
    if not isinstance(max_suspects, int) or max_suspects <= 0:
        max_suspects = DEFAULT_MAX_SUSPECTS
    max_suspects = min(max_suspects, MAX_SUSPECTS_LIMIT)

    category = str(failure_category or "")[:MAX_REASON_CHARS]
    target = str(verify_target or "")

    if repository_map is None:
        return FaultLocalization(
            failure_category=category,
            verify_target=target,
            reasons=("no repository map is available",),
        )

    paths: list[str] = []
    for path in _seq(changed_paths):
        text = str(path or "").strip().replace("\\", "/")
        if text and text not in paths:
            paths.append(text)

    modules: list[str] = []
    for path in paths:
        module = module_of_path(path)
        if module and module not in modules:
            modules.append(module)

    symbols: list[str] = []
    for symbol in _seq(changed_symbols):
        text = str(symbol or "").strip()
        if text and text not in symbols:
            symbols.append(text)

    if not modules and not symbols:
        return FaultLocalization(
            failure_category=category,
            verify_target=target,
            reasons=("no change evidence was supplied",),
        )

    accumulator = _Accumulator()

    # 1. Named changed symbols: the strongest available signal.
    for symbol in symbols:
        entry = None
        for candidate in getattr(repository_map, "symbols", ()) or ():
            if str(getattr(candidate, "qualified", "") or "") == symbol:
                entry = candidate
                break
        module = str(getattr(entry, "module", "") or "") if entry is not None else ""
        accumulator.add(
            symbol,
            module=module,
            weight=_W_CHANGED_SYMBOL,
            kind=SuspectKind.CHANGED_SYMBOL,
            reason=REASON_CHANGED_SYMBOL,
        )

    # 2. Changed modules.
    for module in modules:
        accumulator.add(
            module,
            module=module,
            weight=_W_CHANGED_MODULE,
            kind=SuspectKind.CHANGED_MODULE,
            reason=REASON_CHANGED_MODULE,
        )

    # 3. Structural neighbours of the changed SYMBOLS (callers / callees).
    for symbol in symbols:
        for caller in _call(repository_map, "callers_of", symbol) or ():
            accumulator.add(
                str(caller),
                module="",
                weight=_W_CALLER,
                kind=SuspectKind.CALLER_OF_CHANGED,
                reason=REASON_CALLER,
            )
        for callee in _call(repository_map, "callees_of", symbol) or ():
            accumulator.add(
                str(callee),
                module="",
                weight=_W_CALLEE,
                kind=SuspectKind.CALLEE_OF_CHANGED,
                reason=REASON_CALLEE,
            )

    # 4. Modules the bounded verification test imports.
    test_module = module_of_path(target) or target.replace("/", ".").removesuffix(".py")
    if test_module:
        for imported in _call(repository_map, "dependencies_of", test_module) or ():
            text = str(imported or "")
            if text:
                accumulator.add(
                    text,
                    module=text,
                    weight=_W_TEST_REFERENCED,
                    kind=SuspectKind.TEST_REFERENCED,
                    reason=REASON_TEST_REFERENCED,
                )

    # 5. Import neighbours of the changed modules (blast radius).
    for module in modules:
        for neighbour in _call(repository_map, "dependents_of", module) or ():
            text = str(neighbour or "")
            if text:
                accumulator.add(
                    text,
                    module=text,
                    weight=_W_IMPORT_NEIGHBOUR,
                    kind=SuspectKind.IMPORT_NEIGHBOUR,
                    reason=REASON_NEIGHBOUR,
                )

    ranked = accumulator.ranked()
    truncated = len(ranked) > max_suspects
    suspects: list[SuspectLocation] = []
    for entry in ranked[:max_suspects]:
        qualified = str(entry["qualified"])
        module = str(entry["module"]) or (
            qualified.rsplit(".", 1)[0] if "." in qualified else ""
        )
        region = _call(repository_map, "region_of", qualified)
        suspects.append(
            SuspectLocation(
                qualified=qualified,
                module=module,
                path=_module_path(repository_map, module),
                score=float(entry["score"]),
                kinds=tuple(entry["kinds"]),
                reasons=tuple(str(r)[:MAX_REASON_CHARS] for r in entry["reasons"])[:MAX_REASONS],
                start_line=int(getattr(region, "start_line", 0) or 0),
                end_line=int(getattr(region, "end_line", 0) or 0),
            )
        )

    reasons: list[str] = []
    if category:
        reasons.append(f"failure category: {category}")
    if target:
        reasons.append(f"bounded verification target: {target}")
    if truncated:
        reasons.append(f"suspect list truncated to {max_suspects}")

    return FaultLocalization(
        suspects=tuple(suspects),
        changed_modules=tuple(modules),
        failure_category=category,
        verify_target=target,
        truncated=truncated,
        reasons=tuple(reason[:MAX_REASON_CHARS] for reason in reasons[:MAX_REASONS]),
    )


__all__ = [
    "DEFAULT_MAX_SUSPECTS",
    "FaultLocalization",
    "SuspectKind",
    "SuspectLocation",
    "localize_fault",
    "module_of_path",
]
