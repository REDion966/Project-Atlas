"""Atlas Conversation — L1/L2 Internal Meaning Representation + language boundary.

The first additive layer of the future conversational architecture (Stage 1).
It introduces ONE explicit, inspectable **internal meaning representation**
(:class:`AtlasMeaning`) for each conversational turn:

    user text
      -> existing deterministic interpretation (TaskIntake / SemanticFrame /
         UtteranceMeaning / TurnRole / SemanticIntake)
      -> AtlasMeaning projection  (this module — representation only)
      -> existing ConversationService routing  (unchanged, authoritative)

Design contract (L1/L2):
  * Representation only. ``AtlasMeaning`` *describes what Atlas currently
    believes the utterance means*; it never routes, authorizes, approves,
    executes, promotes, mutates governed state, invokes a tool, or calls a
    model. ``provenance["authority"]`` is always ``"none"``.
  * One interpretation path: the projection REUSES the existing deterministic
    structures (``SemanticFrame``, ``TaskSpec``, ``SemanticIntake``,
    ``TurnRole``, the existing surface normalisation). It does not add a
    second parser, and it never re-runs intake/classification.
  * PROCEED-only: constructing it changes no routing and no handler precedence.
  * Honest placeholders: L3 (communicative function) is NOT implemented yet, so
    ``communicative_function`` is a bounded *status* (``unknown`` /
    ``existing_interpretation``) and the existing bounded reading is carried
    separately as *evidence* — the current ``TaskType`` is never presented as a
    communicative function.
  * Deterministic and model-independent: standard library only, no clock, no
    randomness, no I/O, no network, no model, no embeddings.
  * Bounded and JSON-safe: every field is hard-capped; ``to_dict`` is
    serialisable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atlas.conversation.normalization import (
    canonicalize_surface,
    collapse_whitespace,
)
from atlas.conversation.communicative_function import classify_function
from atlas.conversation.semantic_frame import SemanticFrame
from atlas.conversation.semantic_frame import interpret as interpret_frame
from atlas.conversation.semantic_intake import SemanticIntake
from atlas.conversation.task_intake import TaskSpec
from atlas.conversation.turn_role import TurnRole
from atlas.conversation.utterance_meaning import UTTERANCE_MEANING_KEY

#: Context key under which the bounded meaning projection rides the existing
#: ``TaskSpec.context`` (the same additive channel ``semantic_intake`` uses).
ATLAS_MEANING_KEY: str = "atlas_meaning"

#: Communicative function. Stage 1 introduced a provisional placeholder; Stage 4
#: fills it with the bounded communicative-function vocabulary (see
#: :mod:`atlas.conversation.communicative_function`). ``unknown`` remains the
#: neutral default; ``EXISTING`` is retained for backward compatibility but is no
#: longer emitted.
COMMUNICATIVE_FUNCTION_UNKNOWN: str = "unknown"
COMMUNICATIVE_FUNCTION_EXISTING: str = "existing_interpretation"

#: Hard bounds (a malformed/oversized turn can never produce unbounded output).
_MAX_SOURCE_TEXT_CHARS: int = 500
_MAX_TEXT_CHARS: int = 200
_MAX_ITEMS: int = 8


def _bounded_text(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    """Return a trimmed, length-bounded string (non-strings degrade to ``""``)."""
    return value.strip()[:limit] if isinstance(value, str) else ""


def _bounded_str_tuple(values: Any, limit: int = _MAX_ITEMS) -> tuple[str, ...]:
    """Return a bounded, de-duplicated tuple of non-empty bounded strings."""
    out: list[str] = []
    if not isinstance(values, (list, tuple)):
        return ()
    for value in values:
        text = _bounded_text(value)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return tuple(out)


def _bounded_arguments(values: Any, limit: int = _MAX_ITEMS) -> tuple[tuple[str, str], ...]:
    """Return bounded ``(role, value)`` argument pairs from the frame evidence."""
    out: list[tuple[str, str]] = []
    if not isinstance(values, (list, tuple)):
        return ()
    for pair in values:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        role = _bounded_text(pair[0], 40)
        value = _bounded_text(pair[1])
        if role and value:
            out.append((role, value))
        if len(out) >= limit:
            break
    return tuple(out)


@dataclass(frozen=True, slots=True)
class AtlasMeaning:
    """Bounded, deterministic, authority-free meaning of one turn (L1/L2).

    The single explicit internal-meaning representation. It is a *projection*
    of the existing deterministic interpretation, so it duplicates no parser:
    ``frame`` and ``semantic_intake`` carry the existing structures verbatim
    (nothing is lost, no reconstruction drift), while the top-level fields
    expose the unified, cross-cutting view later stages build on.

    Authority-free by construction: there is no ``authorized`` / ``approved`` /
    ``permission`` field and no method that executes, approves, promotes, or
    mutates governed state. ``provenance["authority"]`` is always ``"none"``.

    Fields that depend on later stages carry honest neutral defaults and are
    documented as unpopulated in Stage 1 (``question_type`` / ``temporal_cues``
    / ``discourse_relations``); nothing future is encoded as a fact.
    """

    # --- L2 language boundary ---
    source_text: str = ""
    normalized_text: str = ""

    # --- L3 placeholder (NOT a classifier) ---
    #: ``unknown`` or ``existing_interpretation`` — never a fabricated function.
    communicative_function: str = COMMUNICATIVE_FUNCTION_UNKNOWN
    #: The EXISTING bounded reading, carried as EVIDENCE only (not a function).
    communicative_function_evidence: dict[str, Any] = field(default_factory=dict)

    # --- existing bounded interpretation (projected, not re-derived) ---
    role: str = ""
    domain: str = ""
    operation: str = ""
    topic: str = ""
    concept: str = ""
    user_goal: str = ""
    operation_arguments: tuple[tuple[str, str], ...] = ()
    constraints: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()

    # --- future fields, honest neutral defaults (unpopulated in Stage 1) ---
    #: Question type (result/cause/elaboration/...) — requires L3; ``""`` here.
    question_type: str = ""
    #: The referent KIND the turn expects an answer from (resolved reference).
    answer_target: str = ""
    #: Bounded reference CUE(s) the surface carried (never a guess).
    references: tuple[str, ...] = ()
    #: Temporal cue(s) ("just completed", "earlier", ...) — none yet: ``()``.
    temporal_cues: tuple[str, ...] = ()
    #: Discourse relation(s) to the prior turn — none yet: ``()``.
    discourse_relations: tuple[str, ...] = ()

    # --- existing L4 evidence + uncertainty / status ---
    resolved_reference: dict[str, Any] | None = None
    uncertainty: dict[str, Any] = field(default_factory=dict)
    clarification_required: bool = False
    governance_relevance: bool = False

    # --- existing provenance identity ---
    task_type: str = ""
    turn_role: str = ""
    confidence: float = 0.0

    # --- existing structures carried verbatim (L1 fidelity) ---
    semantic_intake: SemanticIntake | None = None
    frame: SemanticFrame | None = None

    #: Deterministic provenance; ``authority`` is always ``"none"``.
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Deterministic, JSON-safe serialization."""
        return {
            "source_text": self.source_text,
            "normalized_text": self.normalized_text,
            "communicative_function": self.communicative_function,
            "communicative_function_evidence": dict(
                self.communicative_function_evidence
            ),
            "role": self.role,
            "domain": self.domain,
            "operation": self.operation,
            "topic": self.topic,
            "concept": self.concept,
            "user_goal": self.user_goal,
            "operation_arguments": [list(pair) for pair in self.operation_arguments],
            "constraints": list(self.constraints),
            "success_criteria": list(self.success_criteria),
            "question_type": self.question_type,
            "answer_target": self.answer_target,
            "references": list(self.references),
            "temporal_cues": list(self.temporal_cues),
            "discourse_relations": list(self.discourse_relations),
            "resolved_reference": (
                dict(self.resolved_reference)
                if isinstance(self.resolved_reference, dict)
                else None
            ),
            "uncertainty": dict(self.uncertainty),
            "clarification_required": self.clarification_required,
            "governance_relevance": self.governance_relevance,
            "task_type": self.task_type,
            "turn_role": self.turn_role,
            "confidence": self.confidence,
            "semantic_intake": (
                self.semantic_intake.to_dict()
                if isinstance(self.semantic_intake, SemanticIntake)
                else None
            ),
            "frame": (
                self.frame.to_dict()
                if isinstance(self.frame, SemanticFrame)
                else None
            ),
            "provenance": dict(self.provenance),
        }


def _communicative_function_evidence(
    frame: SemanticFrame | None,
    spec: TaskSpec | None,
    utterance: dict[str, Any],
) -> dict[str, Any]:
    """The EXISTING bounded reading carried as evidence for the L3 placeholder."""
    evidence: dict[str, Any] = {}
    if isinstance(frame, SemanticFrame):
        evidence["frame_role"] = frame.role.value
        evidence["frame_domain"] = frame.domain.value
        if frame.operation:
            evidence["frame_operation"] = _bounded_text(frame.operation, 40)
    illocution = _bounded_text(utterance.get("illocution"), 40)
    if illocution:
        evidence["illocution"] = illocution
    task_type = _bounded_text(
        getattr(getattr(spec, "task_type", None), "value", ""), 40
    )
    if task_type:
        evidence["task_type"] = task_type
    return evidence


def build_atlas_meaning(
    text: Any,
    *,
    spec: TaskSpec | None = None,
    semantic: SemanticIntake | None = None,
    turn_role: TurnRole | None = None,
    frame: SemanticFrame | None = None,
    has_prior_objective: bool = False,
    has_knowledge_context: bool = False,
) -> AtlasMeaning:
    """Project the existing interpretation into an :class:`AtlasMeaning`.

    Pure and deterministic: identical inputs produce identical output. It never
    raises for malformed input — malformed pieces degrade to empty values.

    When ``frame`` is not supplied, the EXISTING shared deterministic
    :func:`atlas.conversation.semantic_frame.interpret` is used (one parser; no
    second interpretation path). ``spec`` / ``semantic`` / ``turn_role`` are the
    already-produced existing structures; nothing is re-classified here.
    """
    source = text if isinstance(text, str) else ""
    normalized = (
        collapse_whitespace(canonicalize_surface(source)) if source else ""
    )

    if frame is None:
        try:
            frame = interpret_frame(
                source,
                has_prior_objective=bool(has_prior_objective),
                has_knowledge_context=bool(has_knowledge_context),
            )
        except Exception:  # defensive: interpretation never raises by contract
            frame = None

    context: dict[str, Any] = (
        spec.context
        if isinstance(spec, TaskSpec) and isinstance(spec.context, dict)
        else {}
    )
    resolved = context.get("resolved_reference")
    resolved_reference = (
        {"field": resolved.get("field"), "value": resolved.get("value")}
        if isinstance(resolved, dict) and isinstance(resolved.get("field"), str)
        else None
    )
    utterance = context.get(UTTERANCE_MEANING_KEY)
    utterance = utterance if isinstance(utterance, dict) else {}

    # --- existing interpretation (projected) ---
    role = frame.role.value if isinstance(frame, SemanticFrame) else ""
    domain = frame.domain.value if isinstance(frame, SemanticFrame) else ""
    operation = (
        _bounded_text(frame.operation, 40) if isinstance(frame, SemanticFrame) else ""
    )
    topic = _bounded_text(frame.subject) if isinstance(frame, SemanticFrame) else ""
    concept = (
        _bounded_text(frame.concept, 60) if isinstance(frame, SemanticFrame) else ""
    )
    operation_arguments = _bounded_arguments(
        frame.arguments if isinstance(frame, SemanticFrame) else ()
    )
    references = _bounded_str_tuple(
        (frame.reference,) if isinstance(frame, SemanticFrame) else ()
    )

    user_goal = (
        _bounded_text(semantic.objective, 400)
        if isinstance(semantic, SemanticIntake)
        else _bounded_text(getattr(spec, "intent", ""), 400)
    )

    uncertainty: dict[str, Any] = {}
    ambiguity = getattr(spec, "ambiguity", None)
    if ambiguity is not None and hasattr(ambiguity, "to_dict"):
        value = ambiguity.to_dict()
        if isinstance(value, dict):
            uncertainty = value

    clarification_required = bool(
        (isinstance(frame, SemanticFrame) and frame.needs_clarification)
        or bool(getattr(spec, "needs_clarification", False))
    )
    governance_relevance = bool(
        isinstance(frame, SemanticFrame) and frame.governance_sensitive
    )

    task_type = _bounded_text(
        getattr(getattr(spec, "task_type", None), "value", ""), 40
    )
    if isinstance(turn_role, TurnRole):
        role_value = turn_role.value
    else:
        role_value = (
            _bounded_text(semantic.turn_role, 40)
            if isinstance(semantic, SemanticIntake)
            else ""
        )

    try:
        confidence = float(getattr(spec, "confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    # Stage 4 — the bounded communicative function, determined from the EXISTING
    # interpretation evidence (the L3 illocution/operation) via the shared
    # deterministic classifier. It DESCRIBES what the turn appears to be doing;
    # it is authority-free. The Stage 1 placeholder is superseded here.
    illocution = _bounded_text(utterance.get("illocution"), 40)
    l3_operation = (
        _bounded_text(semantic.operation, 40)
        if isinstance(semantic, SemanticIntake)
        else _bounded_text(utterance.get("operation"), 40)
    )
    communicative_function = classify_function(
        source, illocution=illocution, operation=l3_operation
    )

    return AtlasMeaning(
        source_text=_bounded_text(source, _MAX_SOURCE_TEXT_CHARS),
        normalized_text=_bounded_text(normalized, _MAX_SOURCE_TEXT_CHARS),
        communicative_function=communicative_function,
        communicative_function_evidence=_communicative_function_evidence(
            frame, spec, utterance
        ),
        role=role,
        domain=domain,
        operation=operation,
        topic=topic,
        concept=concept,
        user_goal=user_goal,
        operation_arguments=operation_arguments,
        constraints=_bounded_str_tuple(
            getattr(spec, "constraints", ()) if spec is not None else ()
        ),
        success_criteria=_bounded_str_tuple(
            getattr(spec, "success_criteria", ()) if spec is not None else ()
        ),
        answer_target=(
            _bounded_text(resolved_reference.get("field"), 60)
            if isinstance(resolved_reference, dict)
            else ""
        ),
        references=references,
        resolved_reference=resolved_reference,
        uncertainty=uncertainty,
        clarification_required=clarification_required,
        governance_relevance=governance_relevance,
        task_type=task_type,
        turn_role=role_value,
        confidence=round(max(0.0, min(1.0, confidence)), 4),
        semantic_intake=semantic if isinstance(semantic, SemanticIntake) else None,
        frame=frame if isinstance(frame, SemanticFrame) else None,
        provenance={
            "source": "deterministic",
            "task_id": _bounded_text(getattr(spec, "task_id", ""), 128),
            "input_hash": _bounded_text(getattr(spec, "input_hash", ""), 64),
            # Explicit, machine-checkable statement that this representation
            # carries no authority whatsoever.
            "authority": "none",
        },
    )


__all__ = [
    "ATLAS_MEANING_KEY",
    "COMMUNICATIVE_FUNCTION_UNKNOWN",
    "COMMUNICATIVE_FUNCTION_EXISTING",
    "AtlasMeaning",
    "build_atlas_meaning",
]
