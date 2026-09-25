"""Atlas Conversation — Semantic Intake contract (D1).

The bounded, deterministic, JSON-safe semantic projection that the D1
Conversation Engine produces from the EXISTING ``TaskSpec`` and turn text.

This is a *meaning* structure, never an authority structure. It deliberately
contains no ``authorized``/``approved``/``permission`` field: interpreting a
user statement such as "I approve this." may yield ``act = "request"`` (or a
correction/approval *reference*), but it can never grant OWNER authority.
Only the existing authoritative mechanisms (session authority, the approval
manager, the promotion gate) may change governed state.

Pure logic: it reads an existing ``TaskSpec`` and returns an immutable value.
No AI, no network, no storage, no kernel access, no execution, no authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atlas.conversation.task_intake import TaskSpec

# ---------------------------------------------------------------------------
# Bounds (a malformed/oversized turn can never produce unbounded output)
# ---------------------------------------------------------------------------

_MAX_OBJECTIVE_CHARS: int = 400
_MAX_ITEM_CHARS: int = 200
_MAX_ITEMS: int = 8
_MAX_ENTITIES: int = 8
_MAX_SUBTASKS: int = 4
_MAX_CORRECTIONS: int = 5

#: Deterministic capability requirement per task type (advisory only — the
#: existing CapabilityRegistry/Router/Dispatcher remains authoritative).
_REQUIRED_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "investigation_request": ("investigation",),
    "information_request": ("research",),
    "action_request": ("task_execution",),
    "development_request": ("development",),
    "planning_request": ("development",),
    "execution_request": ("development_execution",),
    "approval": ("approval",),
    "rejection_request": ("approval",),
    "recovery_request": ("recovery",),
    "verification_request": ("verification",),
    "report_request": ("report",),
    "repository_impact_request": ("repository_impact",),
    "autonomy_request": ("autonomy",),
    "l2_autonomy_request": ("autonomy",),
    "l3_autonomy_request": ("autonomy",),
    "l4_autonomy_request": ("autonomy",),
    "l5_autonomy_request": ("autonomy",),
}

#: Requested-response shape per task type (advisory wording only).
_REQUESTED_RESPONSE: dict[str, str] = {
    "question": "answer",
    "conversation": "answer",
    "unknown": "answer",
    "investigation_request": "report",
    "information_request": "answer",
    "action_request": "action",
    "development_request": "plan",
    "planning_request": "plan",
    "execution_request": "action",
    "approval": "confirmation",
    "rejection_request": "confirmation",
    "recovery_request": "plan",
    "verification_request": "report",
    "report_request": "report",
    "repository_impact_request": "report",
    "autonomy_request": "action",
    "l2_autonomy_request": "action",
    "l3_autonomy_request": "action",
    "l4_autonomy_request": "action",
    "l5_autonomy_request": "action",
}


def _bounded_text(value: Any, limit: int = _MAX_ITEM_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _bounded_items(values: Any, *, limit: int = _MAX_ITEMS) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    out: list[str] = []
    for value in values:
        text = _bounded_text(value)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return tuple(out)


def _act(spec: TaskSpec) -> str:
    """Derive the speech act, preferring the existing L3 utterance meaning."""
    context = spec.context if isinstance(spec.context, dict) else {}
    meaning = context.get("utterance_meaning")
    if isinstance(meaning, dict):
        illocution = meaning.get("illocution")
        if illocution in ("question", "request", "statement"):
            return illocution
    value = getattr(spec.task_type, "value", "")
    if value in ("question", "unknown"):
        return "question"
    if value == "conversation":
        return "statement"
    return "request"


def _operation(spec: TaskSpec) -> str:
    context = spec.context if isinstance(spec.context, dict) else {}
    meaning = context.get("utterance_meaning")
    if isinstance(meaning, dict):
        operation = meaning.get("operation")
        if isinstance(operation, str):
            return _bounded_text(operation)
    return ""


def _entity_names(spec: TaskSpec) -> tuple[str, ...]:
    context = spec.context if isinstance(spec.context, dict) else {}
    raw = context.get("identified_entities")
    names: list[str] = []
    if isinstance(raw, (list, tuple)):
        for entry in raw:
            if isinstance(entry, dict):
                name = _bounded_text(entry.get("name"))
            else:
                name = _bounded_text(getattr(entry, "name", ""))
            if name and name not in names:
                names.append(name)
            if len(names) >= _MAX_ENTITIES:
                break
    return tuple(names)


@dataclass(frozen=True, slots=True)
class SemanticIntake:
    """Deterministic, bounded semantic projection of one turn.

    Authority-free by construction: there is no field through which an
    interpretation could authorize, approve, execute, promote, or mutate
    governed state. ``provenance["authority"]`` is always ``"none"``.
    """

    act: str = "statement"
    objective: str = ""
    operation: str = ""
    entities: tuple[str, ...] = ()
    resolved_reference: dict[str, Any] | None = None
    constraints: tuple[str, ...] = ()
    priorities: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    subtasks: tuple[str, ...] = ()
    ambiguities: tuple[str, ...] = ()
    clarification_questions: tuple[str, ...] = ()
    requested_information: tuple[str, ...] = ()
    requested_operation: str = ""
    required_capabilities: tuple[str, ...] = ()
    required_knowledge: tuple[str, ...] = ()
    requested_response: str = "answer"
    corrections: tuple[dict[str, Any], ...] = ()
    task_type: str = ""
    #: Evidence-Driven Improvement 2 — bounded conversational role of the turn
    #: (see ``atlas.conversation.turn_role.TurnRole``). Interpretation only.
    turn_role: str = ""
    confidence: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "act": self.act,
            "objective": self.objective,
            "operation": self.operation,
            "entities": list(self.entities),
            "resolved_reference": (
                dict(self.resolved_reference)
                if isinstance(self.resolved_reference, dict)
                else None
            ),
            "constraints": list(self.constraints),
            "priorities": list(self.priorities),
            "success_criteria": list(self.success_criteria),
            "subtasks": list(self.subtasks),
            "ambiguities": list(self.ambiguities),
            "clarification_questions": list(self.clarification_questions),
            "requested_information": list(self.requested_information),
            "requested_operation": self.requested_operation,
            "required_capabilities": list(self.required_capabilities),
            "required_knowledge": list(self.required_knowledge),
            "requested_response": self.requested_response,
            "corrections": [dict(c) for c in self.corrections],
            "task_type": self.task_type,
            "turn_role": self.turn_role,
            "confidence": self.confidence,
            "provenance": dict(self.provenance),
        }


def build_semantic_intake(
    spec: TaskSpec,
    text: str,
    *,
    subtasks: tuple[str, ...] = (),
    corrections: tuple[dict[str, Any], ...] = (),
    turn_role: str = "",
) -> SemanticIntake:
    """Project ``spec`` (and deterministic extras) into a ``SemanticIntake``.

    Pure and deterministic: identical ``spec``/extras produce identical output.
    Never raises for malformed input; malformed pieces degrade to empty.
    """
    if not isinstance(spec, TaskSpec):
        raise TypeError("spec must be a TaskSpec")

    context = spec.context if isinstance(spec.context, dict) else {}
    reference = context.get("resolved_reference")
    resolved_reference = (
        {"field": reference.get("field"), "value": reference.get("value")}
        if isinstance(reference, dict)
        and isinstance(reference.get("field"), str)
        else None
    )

    task_type = getattr(spec.task_type, "value", "") or ""
    objective = _bounded_text(spec.intent, _MAX_OBJECTIVE_CHARS)
    operation = _operation(spec)
    requested_operation = objective if task_type in (
        "action_request", "development_request", "planning_request",
        "execution_request",
    ) else ""

    ambiguity = getattr(spec, "ambiguity", None)
    ambiguities = _bounded_items(getattr(ambiguity, "ambiguities", ()))
    clarification_questions = _bounded_items(
        getattr(ambiguity, "clarification_questions", ())
    )

    required_knowledge: tuple[str, ...] = ()
    requested_information: tuple[str, ...] = ()
    if task_type == "information_request" and objective:
        required_knowledge = (objective,)
        requested_information = (objective,)

    try:
        confidence = float(getattr(spec, "confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    return SemanticIntake(
        act=_act(spec),
        objective=objective,
        operation=operation,
        entities=_entity_names(spec),
        resolved_reference=resolved_reference,
        constraints=_bounded_items(spec.constraints),
        priorities=_bounded_items(spec.priorities),
        success_criteria=_bounded_items(spec.success_criteria),
        subtasks=tuple(subtasks)[:_MAX_SUBTASKS],
        ambiguities=ambiguities,
        clarification_questions=clarification_questions,
        requested_information=requested_information,
        requested_operation=requested_operation,
        required_capabilities=_REQUIRED_CAPABILITIES.get(task_type, ()),
        required_knowledge=required_knowledge,
        requested_response=_REQUESTED_RESPONSE.get(task_type, "answer"),
        corrections=tuple(dict(c) for c in corrections)[-_MAX_CORRECTIONS:],
        task_type=task_type,
        turn_role=_bounded_text(turn_role, 40),
        confidence=round(max(0.0, min(1.0, confidence)), 4),
        provenance={
            "source": _bounded_text(getattr(spec, "source", ""), 64),
            "task_id": _bounded_text(getattr(spec, "task_id", ""), 128),
            "input_hash": _bounded_text(getattr(spec, "input_hash", ""), 64),
            # Explicit, machine-checkable statement that this projection
            # carries no authority whatsoever.
            "authority": "none",
        },
    )
