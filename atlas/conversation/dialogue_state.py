"""Atlas Conversation — bounded dialogue / information state (Stage 2).

The bounded, deterministic **semantic-dialogue section** of the EXISTING
:class:`~atlas.conversation.conversation_state.ConversationState`. It records the
evolving state of an ongoing conversation — the current objective/subject/topic,
the current turn's bounded reading, whether a clarification is outstanding or was
resolved, the active plan's bounded status, and a small bounded window of recent
SEMANTIC turn summaries — so later conversational stages (L3/L4/L5/L6) have a
single, coherent place to build on.

Boundaries (mandatory):

  * Single source of truth — this is NOT a second conversation store. It is a
    field of ``ConversationState`` and is written only through the existing
    :class:`ConversationStateManager` (the single owner/serialization point).
  * Representation only — it never routes, authorizes, approves, executes,
    promotes, mutates governed state, or contacts a model/provider. It carries no
    authority field of any kind.
  * Route-independent recording — the state transition is a single pure function
    (:func:`apply_turn`); WHICH handler ran never decides whether it is recorded.
  * Deterministic and model-independent — standard library only, no clock, no
    randomness, no I/O, no network, no model.
  * Bounded and JSON-safe — every string is length-capped, ``recent`` is capped at
    :data:`MAX_RECENT_TURNS`, and nothing copies the conversation transcript.

Later-stage concepts (discourse referents / operation-result identity /
QUD-thread management / communicative-function routing) are deliberately NOT
implemented here; they will extend this container in Stage 3/5 rather than create
a competing store. There are no placeholder fields pretending those exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # annotations only — never imported at runtime (avoids cycles)
    from atlas.conversation.conversation_state import ConversationState
    from atlas.conversation.meaning import AtlasMeaning

#: Upper bound on retained recent SEMANTIC turn summaries (oldest dropped).
MAX_RECENT_TURNS: int = 8

#: Clarification status values. ``pending`` = a clarification is outstanding
#: after this turn; ``resolved`` = this turn resolved a previously pending one;
#: ``none`` = no clarification is involved.
STATUS_NONE: str = "none"
STATUS_PENDING: str = "pending"
STATUS_RESOLVED: str = "resolved"

#: Hard string bounds (a malformed/oversized turn can never produce unbounded state).
_MAX_ROLE_CHARS: int = 40
_MAX_ACT_CHARS: int = 20
_MAX_SUBJECT_CHARS: int = 200
_MAX_OBJECTIVE_CHARS: int = 400
_MAX_QUESTION_CHARS: int = 300
_MAX_STATUS_CHARS: int = 32
_MAX_KIND_CHARS: int = 32
_MAX_TURN_INDEX: int = 1_000_000


def _bounded(value: Any, limit: int) -> str:
    """Return a trimmed, length-bounded string (non-strings degrade to ``""``)."""
    return value.strip()[:limit] if isinstance(value, str) else ""


def _bounded_index(value: Any) -> int:
    """Return a bounded non-negative conversation index (0 on malformed input)."""
    try:
        index = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(index, _MAX_TURN_INDEX))


@dataclass(frozen=True, slots=True)
class DialogueTurn:
    """One bounded SEMANTIC summary of a turn (never the turn's full text).

    Deliberately small: only the deterministic, already-known reading of the
    turn. It is not a transcript record and stores no message content.
    """

    turn_index: int = 0
    role: str = ""
    act: str = ""
    objective: str = ""
    subject: str = ""
    topic: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "turn_index": self.turn_index,
            "role": self.role,
            "act": self.act,
            "objective": self.objective,
            "subject": self.subject,
            "topic": self.topic,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["DialogueTurn"]:
        """Rebuild from a serialized dict, or ``None`` when malformed."""
        if not isinstance(data, dict):
            return None
        return cls(
            turn_index=_bounded_index(data.get("turn_index")),
            role=_bounded(data.get("role"), _MAX_ROLE_CHARS),
            act=_bounded(data.get("act"), _MAX_ACT_CHARS),
            objective=_bounded(data.get("objective"), _MAX_OBJECTIVE_CHARS),
            subject=_bounded(data.get("subject"), _MAX_SUBJECT_CHARS),
            topic=_bounded(data.get("topic"), _MAX_SUBJECT_CHARS),
        )


@dataclass(frozen=True, slots=True)
class DialogueState:
    """Bounded, deterministic semantic-dialogue state (facts only).

    A snapshot of the conversation's current semantic-dialogue facts plus a small
    bounded window of recent turn summaries. Every existing ``ConversationState``
    field it overlaps with stays AUTHORITATIVE; the dialogue snapshot mirrors it
    for the dialogue layer and never overrides it.
    """

    #: Deterministic conversation order at which this state was recorded.
    turn_index: int = 0

    #: The current turn's bounded conversational role (e.g. ``new_objective``).
    turn_role: str = ""

    #: The current turn's bounded speech act where already known
    #: (``question`` / ``request`` / ``statement``; ``""`` when unknown).
    act: str = ""

    #: The current bounded objective (mirror of ``current_objective``/goal).
    objective: str = ""

    #: The current bounded subject (mirror of ``current_subject``/turn topic).
    subject: str = ""

    #: The ACTIVE world topic label and kind (mirror of the world state).
    topic: str = ""
    topic_kind: str = ""

    #: Outstanding/resolved clarification status and its bounded question.
    clarification_status: str = STATUS_NONE
    clarification_question: str = ""

    #: The active plan's bounded status/objective (mirror of ``current_plan``).
    plan_status: str = ""
    plan_objective: str = ""

    #: Bounded window of recent SEMANTIC turn summaries (most recent first).
    recent: tuple[DialogueTurn, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "turn_index": self.turn_index,
            "turn_role": self.turn_role,
            "act": self.act,
            "objective": self.objective,
            "subject": self.subject,
            "topic": self.topic,
            "topic_kind": self.topic_kind,
            "clarification_status": self.clarification_status,
            "clarification_question": self.clarification_question,
            "plan_status": self.plan_status,
            "plan_objective": self.plan_objective,
            "recent": [turn.to_dict() for turn in self.recent],
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["DialogueState"]:
        """Rebuild from a serialized dict, or ``None`` when malformed."""
        if not isinstance(data, dict):
            return None
        status = _bounded(data.get("clarification_status"), _MAX_STATUS_CHARS)
        if status not in (STATUS_NONE, STATUS_PENDING, STATUS_RESOLVED):
            status = STATUS_NONE
        recent: list[DialogueTurn] = []
        raw_recent = data.get("recent")
        if isinstance(raw_recent, (list, tuple)):
            for item in raw_recent:
                turn = item if isinstance(item, DialogueTurn) else DialogueTurn.from_dict(item)
                if turn is not None:
                    recent.append(turn)
        return cls(
            turn_index=_bounded_index(data.get("turn_index")),
            turn_role=_bounded(data.get("turn_role"), _MAX_ROLE_CHARS),
            act=_bounded(data.get("act"), _MAX_ACT_CHARS),
            objective=_bounded(data.get("objective"), _MAX_OBJECTIVE_CHARS),
            subject=_bounded(data.get("subject"), _MAX_SUBJECT_CHARS),
            topic=_bounded(data.get("topic"), _MAX_SUBJECT_CHARS),
            topic_kind=_bounded(data.get("topic_kind"), _MAX_KIND_CHARS),
            clarification_status=status,
            clarification_question=_bounded(
                data.get("clarification_question"), _MAX_QUESTION_CHARS
            ),
            plan_status=_bounded(data.get("plan_status"), _MAX_STATUS_CHARS),
            plan_objective=_bounded(data.get("plan_objective"), _MAX_OBJECTIVE_CHARS),
            recent=tuple(recent)[:MAX_RECENT_TURNS],
        )


@dataclass(frozen=True, slots=True)
class DialogueTurnOutcome:
    """The explicit, bounded inputs to a dialogue-state transition.

    Produced by :func:`outcome_from` from the EXISTING turn interpretation (the
    Stage 1 ``AtlasMeaning``) plus the EXISTING ``ConversationState`` facts. It is
    a value object only — no authority, no behaviour.
    """

    turn_index: int = 0
    turn_role: str = ""
    act: str = ""
    objective: str = ""
    subject: str = ""
    topic: str = ""
    topic_kind: str = ""
    clarification_pending: bool = False
    clarification_question: str = ""
    plan_status: str = ""
    plan_objective: str = ""


def outcome_from(
    meaning: "AtlasMeaning | Any | None",
    state: "ConversationState | Any | None",
    *,
    turn_index: int = 0,
) -> DialogueTurnOutcome:
    """Map the EXISTING meaning + state facts to a bounded transition outcome.

    Pure and duck-typed: it reads only attributes that already exist on the Stage
    1 ``AtlasMeaning`` and on ``ConversationState`` (and their nested
    ``world`` / ``current_plan`` / ``pending_clarification``). It never re-parses
    text, never re-classifies, and never invents a value — absent facts degrade to
    empty/neutral defaults.
    """
    evidence = getattr(meaning, "communicative_function_evidence", None)
    evidence = evidence if isinstance(evidence, dict) else {}
    semantic = getattr(meaning, "semantic_intake", None)
    act = _bounded(getattr(semantic, "act", ""), _MAX_ACT_CHARS) or _bounded(
        evidence.get("illocution"), _MAX_ACT_CHARS
    )

    world = getattr(state, "world", None)
    pending = getattr(state, "pending_clarification", None)
    plan = getattr(state, "current_plan", None)

    return DialogueTurnOutcome(
        turn_index=_bounded_index(turn_index),
        turn_role=_bounded(getattr(meaning, "turn_role", ""), _MAX_ROLE_CHARS),
        act=act,
        objective=_bounded(
            getattr(state, "current_objective", None)
            or getattr(meaning, "user_goal", ""),
            _MAX_OBJECTIVE_CHARS,
        ),
        subject=_bounded(
            getattr(state, "current_subject", None)
            or getattr(meaning, "topic", ""),
            _MAX_SUBJECT_CHARS,
        ),
        topic=_bounded(getattr(world, "active_topic", ""), _MAX_SUBJECT_CHARS),
        topic_kind=_bounded(getattr(world, "active_kind", ""), _MAX_KIND_CHARS),
        clarification_pending=pending is not None,
        clarification_question=(
            _bounded(getattr(pending, "question", ""), _MAX_QUESTION_CHARS)
            if pending is not None
            else ""
        ),
        plan_status=(
            _bounded(plan.get("state", ""), _MAX_STATUS_CHARS)
            if isinstance(plan, dict)
            else ""
        ),
        plan_objective=(
            _bounded(plan.get("objective", ""), _MAX_OBJECTIVE_CHARS)
            if isinstance(plan, dict)
            else ""
        ),
    )


def apply_turn(current: "DialogueState | None", outcome: "DialogueTurnOutcome") -> DialogueState:
    """The single, deterministic dialogue-state transition (pure).

    ``current`` is the state produced by the PREVIOUS turn (or ``None``); it is
    used ONLY to detect the clarification transition (a previously pending
    clarification that is no longer outstanding is RECORDED as ``resolved``) and
    to keep the bounded recent-turn window. Nothing is invented: a status/objective
    with no evidence stays empty/neutral.
    """
    base = current if isinstance(current, DialogueState) else DialogueState()

    if outcome.clarification_pending:
        status = STATUS_PENDING
        question = outcome.clarification_question
    elif base.clarification_status == STATUS_PENDING:
        status = STATUS_RESOLVED
        question = base.clarification_question
    else:
        status = STATUS_NONE
        question = ""

    # The transition is the single bound-enforcement point: every field is
    # re-bounded here, so a malformed/oversized outcome can never produce
    # unbounded state regardless of how it was constructed.
    turn = DialogueTurn(
        turn_index=_bounded_index(outcome.turn_index),
        role=_bounded(outcome.turn_role, _MAX_ROLE_CHARS),
        act=_bounded(outcome.act, _MAX_ACT_CHARS),
        objective=_bounded(outcome.objective, _MAX_OBJECTIVE_CHARS),
        subject=_bounded(outcome.subject, _MAX_SUBJECT_CHARS),
        topic=_bounded(outcome.topic, _MAX_SUBJECT_CHARS),
    )
    recent = (turn,) + tuple(base.recent)
    recent = recent[:MAX_RECENT_TURNS]

    return DialogueState(
        turn_index=_bounded_index(outcome.turn_index),
        turn_role=_bounded(outcome.turn_role, _MAX_ROLE_CHARS),
        act=_bounded(outcome.act, _MAX_ACT_CHARS),
        objective=_bounded(outcome.objective, _MAX_OBJECTIVE_CHARS),
        subject=_bounded(outcome.subject, _MAX_SUBJECT_CHARS),
        topic=_bounded(outcome.topic, _MAX_SUBJECT_CHARS),
        topic_kind=_bounded(outcome.topic_kind, _MAX_KIND_CHARS),
        clarification_status=status,
        clarification_question=_bounded(question, _MAX_QUESTION_CHARS),
        plan_status=_bounded(outcome.plan_status, _MAX_STATUS_CHARS),
        plan_objective=_bounded(outcome.plan_objective, _MAX_OBJECTIVE_CHARS),
        recent=recent,
    )


__all__ = [
    "MAX_RECENT_TURNS",
    "STATUS_NONE",
    "STATUS_PENDING",
    "STATUS_RESOLVED",
    "DialogueTurn",
    "DialogueState",
    "DialogueTurnOutcome",
    "outcome_from",
    "apply_turn",
]
