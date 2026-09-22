"""Atlas Conversation — L3 minimal structured utterance meaning.

A small, deterministic, model-independent interpretation of the CURRENT
utterance: its illocution (question / request / statement), the leading
requested operation, and a bounded target expression.

This is L3 only — the structured interpretation of one utterance. It is a
value object, deliberately minimal: everything else already has an owner.

  * objective / intent          -> ``TaskSpec.intent`` (unchanged)
  * uncertainty / ambiguity     -> ``AmbiguityReport`` (unchanged)
  * entities and reference      -> ``TaskSpec.context`` (unchanged; L4)
  * referent resolution         -> ``ConversationReferenceResolver`` (L4)
  * multi-turn antecedents      -> ``ConversationState`` (L5)
  * routing                     -> ``TaskType`` (unchanged, authoritative)

Design contract (L3):
  * Pure: standard library only. No kernel, no storage, no registry, no AI,
    no network, no embeddings, no external model, no provider seam.
  * Deterministic: no clock, no randomness, no I/O; identical input yields
    identical output.
  * Bounded: ``target`` is hard-capped and control-free.
  * Advisory: it never routes, approves, executes, or promotes anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

#: Hard cap on the retained target expression.
MAX_TARGET_CHARS: int = 200

#: ``TaskSpec.context`` key under which the serialized meaning travels.
UTTERANCE_MEANING_KEY: str = "utterance_meaning"


class Illocution(str, Enum):
    """What the user is DOING with this utterance (not what words it has)."""

    QUESTION = "question"
    REQUEST = "request"
    STATEMENT = "statement"


class Operation(str, Enum):
    """The leading requested operation, when the utterance names one."""

    RESEARCH = "research"
    INVESTIGATE = "investigate"
    DEVELOP = "develop"
    ACT = "act"
    EXPLAIN = "explain"


@dataclass(frozen=True, slots=True)
class UtteranceMeaning:
    """Immutable L3 interpretation of one utterance.

    ``operation`` and ``target`` are optional: many utterances name no
    operation (questions, statements) or carry no separable target.
    """

    illocution: Illocution = Illocution.STATEMENT
    operation: Operation | None = None
    target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Deterministic, JSON-safe serialization (for ``TaskSpec.context``)."""
        return {
            "illocution": self.illocution.value,
            "operation": (
                self.operation.value if self.operation is not None else None
            ),
            "target": self.target,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "UtteranceMeaning | None":
        """Rebuild from a serialized dict, or ``None`` when malformed.

        Fail closed: unknown/absent values fall back to the bounded domain
        defaults rather than raising, so a malformed payload can never inject
        an out-of-domain meaning.
        """
        if not isinstance(data, dict):
            return None
        illocution = data.get("illocution")
        try:
            illocution_value = (
                illocution
                if isinstance(illocution, Illocution)
                else Illocution(str(illocution))
            )
        except ValueError:
            return None
        operation = data.get("operation")
        operation_value: Operation | None = None
        if operation is not None:
            if isinstance(operation, Operation):
                operation_value = operation
            else:
                try:
                    operation_value = Operation(str(operation))
                except ValueError:
                    operation_value = None
        target = data.get("target")
        return cls(
            illocution=illocution_value,
            operation=operation_value,
            target=(
                target[:MAX_TARGET_CHARS]
                if isinstance(target, str) and target.strip()
                else None
            ),
        )
