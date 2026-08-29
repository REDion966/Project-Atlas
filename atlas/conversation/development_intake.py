"""Atlas Conversation — Development Intake (B3).

A pure, deterministic adapter that converts a B2 :class:`TaskSpec` into a
bounded :class:`DevelopmentNeed` for the EXISTING governed development-cycle
preparation flow. This is the intake bridge between conversational
understanding and the F9 governed proposal path.

Design contract (B3):
  * Pure: imports only the data types it maps between. No ``atlas.ai``, no
    kernel, no storage, no EventBus, no execution, no governance calls, no
    code generation.
  * Deterministic-first: identical ``TaskSpec`` inputs produce identical
    ``DevelopmentNeed`` outputs.
  * Bounded: every mapped field is hard-capped.
  * DEVELOPMENT_REQUEST only: every other task type is refused (``None``).
  * Under-specified requests (``needs_clarification``) are gated (``None``).
  * NEVER fabricates ``metadata["code_changes"]`` or ``metadata["test_files"]``;
    the deterministic change supplier therefore fails closed when no concrete
    change content was supplied.

No infrastructure dependencies.
"""

from __future__ import annotations

from typing import Any

from atlas.conversation.task_intake import TaskSpec, TaskType
from atlas.evolution.development_cycle import DevelopmentNeed

# ---------------------------------------------------------------------------
# Bounds (aligned with DevelopmentCyclePolicy where applicable)
# ---------------------------------------------------------------------------

_MAX_TITLE_CHARS: int = 200
_MAX_SUMMARY_CHARS: int = 2_000
_MAX_TEXT_CHARS: int = 4_000
_MAX_ITEMS: int = 8
_MAX_ITEM_CHARS: int = 200
_MAX_CONCEPTS: int = 24

#: Fallback titles are kept short and never describe implementation details.
_DEFAULT_TITLE: str = "Conversational development request"

#: Advisory context fields we forward; all others are dropped. This list is
#: intentionally allow-listed so a TaskSpec can never smuggle extra state.
_CONTEXT_KEYS: tuple[str, ...] = (
    "history_length",
    "concepts",
    "token_count",
    "length",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bounded_text(value: Any, limit: int) -> str:
    """Return a bounded, control-free string, or ``""`` for non-strings."""
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _bounded_items(
    values: Any,
    max_items: int = _MAX_ITEMS,
    max_item_chars: int = _MAX_ITEM_CHARS,
) -> tuple[str, ...]:
    """Deduplicate and bound an iterable of strings (order preserved)."""
    if not isinstance(values, (list, tuple)):
        return ()
    seen: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()[:max_item_chars]
        if item and item not in seen:
            seen.append(item)
        if len(seen) >= max_items:
            break
    return tuple(seen)


# ---------------------------------------------------------------------------
# Classification / clarification gate
# ---------------------------------------------------------------------------


def is_development_request(spec: TaskSpec | None) -> bool:
    """True when ``spec`` is a DEVELOPMENT_REQUEST."""
    return (
        spec is not None
        and isinstance(spec, TaskSpec)
        and spec.task_type == TaskType.DEVELOPMENT_REQUEST
    )


def needs_clarification(spec: TaskSpec | None) -> bool:
    """True when the spec is under-specified and must be clarified first."""
    return is_development_request(spec) and bool(spec.needs_clarification)


def clarification_questions(spec: TaskSpec | None) -> tuple[str, ...]:
    """Return bounded clarification questions for an under-specified request."""
    if spec is None or not isinstance(spec, TaskSpec):
        return ()
    questions = getattr(spec.ambiguity, "clarification_questions", ()) or ()
    return _bounded_items(tuple(questions), _MAX_ITEMS)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


def task_spec_to_development_need(spec: TaskSpec | None) -> DevelopmentNeed | None:
    """Map a B2 ``TaskSpec`` into a bounded ``DevelopmentNeed``.

    Returns ``None`` (refusal) when the spec is not a DEVELOPMENT_REQUEST,
    is under-specified (``needs_clarification``), or is malformed. The result
    never carries ``code_changes`` / ``test_files``, so the existing
    deterministic change supplier fails closed when no concrete change content
    exists elsewhere.
    """
    if spec is None or not isinstance(spec, TaskSpec):
        return None
    if spec.task_type != TaskType.DEVELOPMENT_REQUEST:
        return None
    if spec.needs_clarification:
        return None

    title = _bounded_text(spec.intent, _MAX_TITLE_CHARS) or _DEFAULT_TITLE
    summary = _bounded_text(spec.goal, _MAX_SUMMARY_CHARS) or title

    constraints = _bounded_items(spec.constraints, _MAX_ITEMS)
    priorities = _bounded_items(spec.priorities, _MAX_ITEMS)
    success_criteria = _bounded_items(spec.success_criteria, _MAX_ITEMS)

    rationale = " ".join(constraints)[:_MAX_TEXT_CHARS]
    expected_benefit = " ".join(success_criteria)[:_MAX_TEXT_CHARS]

    metadata: dict[str, Any] = {
        "source": "conversational_development_intake",
        "intake_source": _bounded_text(spec.source, 64),
        "confidence": _bounded_confidence(spec.confidence),
        "task_id": _bounded_text(spec.task_id, 128),
        "input_hash": _bounded_text(spec.input_hash, 64),
    }
    if constraints:
        metadata["constraints"] = list(constraints)
    if priorities:
        metadata["priorities"] = list(priorities)
    if success_criteria:
        metadata["success_criteria"] = list(success_criteria)

    context = _bounded_context(spec.context)
    if context:
        metadata["context"] = context

    return DevelopmentNeed(
        title=title,
        summary=summary,
        rationale=rationale,
        expected_benefit=expected_benefit,
        candidate_id=_bounded_text(spec.task_id, 128),
        metadata=metadata,
    )


def _bounded_confidence(value: Any) -> float:
    """Clamp a confidence value into [0.0, 1.0]; malformed input -> 0.0."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:  # NaN guard
        return 0.0
    return round(max(0.0, min(1.0, number)), 4)


def _bounded_context(context: Any) -> dict[str, Any]:
    """Project an allow-listed, bounded subset of the TaskSpec context."""
    if not isinstance(context, dict):
        return {}
    out: dict[str, Any] = {}
    for key in _CONTEXT_KEYS:
        if key not in context:
            continue
        value = context[key]
        if key == "concepts":
            out[key] = list(_bounded_items(value, _MAX_CONCEPTS))
        elif key == "history_length":
            out[key] = _bounded_int(value, 0, 10_000)
        elif key == "token_count":
            out[key] = _bounded_int(value, 0, 10_000)
        elif key == "length":
            out[key] = _bounded_int(value, 0, 1_000_000)
    return out


def _bounded_int(value: Any, low: int, high: int) -> int:
    """Return an int clamped into ``[low, high]``; malformed input -> ``low``."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))
