"""Atlas Conversation Engine (D1).

The smallest interaction/interpretation/orchestration boundary justified by
D0. It sits between human language and Atlas's EXISTING deterministic systems:

    user text
      -> ConversationEngine.interpret(...)      (interpretation only)
      -> SemanticIntake                          (bounded meaning)
      -> existing ConversationService routing    (unchanged, authoritative)
      -> existing governed handlers/services

It is NOT a brain, planner, capability dispatcher, governance system, memory
system, model, or authority. It performs no routing, execution, approval, or
state mutation beyond the bounded conversational-state fields it owns
(``current_objective`` / ``subtasks`` / ``corrections``).

Deterministic and model-independent: it reuses the existing deterministic
``TaskIntake`` and existing resolvers; it never calls a model or the network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from atlas.conversation.conversation_state import (
    MAX_CORRECTIONS,
    MAX_SUBTASKS,
    ConversationState,
    Correction,
)
from atlas.conversation.semantic_intake import (
    SemanticIntake,
    build_semantic_intake,
)
from atlas.conversation.task_intake import TaskIntake, TaskSpec
from atlas.conversation.turn_role import (
    CORRECTION_MARKERS,
    TurnRole,
    corrected_subject,
    detect_turn_role,
)

#: Context key under which the semantic projection rides the existing TaskSpec.
SEMANTIC_INTAKE_KEY: str = "semantic_intake"

#: Bounded deterministic correction cues. A correction is only ever RECORDED
#: (as a superseded reading); it never re-routes and never grants authority.
#: Canonical set lives in :mod:`atlas.conversation.turn_role`.
_CORRECTION_MARKERS: tuple[str, ...] = CORRECTION_MARKERS

#: Bounded compound-request connectors (representation only — no execution).
_SUBTASK_SPLIT_RE: re.Pattern[str] = re.compile(
    r"\s*(?:;|\band then\b|\bthen\b|\bafter that\b|\band finally\b|\bfinally\b)\s*",
    re.IGNORECASE,
)

_MAX_OBJECTIVE_CHARS: int = 400
_MAX_SUBTASK_CHARS: int = 200


def _bounded(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def detect_subtasks(text: str) -> tuple[str, ...]:
    """Return ordered bounded subtasks of a compound request, or ``()``.

    Deterministic split on a bounded connector set. Purely representational:
    a compound request is *represented*, never executed.
    """
    if not isinstance(text, str) or not text.strip():
        return ()
    parts = [
        clause.strip()[:_MAX_SUBTASK_CHARS]
        for clause in _SUBTASK_SPLIT_RE.split(text)
        if clause.strip()
    ]
    parts = [part for part in parts if part][:MAX_SUBTASKS]
    return tuple(parts) if len(parts) >= 2 else ()


@dataclass(frozen=True, slots=True)
class EngineInterpretation:
    """One turn's interpretation: the existing TaskSpec plus the D1 projection."""

    spec: TaskSpec | None
    semantic: SemanticIntake | None
    subtasks: tuple[str, ...] = ()
    corrections: tuple[Correction, ...] = ()
    turn_role: TurnRole = TurnRole.NEW_OBJECTIVE


class ConversationEngine:
    """Deterministic interpretation boundary over the existing ``TaskIntake``.

    Args:
        task_intake: The existing deterministic ``TaskIntake``. When ``None`` the
            engine performs no intake (interpret returns a ``None`` spec), which
            preserves the legacy intake-less behavior exactly.
    """

    def __init__(self, task_intake: TaskIntake | None = None) -> None:
        self._intake = task_intake

    def interpret(
        self,
        text: str,
        *,
        history_length: int = 0,
        state: ConversationState | None = None,
    ) -> EngineInterpretation:
        """Interpret one turn into (TaskSpec, SemanticIntake). Pure."""
        spec = (
            self._intake.intake(text, history_length=history_length)
            if self._intake is not None
            else None
        )
        if spec is None:
            return EngineInterpretation(spec=None, semantic=None)
        subtasks = detect_subtasks(text)
        corrections = self._detect_correction(text, spec, state)
        turn_role = detect_turn_role(
            text,
            has_prior_objective=bool(
                state is not None and state.current_objective
            ),
        )
        semantic = build_semantic_intake(
            spec,
            text,
            subtasks=subtasks,
            corrections=tuple(c.to_dict() for c in corrections),
            turn_role=turn_role.value,
        )
        return EngineInterpretation(
            spec=spec,
            semantic=semantic,
            subtasks=subtasks,
            corrections=corrections,
            turn_role=turn_role,
        )

    def with_semantic(self, spec: TaskSpec, semantic: SemanticIntake | None) -> TaskSpec:
        """Attach the bounded semantic projection to ``spec.context``.

        Additive and read-only: every existing context key is preserved, and a
        ``None`` projection leaves the spec untouched.
        """
        if semantic is None or not isinstance(spec, TaskSpec):
            return spec
        context = dict(spec.context) if isinstance(spec.context, dict) else {}
        context[SEMANTIC_INTAKE_KEY] = semantic.to_dict()
        return replace(spec, context=context)

    def state_updates(
        self,
        interpretation: EngineInterpretation,
        state: ConversationState | None,
    ) -> dict[str, Any]:
        """Return the bounded conversational-state updates for one turn.

        Only D1 fields are ever produced (``current_objective`` / ``subtasks`` /
        ``corrections``); no governed or authoritative field is touched.

        Evidence-Driven Improvement 2 — the ACTIVE OBJECTIVE is replaced only by
        a genuinely new objective (``TurnRole.NEW_OBJECTIVE``) or by a correction
        (``TurnRole.CORRECTION``, which installs the corrected subject).
        Follow-up / recall / acknowledgement / continuation / clarification /
        reference turns PRESERVE it: a meta turn must never clobber the work the
        user is actually pursuing.
        """
        updates: dict[str, Any] = {}
        role = interpretation.turn_role
        if interpretation.spec is not None:
            objective = _bounded(
                getattr(interpretation.spec, "intent", ""), _MAX_OBJECTIVE_CHARS
            )
            if role is TurnRole.CORRECTION and interpretation.corrections:
                corrected = _bounded(
                    interpretation.corrections[-1].corrected,
                    _MAX_OBJECTIVE_CHARS,
                )
                if corrected:
                    updates["current_objective"] = corrected
                elif objective:
                    updates["current_objective"] = objective
            elif role is TurnRole.NEW_OBJECTIVE and objective:
                updates["current_objective"] = objective
        if interpretation.subtasks:
            updates["subtasks"] = interpretation.subtasks[:MAX_SUBTASKS]
        if interpretation.corrections:
            prior: tuple[Correction, ...] = ()
            if state is not None and state.corrections:
                prior = tuple(state.corrections)
            merged = (prior + interpretation.corrections)[-MAX_CORRECTIONS:]
            updates["corrections"] = merged
        return updates

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_correction(
        text: str,
        spec: TaskSpec,
        state: ConversationState | None,
    ) -> tuple[Correction, ...]:
        """Detect a bounded correction/amendment, or return ``()`.

        Only fires when a prior conversational objective exists and a bounded
        correction cue is present. The result RECORDS the superseded reading and
        the replacement; it does not change routing or authority.

        Evidence-Driven Improvement 2 — the recorded replacement is the bounded
        extracted SUBJECT (the corrected reading the turn installs), so the
        correction can drive the active interpretation rather than only being
        appended as evidence.
        """
        if state is None or not state.current_objective:
            return ()
        if not isinstance(text, str) or not text.strip():
            return ()
        lowered = text.lower()
        if not any(marker in lowered for marker in _CORRECTION_MARKERS):
            return ()
        corrected = corrected_subject(text) or _bounded(
            spec.intent or text, _MAX_OBJECTIVE_CHARS
        )
        if not corrected:
            return ()
        return (
            Correction(
                previous=_bounded(state.current_objective, _MAX_OBJECTIVE_CHARS),
                corrected=corrected,
                turn_id=state.turn_id,
            ),
        )
