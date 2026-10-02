"""Atlas Conversation — contextual response composition (Stage 7).

Turns the ALREADY-DECIDED conversational outcome (Stage 4 communicative
function + Stage 6 salience/ambiguity assessment + Stage 3/5 referent evidence)
into one truthful, context-aware response.

It DESCRIBES what Atlas should communicate and RENDERS it deterministically. It
is not a prose generator and not a second conversation system:

  * Response function  — what the user wants communicated (result / explanation /
                          status / clarification / unavailable).
  * Response target    — the resolved referent (Stage 3) or thread objective.
  * Response evidence  — the recorded facts that may legitimately be stated.
  * Response uncertainty — resolved / ambiguous / insufficient / unavailable.
  * Response shape     — how the answer is structured.
  * Rendering          — deterministic text from the existing style.

Boundaries (mandatory):

  * Descriptive only — a response plan is never authority. It cannot approve,
    promote, execute, authorize, or bypass governance.
  * Evidence-grounded — it communicates only what was actually recorded; it never
    infers a fact because a referent exists, and never invents a cause.
  * Deterministic, bounded, JSON-safe, model-independent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atlas.conversation.communicative_function import FUNCTION_QUERY_CAUSE
from atlas.conversation.discourse_state import REL_PRODUCED, REL_SUPPORTED_BY

#: Response shapes (bounded vocabulary).
SHAPE_RESULT_SUMMARY: str = "result_summary"
SHAPE_EXPLANATION: str = "explanation"
SHAPE_CLARIFICATION: str = "clarification"
SHAPE_UNAVAILABLE: str = "unavailable"

SHAPES: frozenset[str] = frozenset(
    {SHAPE_RESULT_SUMMARY, SHAPE_EXPLANATION, SHAPE_CLARIFICATION, SHAPE_UNAVAILABLE}
)

#: Uncertainty classification carried by a plan.
UNCERTAINTY_RESOLVED: str = "resolved"
UNCERTAINTY_AMBIGUOUS: str = "ambiguous"
UNCERTAINTY_INSUFFICIENT: str = "insufficient"
UNCERTAINTY_UNAVAILABLE: str = "unavailable"

MAX_CANDIDATES: int = 8
MAX_EVIDENCE: int = 6
_MAX_TEXT: int = 300


def _bounded(value: Any, limit: int = _MAX_TEXT) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _referent_label(discourse: Any, referent_id: str) -> str:
    if discourse is None or not referent_id:
        return ""
    for referent in getattr(discourse, "referents", ()) or ():
        if getattr(referent, "referent_id", "") == referent_id:
            return _bounded(getattr(referent, "label", ""))
    return ""


def _producing_objective(discourse: Any, result_id: str) -> str:
    """Return the objective (operation label) that produced ``result_id``."""
    if discourse is None or not result_id:
        return ""
    for relation in getattr(discourse, "relations", ()) or ():
        if (
            getattr(relation, "relation", "") == REL_PRODUCED
            and getattr(relation, "target_id", "") == result_id
        ):
            return _referent_label(discourse, getattr(relation, "source_id", ""))
    return ""


def _evidence_labels(discourse: Any, referent_id: str) -> tuple[str, ...]:
    """Return the bounded evidence labels that support ``referent_id``."""
    if discourse is None or not referent_id:
        return ()
    out: list[str] = []
    for relation in getattr(discourse, "relations", ()) or ():
        if (
            getattr(relation, "relation", "") == REL_SUPPORTED_BY
            and getattr(relation, "source_id", "") == referent_id
        ):
            label = _referent_label(discourse, getattr(relation, "target_id", ""))
            if label and label not in out:
                out.append(label)
            if len(out) >= MAX_EVIDENCE:
                break
    return tuple(out)


@dataclass(frozen=True, slots=True)
class ResponsePlan:
    """A bounded, inspectable, authority-free description of one response."""

    function: str = ""
    shape: str = SHAPE_UNAVAILABLE
    uncertainty: str = UNCERTAINTY_UNAVAILABLE
    target_kind: str = ""
    target_referent_id: str = ""
    target_label: str = ""
    objective: str = ""
    candidates: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "function": self.function,
            "shape": self.shape,
            "uncertainty": self.uncertainty,
            "target_kind": self.target_kind,
            "target_referent_id": self.target_referent_id,
            "target_label": self.target_label,
            "objective": self.objective,
            "candidates": list(self.candidates),
            "evidence": list(self.evidence),
        }


def compose_response(
    *,
    function: str,
    route: str,
    target_kind: str = "",
    target_referent_id: str = "",
    target_label: str = "",
    candidates: Any = (),
    discourse: Any = None,
) -> ResponsePlan:
    """Compose the bounded response plan from the already-decided outcome."""
    bounded_function = _bounded(function, 40)
    bounded_candidates = tuple(
        _bounded(c, 120) for c in (candidates or ()) if isinstance(c, str) and c.strip()
    )[:MAX_CANDIDATES]

    if route == "clarify":
        return ResponsePlan(
            function=bounded_function,
            shape=SHAPE_CLARIFICATION,
            uncertainty=UNCERTAINTY_AMBIGUOUS,
            candidates=bounded_candidates,
        )

    # Anything that is not a RESOLVED result (fail_closed, an unknown route, or a
    # malformed decision) fails closed to an honest unavailable response.
    if route != "result":
        objective = (
            _referent_label(discourse, target_referent_id)
            if target_kind == "operation"
            else ""
        )
        return ResponsePlan(
            function=bounded_function,
            shape=SHAPE_UNAVAILABLE,
            uncertainty=(UNCERTAINTY_INSUFFICIENT if objective else UNCERTAINTY_UNAVAILABLE),
            target_kind=_bounded(target_kind, 40),
            target_referent_id=_bounded(target_referent_id, 16),
            objective=objective,
        )

    # route == "result" — a resolved target with recorded content.
    objective = (
        _referent_label(discourse, target_referent_id)
        if target_kind == "operation"
        else _producing_objective(discourse, target_referent_id)
    )
    evidence = _evidence_labels(discourse, target_referent_id)
    shape = (
        SHAPE_EXPLANATION
        if bounded_function == FUNCTION_QUERY_CAUSE
        else SHAPE_RESULT_SUMMARY
    )
    return ResponsePlan(
        function=bounded_function,
        shape=shape,
        uncertainty=(UNCERTAINTY_INSUFFICIENT if shape == SHAPE_EXPLANATION else UNCERTAINTY_RESOLVED),
        target_kind=_bounded(target_kind, 40),
        target_referent_id=_bounded(target_referent_id, 16),
        target_label=_bounded(target_label),
        objective=objective,
        evidence=evidence,
    )


def _clean_objective(objective: str) -> str:
    return objective.strip().rstrip(".").strip()


def render_response(plan: ResponsePlan) -> str:
    """Render a plan to deterministic, user-facing text (existing style)."""
    if plan.shape == SHAPE_CLARIFICATION:
        lines = ["I need a bit more detail before I can answer:"]
        if plan.candidates:
            lines.append("More than one item matches:")
            lines.extend(f"- {candidate}" for candidate in plan.candidates)
        lines.append("Which one do you mean?")
        lines.append("Nothing was executed or authorized.")
        return "\n".join(lines)

    if plan.shape == SHAPE_UNAVAILABLE:
        if plan.uncertainty == UNCERTAINTY_INSUFFICIENT and plan.objective:
            return (
                f"I found '{_clean_objective(plan.objective)}', but there is no "
                "recorded result for it. I will not invent one, and naming a past "
                "operation does not start a new one."
            )
        return (
            "I cannot answer that: I have no recorded result to report. I will not "
            "invent one, and naming a past operation does not start a new one. "
            "Please ask me to investigate a subject first."
        )

    if plan.shape == SHAPE_EXPLANATION:
        body = f"Here is the recorded result:\n\n{plan.target_label}" if plan.target_label else (
            "No recorded result is available for this target."
        )
        evidence = _render_evidence(plan.evidence)
        return (
            "I do not infer causes, and the record does not establish why this "
            f"happened. {body}{evidence}"
        )

    # SHAPE_RESULT_SUMMARY
    if plan.objective:
        head = f"Result of {_clean_objective(plan.objective)}:"
    else:
        head = "Recorded result:"
    body = f"{head}\n\n{plan.target_label}" if plan.target_label else (
        "No recorded result is available for this target."
    )
    return f"{body}{_render_evidence(plan.evidence)}"


def _render_evidence(evidence: tuple[str, ...]) -> str:
    if not evidence:
        return ""
    lines = ["", "Evidence:"]
    lines.extend(f"- {item}" for item in evidence)
    return "\n".join(lines)


def compose_from_decision(
    function: str, decision: Any, discourse: Any = None
) -> ResponsePlan:
    """Convenience: compose a plan from a Stage 4 ``RoutingDecision`` (duck-typed)."""
    assessment = getattr(decision, "assessment", None)
    assessment = assessment if isinstance(assessment, dict) else {}
    candidates = tuple(
        entry.get("label")
        for entry in (assessment.get("candidates") or ())
        if isinstance(entry, dict) and entry.get("label")
    )
    return compose_response(
        function=function,
        route=getattr(decision, "route", ""),
        target_kind=getattr(decision, "target_kind", ""),
        target_referent_id=getattr(decision, "target_referent_id", ""),
        target_label=getattr(decision, "target_label", ""),
        candidates=candidates,
        discourse=discourse,
    )


__all__ = [
    "SHAPE_RESULT_SUMMARY",
    "SHAPE_EXPLANATION",
    "SHAPE_CLARIFICATION",
    "SHAPE_UNAVAILABLE",
    "SHAPES",
    "UNCERTAINTY_RESOLVED",
    "UNCERTAINTY_AMBIGUOUS",
    "UNCERTAINTY_INSUFFICIENT",
    "UNCERTAINTY_UNAVAILABLE",
    "MAX_CANDIDATES",
    "MAX_EVIDENCE",
    "ResponsePlan",
    "compose_response",
    "compose_from_decision",
    "render_response",
]
