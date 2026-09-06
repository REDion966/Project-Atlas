"""Atlas Conversation — Reference Resolution (P9.3).

Deterministic, conservative resolution of conversational references such as
"that problem", "that task", "run it again", "what did you find?" against the
structured :class:`ConversationState` established by P9.1/P9.2.

Core safety invariant::

    AMBIGUITY -> CLARIFICATION. NEVER GUESS.

The resolver NEVER uses an LLM, NEVER performs semantic guessing, and NEVER
silently selects one candidate when multiple plausible referents exist.

Resolution statuses:
  - RESOLVED   -> exactly one valid referent
  - UNRESOLVED -> no valid referent
  - AMBIGUOUS  -> more than one plausible referent

This module is side-effect free, authorization-independent, and
execution-independent. It produces only structured information.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from atlas.conversation.conversation_state import ConversationState


class ReferenceResolutionStatus(str, Enum):
    """Outcome of attempting to resolve a conversational reference."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class ReferenceResolutionResult:
    """Immutable result of a reference-resolution attempt.

    Carries enough structure for a caller to generate a clarification request
    without guessing.
    """

    status: ReferenceResolutionStatus
    query: str
    resolved_field: Optional[str] = None
    resolved_value: Optional[str] = None
    candidates: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "status": self.status.value,
            "query": self.query,
            "resolved_field": self.resolved_field,
            "resolved_value": self.resolved_value,
            "candidates": list(self.candidates),
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Reference patterns: (trigger_phrases, candidate_fields, category_name)
#
# CRITICAL: patterns are sorted by longest phrase length (descending) so that
# multi-word phrases ("that investigation") are checked before single-word
# substrings ("that"). Without this, "that" would greedily match first and
# misclassify "that investigation" as a subject reference.
# ---------------------------------------------------------------------------

_REFERENCE_PATTERNS: tuple[tuple[tuple[str, ...], tuple[str, ...], str], ...] = (
    # "what you found" may refer to investigation or result
    (
        ("what you just found", "what did you find", "what you found"),
        ("current_investigation", "latest_result"),
        "findings",
    ),
    # Continuation references
    (
        ("continue with that", "continue"),
        ("current_task", "current_investigation", "development_intent"),
        "continuation",
    ),
    # Action references (repeat/again)
    (
        ("do that again", "run it again", "repeat that", "again"),
        ("current_task", "relevant_prior_action"),
        "action",
    ),
    # Investigation references
    (
        ("this investigation", "that investigation", "the investigation"),
        ("current_investigation",),
        "investigation",
    ),
    # Subject references (multi-word first)
    (
        ("this topic", "that topic", "this issue", "that issue", "the problem"),
        ("current_subject",),
        "subject",
    ),
    # Task references
    (
        ("this task", "that task", "the task"),
        ("current_task",),
        "task",
    ),
    # Result references
    (
        ("that result", "the result", "the findings"),
        ("latest_result",),
        "result",
    ),
    # Development intent references
    (
        ("that improvement", "the development"),
        ("development_intent",),
        "development",
    ),
    # Pending question
    (
        ("the question", "my question"),
        ("pending_question",),
        "question",
    ),
    # Pending confirmation
    (
        ("that confirmation", "the confirmation"),
        ("pending_confirmation",),
        "confirmation",
    ),
    # "it" resolves only to the active task (conservative, single-word last)
    (
        ("it",),
        ("current_task",),
        "task",
    ),
    # Single-word subject triggers (checked last — most generic)
    (
        ("this", "that"),
        ("current_subject",),
        "subject",
    ),
)


class ConversationReferenceResolver:
    """Deterministic resolver of conversational references against state.

    Side-effect free: never mutates the supplied :class:`ConversationState`.
    """

    def resolve(
        self,
        query: str,
        state: ConversationState,
    ) -> ReferenceResolutionResult:
        """Resolve a conversational reference against structured state.

        Args:
            query: the raw reference phrase (e.g. "run it again").
            state: the current :class:`ConversationState`.

        Returns:
            A structured :class:`ReferenceResolutionResult`.
        """
        normalized = query.strip().lower()

        # Find the first matching reference pattern.
        matched_fields: Optional[tuple[str, ...]] = None
        category: str = "unknown"
        for phrases, fields, cat in _REFERENCE_PATTERNS:
            if any(phrase in normalized for phrase in phrases):
                matched_fields = fields
                category = cat
                break

        if matched_fields is None:
            return ReferenceResolutionResult(
                status=ReferenceResolutionStatus.UNRESOLVED,
                query=query,
                reason=f"Unrecognized reference: no pattern matches {query!r}.",
            )

        # Collect candidate fields that have a value in the current state.
        candidates = [
            f for f in matched_fields if getattr(state, f) is not None
        ]

        if len(candidates) == 0:
            return ReferenceResolutionResult(
                status=ReferenceResolutionStatus.UNRESOLVED,
                query=query,
                reason=f"No active {category} found in current state.",
            )

        if len(candidates) == 1:
            field = candidates[0]
            return ReferenceResolutionResult(
                status=ReferenceResolutionStatus.RESOLVED,
                query=query,
                resolved_field=field,
                resolved_value=getattr(state, field),
                reason=f"Unique {category} referent resolved to {field}.",
            )

        # Multiple plausible referents -> ambiguous, never guess.
        return ReferenceResolutionResult(
            status=ReferenceResolutionStatus.AMBIGUOUS,
            query=query,
            candidates=tuple(candidates),
            reason=(
                f"Multiple plausible {category} referents: "
                f"{', '.join(candidates)}. Clarification required."
            ),
        )
