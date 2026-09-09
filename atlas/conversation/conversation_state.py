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
            "development_intent": self.development_intent,
            "pending_question": self.pending_question,
            "pending_confirmation": self.pending_confirmation,
            "latest_result": self.latest_result,
            "relevant_prior_action": self.relevant_prior_action,
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
