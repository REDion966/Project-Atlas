"""Atlas Conversation — salience, ambiguity & uncertainty (Stage 6).

Deterministic, inspectable adjudication of WHICH contextual candidate a turn's
reference is aimed at, and WHEN the available conversational evidence is not
enough to choose.

It answers two questions:

  * given several compatible referents, which one does the current conversation
    support (by EXPLICIT evidence), and
  * when is there genuinely no single supported target (ambiguity / uncertainty)?

Boundaries (mandatory):

  * Descriptive only — a highly salient candidate is NOT approved, authorized,
    executable or promoted. Salience never grants authority.
  * No learning, no embeddings, no probabilities — selection is a fixed,
    documented EVIDENCE HIERARCHY over explicit, deterministic evidence classes.
  * Referents are read from the Stage 3 ``DiscourseState`` by reference; the
    Stage 5 ``DialogueThreadState`` supplies the active-thread / QUD evidence.
    Nothing is copied and no referent identity is mutated by salience.
  * Bounded, JSON-safe, deterministic (no dict/set-order dependence).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Evidence levels, ordered strongest → weakest. Higher is stronger.
LEVEL_EXPLICIT: int = 5  # matched an explicitly named target
LEVEL_QUD: int = 4  # the current thread's question-under-discussion concerns it
LEVEL_ACTIVE_THREAD: int = 3  # it is the active thread's operation/result
LEVEL_RECENCY: int = 1  # it is the single most recent result (weak)

#: A tie at or above this level is "strong" evidence; RECENCY alone is NOT
#: sufficient to choose between multiple materially plausible candidates.
LEVEL_STRONG: int = LEVEL_ACTIVE_THREAD

STATUS_RESOLVED: str = "resolved"  # one candidate is sufficiently supported
STATUS_AMBIGUOUS: str = "ambiguous"  # several remain materially plausible
STATUS_UNCERTAIN: str = "uncertain"  # evidence cannot establish the named target
STATUS_NONE: str = "none"  # no valid candidate exists

STATUSES: frozenset[str] = frozenset(
    {STATUS_RESOLVED, STATUS_AMBIGUOUS, STATUS_UNCERTAIN, STATUS_NONE}
)

#: Bound on the candidate set (a turn can never consider an unbounded set).
MAX_CANDIDATES: int = 12

_MAX_TEXT_CHARS: int = 200


def _bounded(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class Candidate:
    """One bounded contextual candidate with its strongest applicable evidence."""

    referent_id: str
    kind: str = ""
    label: str = ""
    level: int = 0
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "referent_id": self.referent_id,
            "kind": self.kind,
            "label": self.label,
            "level": self.level,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class SalienceAssessment:
    """A bounded, inspectable, authority-free salience/ambiguity assessment."""

    status: str = STATUS_NONE
    selected_referent_id: str = ""
    selected_kind: str = ""
    selected_label: str = ""
    candidates: tuple[Candidate, ...] = ()
    reason: str = ""

    def labels(self) -> tuple[str, ...]:
        """Bounded candidate labels (for a clarification question)."""
        return tuple(c.label for c in self.candidates if c.label)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "selected_referent_id": self.selected_referent_id,
            "selected_kind": self.selected_kind,
            "selected_label": self.selected_label,
            "candidates": [c.to_dict() for c in self.candidates],
            "reason": self.reason,
        }


def _active(thread_state: Any) -> Any:
    """Return the active thread from a Stage 5 thread state, or ``None``."""
    if thread_state is None:
        return None
    try:
        return thread_state.active()
    except Exception:  # malformed foreign object -> no active-thread evidence
        return None


def _evidence(
    referent_id: str,
    *,
    explicit_ids: frozenset[str],
    qud_referent_id: str,
    active_result_id: str,
    active_operation_id: str,
    latest_referent_id: str,
) -> tuple[int, tuple[str, ...]]:
    """Return ``(level, reasons)`` — the strongest applicable evidence class."""
    if referent_id in explicit_ids:
        return LEVEL_EXPLICIT, ("explicit-target",)
    if qud_referent_id and referent_id == qud_referent_id:
        return LEVEL_QUD, ("qud-target",)
    if referent_id and referent_id in (active_result_id, active_operation_id):
        return LEVEL_ACTIVE_THREAD, ("active-thread",)
    if latest_referent_id and referent_id == latest_referent_id:
        return LEVEL_RECENCY, ("recency",)
    return 0, ()


def result_candidates(
    discourse: Any,
    thread_state: Any = None,
    *,
    explicit_ids: Any = (),
    latest_referent_id: str = "",
) -> tuple[Candidate, ...]:
    """Build the bounded RESULT candidate set with their evidence levels.

    Deterministic: referents are read in their stored order and capped at
    :data:`MAX_CANDIDATES`. Candidate generation stays bounded to the existing
    ``DiscourseState`` — no repository scan, no semantic search.
    """
    explicit = frozenset(str(i) for i in explicit_ids if isinstance(i, str) and i)
    active = _active(thread_state)
    active_result = getattr(active, "result_referent_id", "") if active is not None else ""
    active_operation = (
        getattr(active, "operation_referent_id", "") if active is not None else ""
    )
    qud = getattr(active, "qud", None) if active is not None else None
    qud_referent = getattr(qud, "referent_id", "") if qud is not None else ""
    latest = _bounded(latest_referent_id, 64)

    candidates: list[Candidate] = []
    referents = getattr(discourse, "referents", ()) if discourse is not None else ()
    for referent in tuple(referents or ()):
        if getattr(referent, "kind", "") != "result":
            continue
        referent_id = getattr(referent, "referent_id", "")
        if not referent_id:
            continue
        level, reasons = _evidence(
            referent_id,
            explicit_ids=explicit,
            qud_referent_id=qud_referent,
            active_result_id=active_result,
            active_operation_id=active_operation,
            latest_referent_id=latest,
        )
        candidates.append(
            Candidate(
                referent_id=referent_id,
                kind="result",
                label=_bounded(getattr(referent, "label", "")),
                level=level,
                reasons=reasons,
            )
        )
        if len(candidates) >= MAX_CANDIDATES:
            break
    return tuple(candidates)


def operation_candidates(
    discourse: Any, referent_ids: Any
) -> tuple[Candidate, ...]:
    """Build EXPLICIT operation candidates from named referent ids (bounded)."""
    wanted = {str(i) for i in referent_ids if isinstance(i, str) and i}
    out: list[Candidate] = []
    referents = getattr(discourse, "referents", ()) if discourse is not None else ()
    for referent in tuple(referents or ()):
        if getattr(referent, "referent_id", "") not in wanted:
            continue
        out.append(
            Candidate(
                referent_id=getattr(referent, "referent_id", ""),
                kind=_bounded(getattr(referent, "kind", ""), 40),
                label=_bounded(getattr(referent, "label", "")),
                level=LEVEL_EXPLICIT,
                reasons=("explicit-target",),
            )
        )
        if len(out) >= MAX_CANDIDATES:
            break
    return tuple(out)


def assess_candidates(
    candidates: tuple[Candidate, ...], *, explicit_target: str = ""
) -> SalienceAssessment:
    """Deterministically select a candidate or report ambiguity/uncertainty.

    Rules (documented evidence hierarchy — EXPLICIT > QUD > ACTIVE_THREAD >
    RECENCY):

    * no candidates → ``NONE`` (unless an explicit target was named but matched
      nothing → ``UNCERTAIN``);
    * exactly one candidate → ``RESOLVED``;
    * several candidates: the unique strongest candidate at or above
      :data:`LEVEL_STRONG` → ``RESOLVED``;
    * several candidates tied at the strongest strong level → ``AMBIGUOUS``;
    * several candidates with no strong evidence (only RECENCY) → ``AMBIGUOUS``
      (recency alone never decides between materially plausible candidates).

    Ties never resolve by incidental list/dict order.
    """
    if not candidates:
        if explicit_target:
            return SalienceAssessment(
                status=STATUS_UNCERTAIN,
                reason="the named target matched no known referent",
            )
        return SalienceAssessment(status=STATUS_NONE, reason="no compatible referent")

    if len(candidates) == 1:
        only = candidates[0]
        return SalienceAssessment(
            status=STATUS_RESOLVED,
            selected_referent_id=only.referent_id,
            selected_kind=only.kind,
            selected_label=only.label,
            candidates=candidates,
            reason="the only compatible candidate",
        )

    strong = [c for c in candidates if c.level >= LEVEL_STRONG]
    if strong:
        top = max(c.level for c in strong)
        strongest = [c for c in strong if c.level == top]
        if len(strongest) == 1:
            winner = strongest[0]
            return SalienceAssessment(
                status=STATUS_RESOLVED,
                selected_referent_id=winner.referent_id,
                selected_kind=winner.kind,
                selected_label=winner.label,
                candidates=candidates,
                reason=f"strongest evidence: {winner.reasons[0] if winner.reasons else 'evidence'}",
            )
        return SalienceAssessment(
            status=STATUS_AMBIGUOUS,
            candidates=tuple(strongest) + tuple(c for c in candidates if c not in strongest),
            reason="several candidates share the strongest evidence",
        )

    # No strong evidence at all: only recency (if anything) — not sufficient.
    return SalienceAssessment(
        status=STATUS_AMBIGUOUS,
        candidates=candidates,
        reason="insufficient evidence to choose among several candidates",
    )


def assess(
    discourse: Any,
    thread_state: Any = None,
    *,
    explicit_ids: Any = (),
    explicit_target: str = "",
    latest_referent_id: str = "",
) -> SalienceAssessment:
    """Build the RESULT candidates and assess them (the common Stage 6 call)."""
    candidates = result_candidates(
        discourse,
        thread_state,
        explicit_ids=explicit_ids,
        latest_referent_id=latest_referent_id,
    )
    return assess_candidates(candidates, explicit_target=explicit_target)


__all__ = [
    "LEVEL_EXPLICIT",
    "LEVEL_QUD",
    "LEVEL_ACTIVE_THREAD",
    "LEVEL_RECENCY",
    "LEVEL_STRONG",
    "STATUS_RESOLVED",
    "STATUS_AMBIGUOUS",
    "STATUS_UNCERTAIN",
    "STATUS_NONE",
    "STATUSES",
    "MAX_CANDIDATES",
    "Candidate",
    "SalienceAssessment",
    "result_candidates",
    "operation_candidates",
    "assess_candidates",
    "assess",
]
