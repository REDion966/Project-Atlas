"""Atlas Conversation — Structured Conversational State (P9.1).

A dedicated, typed, deterministic state container for facts about the
current conversation turn so that later stages (P9.3) can resolve references
such as "that problem", "that change", "run it again", "continue", "fix that".

This is NOT:
- general memory (see atlas/memory, atlas/longterm)
- session identity/authority (see atlas/session)
- model prompt/context assembly (see atlas/conversation/context.py)
- a decision surface — it stores facts, never executes/approves/promotes

Design contract:
  * Immutable value object (frozen, slots): every update produces a new state.
  * Explicitly typed: every field is Optional; absence is None.
  * Independent of authorization: holds no principal/authority.
  * Session-safe: one manager instance per conversation context.
  * Serializable: to_dict() for downstream consumers.

P9.1 establishes the CONTRACT and core container.
P9.2 defines lifecycle integration.
P9.3 defines reference resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import uuid

from atlas.conversation.entity_capture import CapturedEntity

#: Bound applied to a retained governed-operation operand.
_MAX_OPERATION_OPERAND_CHARS: int = 500

#: NLU-4 — upper bound on conversation-scoped captured entities retained.
MAX_CAPTURED_ENTITIES: int = 8

#: D1 — bound applied to a retained corrective reading.
_MAX_CORRECTION_CHARS: int = 300

#: D1 — upper bound on retained corrections (older superseded readings dropped).
MAX_CORRECTIONS: int = 5

#: D1 — upper bound on retained compound subtasks.
MAX_SUBTASKS: int = 4


@dataclass(frozen=True, slots=True)
class Correction:
    """A user correction/amendment (D1): a superseded reading and its replacement.

    Facts only — it records that the user superseded a prior conversational
    objective and what they said instead. It never re-routes anything and is
    never authority (it cannot approve, authorize, execute, or promote).
    """

    previous: str
    corrected: str
    turn_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "previous": self.previous,
            "corrected": self.corrected,
            "turn_id": self.turn_id,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["Correction"]:
        """Rebuild from a serialized dict, or ``None`` when malformed."""
        if not isinstance(data, dict):
            return None
        previous = data.get("previous")
        corrected = data.get("corrected")
        if not isinstance(previous, str) or not previous.strip():
            return None
        if not isinstance(corrected, str) or not corrected.strip():
            return None
        turn_id = data.get("turn_id")
        return cls(
            previous=previous.strip()[:_MAX_CORRECTION_CHARS],
            corrected=corrected.strip()[:_MAX_CORRECTION_CHARS],
            turn_id=turn_id if isinstance(turn_id, str) else "",
        )



@dataclass(frozen=True, slots=True)
class GovernedOperation:
    """The single most recent governed operation (facts only, no history).

    ``kind`` is the existing :class:`~atlas.conversation.task_intake.TaskType`
    value (e.g. ``"investigation_request"``), ``operand`` is the operation's
    retained target when one exists, and ``proposal_id`` links a
    proposal-backed operation.

    This is a *fact* about what actually happened — never an interpretation of
    what the user meant and never authority. It is deliberately single-valued:
    recording a new operation replaces the previous one, and there is no
    operation history or action ledger.
    """

    kind: str
    operand: Optional[str] = None
    proposal_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "kind": self.kind,
            "operand": self.operand,
            "proposal_id": self.proposal_id,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["GovernedOperation"]:
        """Rebuild from a serialized dict, or ``None`` when malformed."""
        if not isinstance(data, dict):
            return None
        kind = data.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            return None
        operand = data.get("operand")
        proposal_id = data.get("proposal_id")
        return cls(
            kind=kind.strip(),
            operand=(
                operand.strip()[:_MAX_OPERATION_OPERAND_CHARS]
                if isinstance(operand, str) and operand.strip()
                else None
            ),
            proposal_id=(
                proposal_id.strip()
                if isinstance(proposal_id, str) and proposal_id.strip()
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class ConversationState:
    """Immutable structured facts about the current conversation turn.

    Every field is Optional. Absence is always ``None`` — there is no
    sentinel string. Consumers must handle ``None`` explicitly.
    """

    # What the conversation is currently about (free-form, bounded subject).
    current_subject: Optional[str] = None

    # Stable reference (e.g. task id) of the active task, when one exists.
    current_task: Optional[str] = None

    # Stable reference of an active investigation, when one exists.
    current_investigation: Optional[str] = None

    # Stable reference of an active proposal, when one exists.
    active_proposal_id: Optional[str] = None

    # Fingerprint of the active proposal at the time of approval, for strict
    # binding verification.
    active_proposal_fingerprint: Optional[str] = None

    # Stable reference of a pending approval, when one exists.
    pending_approval_id: Optional[str] = None

    # Stable reference of a converted EvolutionProposal (from InvestigationProposal),
    # when one exists. Tracks the governed development proposal created from
    # an investigation.
    evolution_proposal_id: Optional[str] = None

    # Stable reference of a recovery EvolutionProposal created after a
    # REVISE_AND_RETRY recovery decision. Distinct from the original proposal.
    recovery_proposal_id: Optional[str] = None

    # Stable reference of the pending recovery approval request. Distinct from
    # the original development approval.
    recovery_approval_id: Optional[str] = None

    # L1/L2 autonomy tracking: number of steps executed autonomously.
    autonomous_steps_executed: int = 0

    # L1/L2 autonomy tracking: summary of last autonomous decision.
    last_autonomy_decision: Optional[str] = None

    # L2 autonomy tracking: IDs of chained workflows.
    chained_workflows: tuple[str, ...] = ()

    # L2 autonomy tracking: summary of last L2-specific decision.
    last_l2_decision: Optional[str] = None

    # L3 autonomy tracking: number of autonomous recoveries executed.
    autonomous_recoveries: int = 0

    # L3 autonomy tracking: number of sub-plans generated.
    sub_plans_generated: int = 0

    # L3 autonomy tracking: summary of last L3-specific decision.
    last_l3_decision: Optional[str] = None

    # L4 autonomy tracking: number of capabilities acquired.
    capabilities_acquired: int = 0

    # L4 autonomy tracking: summary of last L4-specific decision.
    last_l4_decision: Optional[str] = None

    # L5 autonomy tracking: number of objectives coordinated.
    coordinated_objectives: int = 0

    # L5 autonomy tracking: summary of last L5-specific decision.
    last_l5_decision: Optional[str] = None

    # Current development-related intent description, when one exists.
    development_intent: Optional[str] = None

    # Question Atlas is currently waiting for an answer to.
    pending_question: Optional[str] = None

    # Confirmation that is currently awaiting user response (description).
    pending_confirmation: Optional[str] = None

    # Reference/id of the most recent meaningful result or output.
    latest_result: Optional[str] = None

    # Reference/id of the most recent meaningful action (for "that action").
    relevant_prior_action: Optional[str] = None

    # The single most recent governed operation (facts only; no history).
    last_operation: Optional[GovernedOperation] = None

    # NLU-4 — bounded, conversation-scoped entities the user explicitly named
    # (most recent last). Provenance-carrying references only; never a durable
    # memory store, never a verified fact, never authority.
    captured_entities: tuple[CapturedEntity, ...] = ()

    # D1 — the current bounded conversational objective, when one is expressed.
    # A representation of what the human is asking for — never what Atlas is
    # authorized to do.
    current_objective: Optional[str] = None

    # D1 — bounded, ordered subtasks of a compound request (representation
    # only; execution, if any, remains with existing governed systems).
    subtasks: tuple[str, ...] = ()

    # D1 — bounded record of user corrections/amendments (superseded readings).
    corrections: tuple[Correction, ...] = ()

    # Evidence-driven improvement 1 — the immediately preceding knowledge
    # answer, retained so bare follow-ups ("what did you find?", "what source
    # supports that?", "can you continue?") can resolve against it. Bounded,
    # conversation-scoped FACTS only; never authority, never a second store.
    last_knowledge: Optional[dict[str, Any]] = None

    # Turn/reference identity distinguishing this state across turns.
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "current_subject": self.current_subject,
            "current_task": self.current_task,
            "current_investigation": self.current_investigation,
            "active_proposal_id": self.active_proposal_id,
            "active_proposal_fingerprint": self.active_proposal_fingerprint,
            "pending_approval_id": self.pending_approval_id,
            "evolution_proposal_id": self.evolution_proposal_id,
            "recovery_proposal_id": self.recovery_proposal_id,
            "recovery_approval_id": self.recovery_approval_id,
            "autonomous_steps_executed": self.autonomous_steps_executed,
            "last_autonomy_decision": self.last_autonomy_decision,
            "chained_workflows": list(self.chained_workflows),
            "last_l2_decision": self.last_l2_decision,
            "autonomous_recoveries": self.autonomous_recoveries,
            "sub_plans_generated": self.sub_plans_generated,
            "last_l3_decision": self.last_l3_decision,
            "capabilities_acquired": self.capabilities_acquired,
            "last_l4_decision": self.last_l4_decision,
            "coordinated_objectives": self.coordinated_objectives,
            "last_l5_decision": self.last_l5_decision,
            "development_intent": self.development_intent,
            "pending_question": self.pending_question,
            "pending_confirmation": self.pending_confirmation,
            "latest_result": self.latest_result,
            "relevant_prior_action": self.relevant_prior_action,
            "last_operation": (
                self.last_operation.to_dict()
                if self.last_operation is not None
                else None
            ),
            "captured_entities": [
                entity.to_dict() for entity in self.captured_entities
            ],
            "current_objective": self.current_objective,
            "subtasks": list(self.subtasks),
            "corrections": [c.to_dict() for c in self.corrections],
            "last_knowledge": (
                dict(self.last_knowledge)
                if isinstance(self.last_knowledge, dict)
                else None
            ),
            "turn_id": self.turn_id,
        }


class ConversationStateManager:
    """Holds and updates the immutable ConversationState for one conversation.

    One instance per conversation/session context. Not global mutable state.
    Thread-safe in the sense that each context holds its own manager.

    P9.1 established create/read/update/clear.
    P9.2 adds lifecycle semantics: turn boundaries, topic replacement,
    explicit expiration, and result recording.
    """

    def __init__(self, state: Optional[ConversationState] = None) -> None:
        self._state: ConversationState = state or ConversationState()

    @property
    def state(self) -> ConversationState:
        """Return the current immutable state."""
        return self._state

    # ------------------------------------------------------------------
    # P9.1 surface (preserved)
    # ------------------------------------------------------------------

    def update(self, **fields: Any) -> ConversationState:
        """Return a new state with the given fields merged (immutable update).

        Unknown fields are ignored so callers cannot accidentally inject
        state the contract does not define. Does NOT regenerate turn_id —
        minor refinements stay within the same turn.
        """
        known = {f.name for f in self._state.__dataclass_fields__.values()}
        merged = {
            k: v for k, v in {**self._state.to_dict(), **fields}.items()
            if k in known
        }
        # ``to_dict`` serializes the retained operation to a plain dict; rebuild
        # the typed value so the immutable state keeps its contract.
        if isinstance(merged.get("last_operation"), dict):
            merged["last_operation"] = GovernedOperation.from_dict(
                merged["last_operation"]
            )
        # Likewise rebuild the bounded captured-entity records (NLU-4).
        raw_entities = merged.get("captured_entities")
        if isinstance(raw_entities, (list, tuple)):
            rebuilt: list[CapturedEntity] = []
            for item in raw_entities:
                entity = (
                    item
                    if isinstance(item, CapturedEntity)
                    else CapturedEntity.from_dict(item)
                )
                if entity is not None:
                    rebuilt.append(entity)
            merged["captured_entities"] = tuple(rebuilt)
        # D1 — rebuild bounded subtasks and correction records so a
        # to_dict round-trip preserves their types.
        raw_subtasks = merged.get("subtasks")
        if isinstance(raw_subtasks, (list, tuple)):
            merged["subtasks"] = tuple(
                item.strip()[:200]
                for item in raw_subtasks
                if isinstance(item, str) and item.strip()
            )[:MAX_SUBTASKS]
        raw_corrections = merged.get("corrections")
        if isinstance(raw_corrections, (list, tuple)):
            rebuilt_corrections: list[Correction] = []
            for item in raw_corrections:
                correction = (
                    item if isinstance(item, Correction) else Correction.from_dict(item)
                )
                if correction is not None:
                    rebuilt_corrections.append(correction)
            merged["corrections"] = tuple(rebuilt_corrections)[-MAX_CORRECTIONS:]
        # Retained knowledge fact must stay a plain dict (or None).
        if not isinstance(merged.get("last_knowledge"), dict):
            merged["last_knowledge"] = None
        self._state = ConversationState(**merged)
        return self._state

    def clear(self) -> ConversationState:
        """Reset to a fresh empty state (new turn_id)."""
        self._state = ConversationState()
        return self._state

    def reset_field(self, field_name: str) -> ConversationState:
        """Clear a single field by name (set to None). Unknown names ignored."""
        if field_name not in self._state.__dataclass_fields__:
            return self._state
        return self.update(**{field_name: None})

    # ------------------------------------------------------------------
    # P9.2 lifecycle
    # ------------------------------------------------------------------

    def begin_turn(self) -> ConversationState:
        """Begin a new turn: regenerate turn_id, preserve all other state.

        A turn boundary is explicit and deterministic — the caller decides
        when a new turn begins. Minor updates within a turn do NOT change
        turn_id.
        """
        return self.update(turn_id=str(uuid.uuid4()))

    def replace_topic(
        self,
        new_subject: str,
        *,
        new_task: Optional[str] = None,
        new_investigation: Optional[str] = None,
        **other_fields: Any,
    ) -> ConversationState:
        """Handle a conflicting-topic transition deterministically.

        Rules (applied in order):
          1. An active ``current_task`` is demoted to ``relevant_prior_action``
             (unless a new task is supplied, in which case the old task is
             dropped — it is superseded, not accumulated).
          2. ``current_subject`` is replaced by ``new_subject``.
          3. ``current_task`` is set to ``new_task`` (or cleared).
          4. ``current_investigation`` is set to ``new_investigation`` (or cleared).
          5. ``development_intent`` is preserved (may still apply).
          6. ``pending_question`` / ``pending_confirmation`` are preserved
             (still awaiting response).
          7. ``latest_result`` is preserved (carries forward).
          8. ``turn_id`` is regenerated (new topic = new turn).
          9. Any ``**other_fields`` are merged on top.
        """
        fields: dict[str, Any] = {
            "current_subject": new_subject,
            "current_task": new_task,
            "current_investigation": new_investigation,
            "turn_id": str(uuid.uuid4()),
        }
        if new_task is not None:
            # Old task superseded entirely.
            fields["relevant_prior_action"] = None
        elif self._state.current_task is not None:
            # Active task demoted to prior action.
            fields["relevant_prior_action"] = self._state.current_task
        fields.update(other_fields)
        return self.update(**fields)

    def expire_field(self, field_name: str) -> ConversationState:
        """Explicitly expire a field (set to None).

        Expiration is deterministic and caller-driven: there is no time-based
        lifecycle primitive in Atlas, so a field expires only when explicitly
        marked expired or replaced. Unknown names are ignored.
        """
        return self.reset_field(field_name)

    def record_result(self, result: str) -> ConversationState:
        """Record a meaningful result.

        Sets ``latest_result``. If there is an active ``current_task``, it is
        demoted to ``relevant_prior_action`` (the task produced this result).
        """
        fields: dict[str, Any] = {"latest_result": result}
        if self._state.current_task is not None:
            fields["relevant_prior_action"] = self._state.current_task
        return self.update(**fields)

    def complete_task(self, result: Optional[str] = None) -> ConversationState:
        """Mark the current task as complete.

        Moves ``current_task`` to ``relevant_prior_action``, clears
        ``current_task`` and ``current_investigation``. Optionally records
        a ``latest_result``.
        """
        fields: dict[str, Any] = {
            "relevant_prior_action": self._state.current_task,
            "current_task": None,
            "current_investigation": None,
        }
        if result is not None:
            fields["latest_result"] = result
        return self.update(**fields)

    def record_operation(
        self,
        kind: str,
        operand: Optional[str] = None,
        proposal_id: Optional[str] = None,
    ) -> ConversationState:
        """Record the single most recent governed operation.

        Replaces any previously retained operation — there is no history. A
        blank/non-string ``kind`` is ignored (fail closed), so a malformed
        caller can never create a nameless operation.
        """
        operation = GovernedOperation.from_dict(
            {"kind": kind, "operand": operand, "proposal_id": proposal_id}
        )
        if operation is None:
            return self._state
        return self.update(last_operation=operation)

    def record_captured_entities(
        self,
        entities: "tuple[CapturedEntity, ...] | list[CapturedEntity]",
        *,
        limit: int = MAX_CAPTURED_ENTITIES,
    ) -> ConversationState:
        """Append bounded captured entities (NLU-4).

        Deduplicated by normalized name — re-mentioning an entity moves it to
        the most-recent position rather than adding a duplicate — and capped at
        ``MAX_CAPTURED_ENTITIES`` (oldest dropped). Non-``CapturedEntity``,
        blank, and over-long entries are ignored (fail closed).
        """
        if not entities:
            return self._state
        ordered: dict[str, CapturedEntity] = {}
        for entity in self._state.captured_entities or ():
            if isinstance(entity, CapturedEntity):
                ordered[entity.normalized or entity.name.lower()] = entity
        for entity in entities:
            if not isinstance(entity, CapturedEntity):
                continue
            name = entity.name.strip()
            if not name:
                continue
            key = entity.normalized or name.lower()
            ordered.pop(key, None)
            ordered[key] = CapturedEntity(
                name=name,
                normalized=key,
                turn_id=entity.turn_id,
            )
        bounded = tuple(list(ordered.values())[-max(1, limit):])
        return self.update(captured_entities=bounded)
