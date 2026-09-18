"""Atlas Conversation — Bounded Conversational Context (Phase 3).

A deterministic, immutable *projection* of a small, bounded window of the
existing :class:`~atlas.conversation.conversation.Conversation` history plus
the structured :class:`~atlas.conversation.conversation_state.ConversationState`.

It exists so the deterministic conversational layer can be handed the context
that already exists inside Atlas without ever receiving the mutable
authoritative objects. Phase 3 exposes this context only; consuming it for
interpretation belongs to later, separately reviewed phases.

Safety contract:
  * Projection, never a replacement — ``Conversation`` and
    ``ConversationStateManager`` remain the authoritative sources.
  * Read-only and immutable (frozen dataclasses, tuple fields).
  * Bounded: at most :data:`MAX_CONTEXT_TURNS` recent messages, each truncated
    to :data:`MAX_CONTEXT_CHARS`.
  * Deterministic: no clock, no randomness, no I/O.
  * No execution, no authority, no provider, no repository access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from atlas.conversation.conversation_state import ConversationState

#: Maximum number of recent messages exposed in a context snapshot.
MAX_CONTEXT_TURNS: int = 10

#: Maximum characters retained per exposed message content.
MAX_CONTEXT_CHARS: int = 500


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """One bounded, read-only view of a conversation message."""

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ConversationContext:
    """Immutable, bounded snapshot of recent conversation state.

    Attributes:
        recent_turns: Bounded window of the most recent messages, oldest first.
        recent_user_turns: Contents of the recent user turns in the window.
        recent_assistant_turns: Contents of the recent assistant turns.
        total_messages: Total messages in the source conversation (not the
            window size).
        state: The structured :class:`ConversationState` for the turn.
    """

    recent_turns: tuple[ConversationTurn, ...] = ()
    recent_user_turns: tuple[str, ...] = ()
    recent_assistant_turns: tuple[str, ...] = ()
    total_messages: int = 0
    state: ConversationState = field(default_factory=ConversationState)

    @property
    def has_history(self) -> bool:
        """True when the bounded window contains at least one message."""
        return bool(self.recent_turns)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe serialization (bounded; no raw authoritative objects)."""
        return {
            "recent_turns": [
                {"role": turn.role, "content": turn.content}
                for turn in self.recent_turns
            ],
            "recent_user_turns": list(self.recent_user_turns),
            "recent_assistant_turns": list(self.recent_assistant_turns),
            "total_messages": self.total_messages,
            "state": self.state.to_dict(),
        }


def _bounded_content(content: Any) -> str:
    """Return bounded text for one message content value."""
    text = content if isinstance(content, str) else ""
    return text[:MAX_CONTEXT_CHARS]


def _bounded_role(role: Any) -> str:
    """Return a bounded role string for one message."""
    return role if isinstance(role, str) else ""


def build_conversation_context(
    messages: Iterable[Any] | None,
    state: ConversationState | None = None,
) -> ConversationContext:
    """Build a bounded, immutable context projection.

    Reads only the last :data:`MAX_CONTEXT_TURNS` messages; older turns are
    never exposed. The source objects are copied by value and never retained,
    so later mutation of the conversation cannot change the snapshot.
    """
    materialized = list(messages) if messages is not None else []
    window = materialized[-MAX_CONTEXT_TURNS:] if MAX_CONTEXT_TURNS > 0 else []
    recent_turns = tuple(
        ConversationTurn(
            role=_bounded_role(getattr(message, "role", "")),
            content=_bounded_content(getattr(message, "content", "")),
        )
        for message in window
    )
    return ConversationContext(
        recent_turns=recent_turns,
        recent_user_turns=tuple(
            turn.content for turn in recent_turns if turn.role == "user"
        ),
        recent_assistant_turns=tuple(
            turn.content for turn in recent_turns if turn.role == "assistant"
        ),
        total_messages=len(materialized),
        state=state if state is not None else ConversationState(),
    )
