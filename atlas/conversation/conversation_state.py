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

    This is the minimal P9.1 lifecycle surface: create/read/update/clear.
    P9.2 enriches this with integration semantics.
    """

    def __init__(self, state: Optional[ConversationState] = None) -> None:
        self._state: ConversationState = state or ConversationState()

    @property
    def state(self) -> ConversationState:
        """Return the current immutable state."""
        return self._state

    def update(self, **fields: Any) -> ConversationState:
        """Return a new state with the given fields merged (immutable update).

        Unknown fields are ignored so callers cannot accidentally inject
        state the contract does not define.
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
