"""Atlas Conversation — Typed Turn-Meaning boundary contract (L1).

An immutable, role-typed, JSON-safe projection of one conversation turn at the
existing conversation -> cognition boundary. It carries only *turn meaning*
already produced by the deterministic conversation layer, plus a bounded
source-text provenance anchor:

  * ``intent``      — bounded operational-intent snapshot of the existing
                      ``TaskSpec`` (routing meaning, not a second TaskSpec).
  * ``uncertainty`` — snapshot of the existing ``AmbiguityReport``.
  * ``reference``   — snapshot of the existing ``resolved_reference`` evidence.
  * ``source_text`` — bounded user input, used only as a provenance anchor.
  * ``provenance``  — deterministic source/turn information already present in
                      the architecture (no new identity system).

Design contract (L1):
  * Value object only: it owns immutable *snapshots*, never mutable runtime
    objects (no ``CognitionState`` / ``ConversationState`` /
    ``ConversationContext`` / ``UnderstandingGraph`` / concept objects /
    governance / provider objects).
  * Not a second TaskSpec — it is a bounded projection of existing fields.
  * Deterministic and model-independent: no clock, no randomness, no I/O.
  * Behaviour-neutral: constructing and passing it changes no routing, no
    governed handler, no prompt, and no provider behaviour.
  * Exactly one consumer exists: :func:`accept_turn_meaning`, the fail-closed
    acceptance check at the cognition boundary. The contract's *semantic
    content* is intentionally NOT consumed in L1; content consumption belongs
    to a later stage.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

#: Bound for the source-text provenance anchor.
MAX_SOURCE_TEXT_CHARS: int = 500

#: Fields projected from the existing ``TaskSpec`` as operational intent.
#: ``ambiguity`` and ``context`` are deliberately excluded here because they
#: are carried by their own role-separated blocks (uncertainty / reference).
_INTENT_FIELDS: tuple[str, ...] = (
    "task_id",
    "task_type",
    "intent",
    "goal",
    "constraints",
    "priorities",
    "success_criteria",
    "confidence",
    "needs_clarification",
    "source",
    "verified",
    "input_hash",
)


@dataclass(frozen=True, slots=True)
class TurnMeaning:
    """Immutable, role-typed meaning of one turn crossing into cognition."""

    intent: dict[str, Any] = field(default_factory=dict)
    uncertainty: dict[str, Any] = field(default_factory=dict)
    reference: dict[str, Any] = field(default_factory=dict)
    source_text: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Deterministic, JSON-safe serialization (returns fresh copies)."""
        return {
            "intent": copy.deepcopy(self.intent),
            "uncertainty": copy.deepcopy(self.uncertainty),
            "reference": copy.deepcopy(self.reference),
            "source_text": self.source_text,
            "provenance": copy.deepcopy(self.provenance),
        }


def _bounded_text(value: Any, limit: int = MAX_SOURCE_TEXT_CHARS) -> str:
    """Return bounded source text for the provenance anchor."""
    text = value if isinstance(value, str) else ""
    return text[:limit]


def build_turn_meaning(spec: Any, source_text: str) -> TurnMeaning:
    """Build the contract from an existing ``TaskSpec`` and the turn's input.

    The produced object owns deep copies of every nested value, so later
    mutation of the source ``TaskSpec`` (or of the returned ``to_dict()``
    payload) cannot alter it.
    """
    spec_dict = spec.to_dict() if hasattr(spec, "to_dict") else {}
    if not isinstance(spec_dict, dict):
        spec_dict = {}

    intent: dict[str, Any] = {}
    for name in _INTENT_FIELDS:
        if name in spec_dict:
            intent[name] = copy.deepcopy(spec_dict[name])

    uncertainty: dict[str, Any] = {}
    ambiguity = getattr(spec, "ambiguity", None)
    if ambiguity is not None and hasattr(ambiguity, "to_dict"):
        value = ambiguity.to_dict()
        if isinstance(value, dict):
            uncertainty = copy.deepcopy(value)

    reference: dict[str, Any] = {}
    context = getattr(spec, "context", None)
    if isinstance(context, dict):
        resolved = context.get("resolved_reference")
        if isinstance(resolved, dict):
            reference = copy.deepcopy(resolved)

    provenance: dict[str, Any] = {
        "source": "deterministic",
        "task_id": str(getattr(spec, "task_id", "") or ""),
        "input_hash": str(getattr(spec, "input_hash", "") or ""),
    }

    return TurnMeaning(
        intent=intent,
        uncertainty=uncertainty,
        reference=reference,
        source_text=_bounded_text(source_text),
        provenance=provenance,
    )


def accept_turn_meaning(value: Any) -> TurnMeaning | None:
    """Fail-closed acceptance check for the cognition boundary (L1 consumer).

    Returns the contract unchanged when it has the expected shape/type, and
    ``None`` otherwise (malformed input is silently dropped, so behaviour is
    unchanged). It intentionally inspects only the contract's *shape* — never
    its semantic content — and it never executes, routes, or mutates anything.
    """
    if value is None:
        return None
    if not isinstance(value, TurnMeaning):
        return None
    if not isinstance(value.source_text, str):
        return None
    for block in ("intent", "uncertainty", "reference", "provenance"):
        if not isinstance(getattr(value, block, None), dict):
            return None
    return value
