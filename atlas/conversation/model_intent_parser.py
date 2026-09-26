"""Atlas Conversation — Model-assisted intent parser (Step 1, OPTIONAL).

A bounded, concrete implementation of the EXISTING ``IntentParser`` seam
(:class:`atlas.conversation.task_intake.IntentParser`) backed by the EXISTING
AI service. It lets an enabled local model propose a *structured reading* of a
turn (task type + intent + goal) — and only when the deterministic intake
cannot type the turn at all.

Boundaries (mirrors the existing ``ModelAssistedChangeSupplier`` contract):

* no ``atlas.ai`` import — the model is a duck-typed callable, so this module
  stays pure and the composition layer owns the provider wiring;
* OFF by default: ``model=None`` makes :meth:`parse` return ``None`` so the
  deterministic intake is authoritative;
* deterministic-first: the model is consulted only when the deterministic
  intake returns ``UNKNOWN`` — a turn the deterministic vocabulary already
  types is never re-litigated by a model;
* output is UNTRUSTED: a single strict JSON object, closed key/vocabulary sets,
  hard bounds; any failure returns ``None`` (fail-closed, never repaired);
* it may never propose a governance/decision task type (approval, execution,
  rejection, planning, recovery, verification, autonomy) — the sanitizer in
  ``task_intake`` enforces the same allowlist independently;
* it never executes, approves, promotes, mutates state, or touches the kernel,
  registries, storage, or the event bus.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from atlas.conversation.lexicon import tokens as _lemmas
from atlas.conversation.task_intake import (
    MODEL_PROPOSABLE_TASK_TYPES,
    TaskIntake,
    TaskType,
)

#: Bound on the turn text sent to the model.
MAX_PROMPT_TEXT_CHARS: int = 600
#: Bounds on the returned free-text fields (further bounded by task_intake).
MAX_INTENT_CHARS: int = 200
MAX_GOAL_CHARS: int = 300
#: Only these keys are accepted from the model; anything else rejects the whole
#: response (fail-closed, no silent repair).
_SUPPORTED_KEYS: frozenset[str] = frozenset({"task_type", "intent", "goal"})

#: The closed task-type vocabulary the model is allowed to see / propose.
_TASK_TYPES_LIST: str = ", ".join(sorted(MODEL_PROPOSABLE_TASK_TYPES))

#: Deterministic task types that mean "no specific structure was found": the
#: model may be consulted to propose a bounded reading. Any other type is
#: already understood deterministically and is never re-litigated by a model.
_UNDETERMINED_TASK_TYPES: frozenset[TaskType] = frozenset(
    {TaskType.UNKNOWN, TaskType.CONVERSATION}
)

#: Minimum content tokens before a model call is worth making (a bare "hi" or
#: "thanks" is never sent to a model just to be re-read).
_MIN_TOKENS_FOR_ASSIST: int = 3


class ModelIntentParser:
    """Optional model-assisted parsing over the existing ``IntentParser`` seam.

    Args:
        model: A duck-typed callable invoked with one prompt string. It may
            return a ``str`` containing exactly one JSON object, a ``dict``
            (already-decoded JSON), or any object exposing a ``.text`` string
            (the existing ``AIResponse`` shape). ``None`` (default) disables
            model assistance entirely.
    """

    def __init__(self, model: Callable[[str], Any] | None = None) -> None:
        self._model = model

    @property
    def enabled(self) -> bool:
        """True when a model callable is wired."""
        return self._model is not None

    def parse(self, text: str, context: dict[str, Any]) -> dict[str, Any] | None:
        """Return a bounded, validated parse dict, or ``None`` (fail-closed).

        Deterministic-first: when the deterministic intake already types the
        turn, ``None`` is returned so the model is never consulted.
        """
        if self._model is None or not isinstance(text, str) or not text.strip():
            return None
        if not self._is_undetermined(text):
            return None
        try:
            raw = self._model(self._build_prompt(text))
        except Exception:
            return None
        payload = _extract_payload(raw)
        if payload is None:
            return None
        return self._validate(payload)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _is_undetermined(text: str) -> bool:
        """True when the deterministic intake found no specific structure.

        The deterministic intake never fails to return a type; its untyped
        default is ``CONVERSATION``. The model is consulted only for that
        default (or a genuinely empty ``UNKNOWN``) and only when the turn is
        substantial enough to be worth a model call. A turn the deterministic
        vocabulary already types (question / investigation / development /
        action / ...) is never re-litigated.
        """
        try:
            spec = TaskIntake().intake(text)
        except Exception:
            return False
        if spec.task_type not in _UNDETERMINED_TASK_TYPES:
            return False
        return len(_lemmas(text)) >= _MIN_TOKENS_FOR_ASSIST

    @staticmethod
    def _build_prompt(text: str) -> str:
        """Render a bounded, closed-vocabulary interpretation prompt."""
        return (
            "You are a bounded language-understanding helper for a deterministic "
            "assistant. Read ONE user turn and return ONE JSON object, with no "
            "prose and no markdown, containing exactly these keys:\n"
            '  "task_type": one of [' + _TASK_TYPES_LIST + "]\n"
            '  "intent": a short description of what the user wants\n'
            '  "goal": the user\'s objective, restated briefly\n'
            "Do not include any other keys. Do not propose approvals, "
            "executions, permissions, or system changes. If the turn is unclear, "
            'use "unknown".\n'
            "User turn:\n" + text.strip()[:MAX_PROMPT_TEXT_CHARS]
        )

    @staticmethod
    def _validate(payload: dict[str, Any]) -> dict[str, Any] | None:
        """Structurally validate + bound a decoded model payload."""
        if not set(payload.keys()) <= _SUPPORTED_KEYS:
            return None
        fields: dict[str, Any] = {}
        task_type = payload.get("task_type")
        if isinstance(task_type, str) and task_type in MODEL_PROPOSABLE_TASK_TYPES:
            fields["task_type"] = task_type
        for key, limit in (("intent", MAX_INTENT_CHARS), ("goal", MAX_GOAL_CHARS)):
            value = payload.get(key)
            if isinstance(value, str):
                cleaned = value.strip()[:limit]
                if cleaned:
                    fields[key] = cleaned
        return fields or None


def _extract_payload(raw: Any) -> dict[str, Any] | None:
    """Normalize a model response into a decoded dict, or ``None``."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return _parse_json(raw)
    text = getattr(raw, "text", None)
    if isinstance(text, str):
        return _parse_json(text)
    return None


def _parse_json(text: str) -> dict[str, Any] | None:
    """Strictly parse exactly one JSON object; reject anything else."""
    stripped = text.strip()
    if not stripped:
        return None
    try:
        obj = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None
