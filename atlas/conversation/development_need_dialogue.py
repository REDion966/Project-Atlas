"""Atlas Conversation — Development Need Dialogue (P7.3).

Pure, deterministic dialogue layer for P7.2's non-explicit development
signals. This is the EXPLANATION + CONFIRMATION half of conversational
self-development:

    detected need
        -> explain the opportunity
        -> ask for explicit confirmation
        -> interpret the user reply deterministically
        -> on CONFIRM: produce an explicit development INTENT hand-off
        -> on DENY / AMBIGUOUS / no context: nothing is developed

Critical invariant::

    DETECTION != DEVELOPMENT REQUEST

A detected opportunity must NEVER automatically become a governed
development request. Nothing is created, approved, executed, or promoted by
this module. The actual routing of a confirmed intent into the existing B3
intake / governed F9 pipeline is owned by P7.4; this module produces only a
small immutable :class:`ExplicitDevelopmentIntent` hand-off.

Design contract:
  * Pure: imports only conversation-owned data types. No kernel, no runtime,
    no storage, no EventBus, no AI, no evolution execution, no orchestration
    execution, no advisory runtime, no approval, no execution.
  * Deterministic: identical inputs produce identical output; no wall-clock,
    no randomness, no counters.
  * Fail-closed confirmation: ambiguous, unrelated, empty, or stale/missing
    context never counts as confirmation. A bounded explicit affirmative is
    required to confirm; a bounded explicit negative is required to deny;
    anything else is AMBIGUOUS (re-ask).
  * The dialogue interprets confirmation itself; it does not invoke any
    development path. P7.4 wires that hand-off.

No infrastructure dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from atlas.conversation.development_need_detector import (
    DetectedDevelopmentNeed,
)
from atlas.conversation.message import Message

# ---------------------------------------------------------------------------
# Confirmation lexicon (bounded, explicit, deterministic).
# ---------------------------------------------------------------------------

#: Whole-phrase affirmatives checked before tokenization.
_AFFIRMATIVE_PHRASES: tuple[str, ...] = (
    "go ahead",
    "yes please",
    "please do",
    "by all means",
    "sounds good",
    "lets do it",
)

#: Whole-token affirmatives (matched against whole words only).
_AFFIRMATIVE_TOKENS: frozenset[str] = frozenset({
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "absolutely",
    "definitely", "certainly", "confirm", "confirmed", "affirmative",
    "proceed", "right", "correct", "indeed", "gladly", "aye", "roger",
    "fine",
})

#: Whole-phrase negatives checked before tokenization.
_NEGATIVE_PHRASES: tuple[str, ...] = (
    "never mind",
    "no thanks",
    "no thank you",
    "not now",
    "maybe later",
    "i decline",
    "do not",
    "dont",
)

#: Whole-token negatives (matched against whole words only).
_NEGATIVE_TOKENS: frozenset[str] = frozenset({
    "no", "nope", "nah", "nay", "never", "dont", "not", "pass", "skip",
    "stop", "decline", "rejected", "reject", "deny", "denied", "avoid",
    "refuse",
})

#: Tokenizer: whole words of lowercase alphanumerics/underscores.
_TOKEN_RE = re.compile(r"[a-z0-9_]+")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ConfirmationStatus(str, Enum):
    """Deterministic outcome of interpreting a confirmation reply."""

    CONFIRMED = "confirmed"
    DENIED = "denied"
    AMBIGUOUS = "ambiguous"
    NO_PENDING_CONTEXT = "no_pending_context"


@dataclass(frozen=True, slots=True)
class ExplicitDevelopmentIntent:
    """A user-CONFIRMED development intent hand-off.

    This is NOT a :class:`DevelopmentNeed` (no code content, no approval
    lifecycle) and NOT a proposal. It is a small immutable record describing
    what the user explicitly confirmed Atlas should improve, plus the
    provenance needed to route it. P7.4 translates this into a governed
    development request through the existing kernel development seam.
    """

    title: str
    rationale: str
    capability: str = ""
    target_components: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    signal_kind: str = ""
    source: str = "development_need_dialogue"
    session_id: str = ""
    principal_id: str = ""
    authority: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "rationale": self.rationale,
            "capability": self.capability,
            "target_components": list(self.target_components),
            "evidence": list(self.evidence),
            "signal_kind": self.signal_kind,
            "source": self.source,
            "session_id": self.session_id,
            "principal_id": self.principal_id,
            "authority": self.authority,
        }


# ---------------------------------------------------------------------------
# Dialogue
# ---------------------------------------------------------------------------


class DevelopmentNeedDialogue:
    """Deterministic explanation + confirmation dialogue for detected needs.

    Stateless and safe to reuse. Every method is pure: no I/O, no model
    calls, no approval, no execution.
    """

    def explain(self, need: DetectedDevelopmentNeed) -> Message:
        """Build a bounded explanation of the detected opportunity that ends
        with an explicit yes/no confirmation request.

        The returned message is tagged with metadata so the awaiting-
        confirmation context can be recognized later (and so unrelated
        messages are never misread as confirmation).
        """
        content = self._explanation_text(need)
        return Message(
            role="assistant",
            content=content,
            metadata={
                "development_need_dialogue": {
                    "status": "awaiting_confirmation",
                    "signal_kind": need.signal_kind,
                    "capability": need.capability,
                }
            },
        )

    def interpret_confirmation(
        self,
        reply: str,
        pending_need: DetectedDevelopmentNeed | None = None,
    ) -> ConfirmationStatus:
        """Deterministically interpret a user reply to a confirmation prompt.

        Fail-closed rules:
          * no pending confirmation context -> NO_PENDING_CONTEXT
          * empty/whitespace reply -> AMBIGUOUS
          * explicit affirmative only -> CONFIRMED
          * explicit negative only -> DENIED
          * mixed, weak, or unrelated text -> AMBIGUOUS
        """
        if pending_need is None:
            return ConfirmationStatus.NO_PENDING_CONTEXT

        normalized = reply.strip().lower()
        if not normalized:
            return ConfirmationStatus.AMBIGUOUS

        has_aff = self._matches_affirmative(normalized)
        has_neg = self._matches_negative(normalized)

        if has_aff and not has_neg:
            return ConfirmationStatus.CONFIRMED
        if has_neg and not has_aff:
            return ConfirmationStatus.DENIED
        return ConfirmationStatus.AMBIGUOUS

    def denied_response(self) -> Message:
        """Bounded acknowledgment that the user declined the opportunity."""
        return Message(
            role="assistant",
            content=(
                "Understood. I won't propose an improvement for this. "
                "Let me know if you'd like to revisit it later."
            ),
            metadata={"development_need_dialogue": {"status": "denied"}},
        )

    def clarification_response(self) -> Message:
        """Bounded re-ask when the reply was ambiguous or unrelated."""
        return Message(
            role="assistant",
            content=(
                "To avoid doing anything unexpected, I'll need a clear "
                "confirmation. Would you like me to propose a governed "
                "improvement for this? Please answer yes or no."
            ),
            metadata={"development_need_dialogue": {"status": "re_asking"}},
        )

    def confirmed_response(self, need: DetectedDevelopmentNeed) -> Message:
        """Brief acknowledgment that the confirmed intent is being handed off
        toward the governed development path (actual routing is P7.4)."""
        capability = need.capability or "this area"
        return Message(
            role="assistant",
            content=(
                f"Thank you. I'll prepare a governed development request for "
                f"improving {capability} and route it through the standard "
                f"approval process."
            ),
            metadata={
                "development_need_dialogue": {"status": "confirmed"},
                "signal_kind": need.signal_kind,
            },
        )

    def build_intent(self, need: DetectedDevelopmentNeed) -> ExplicitDevelopmentIntent:
        """Build the explicit development intent hand-off for a CONFIRMED
        detected need. Pure; performs no routing."""
        title, rationale = self._intent_title_and_rationale(need)
        return ExplicitDevelopmentIntent(
            title=title,
            rationale=rationale,
            capability=need.capability,
            target_components=(need.capability,) if need.capability else (),
            evidence=need.evidence,
            signal_kind=need.signal_kind,
            session_id=need.session_id,
            principal_id=need.principal_id,
            authority=need.authority,
        )

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _explanation_text(self, need: DetectedDevelopmentNeed) -> str:
        capability = need.capability.strip() if need.capability else ""
        if need.signal_kind == "capability_gap" and capability:
            observed = (
                f"I noticed that the requested capability '{capability}' "
                "could not be resolved to an available Atlas capability."
            )
            suggestion = (
                f"This may indicate that Atlas would benefit from adding "
                f"support for '{capability}'."
            )
        elif need.signal_kind == "unresolved_action":
            observed = (
                "I noticed that this action could not be resolved to an "
                "available capability."
            )
            suggestion = "This suggests a possible improvement opportunity."
        elif need.signal_kind == "repeated_clarification":
            observed = (
                "I've had to ask for clarification multiple times while "
                "trying to handle this."
            )
            suggestion = (
                "This suggests the current capabilities may not fully "
                "support this task."
            )
        elif need.signal_kind == "advisory_opportunity":
            reason = need.reason or "a potential improvement opportunity"
            observed = (
                "Based on an advisory observation, I noticed "
                f"{reason}."
            )
            suggestion = ""
        else:
            reason = need.reason or "a potential improvement opportunity"
            observed = f"I noticed {reason}."
            suggestion = ""

        parts = [observed]
        if need.evidence:
            parts.append("Evidence: " + "; ".join(need.evidence) + ".")
        if suggestion:
            parts.append(suggestion)
        parts.append(
            "Would you like me to propose a governed development request for "
            "this improvement? Please answer yes or no."
        )
        return " ".join(parts)

    def _intent_title_and_rationale(
        self, need: DetectedDevelopmentNeed
    ) -> tuple[str, str]:
        capability = need.capability.strip() if need.capability else ""
        if capability:
            title = f"Add or improve capability: {capability}"
        else:
            title = "Improve capability: " + (need.reason or "detected opportunity")
        rationale = need.reason or "User-confirmed improvement opportunity."
        if need.evidence:
            rationale = f"{rationale} Evidence: {'; '.join(need.evidence)}."
        return title, rationale

    # ------------------------------------------------------------------
    # Matching (deterministic, whole-word / whole-phrase only)
    # ------------------------------------------------------------------

    def _matches_affirmative(self, normalized: str) -> bool:
        if any(phrase in normalized for phrase in _AFFIRMATIVE_PHRASES):
            return True
        tokens = set(_TOKEN_RE.findall(normalized))
        return bool(tokens & _AFFIRMATIVE_TOKENS)

    def _matches_negative(self, normalized: str) -> bool:
        if any(phrase in normalized for phrase in _NEGATIVE_PHRASES):
            return True
        tokens = set(_TOKEN_RE.findall(normalized))
        return bool(tokens & _NEGATIVE_TOKENS)
