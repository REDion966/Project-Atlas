"""Atlas Toolchain — Conditional Step Predicate (Phase 22, Batch 1).

A small, deterministic predicate mechanism over prior step ``output``
dictionaries. There is no general expression language: the only supported
condition spec is an equality check against a prior step's output value.

Condition spec (carried in ``ToolStep.parameters["when"]`` or legacy
``"step_when"``):

    - ``{"key": <str>, "equals": <value>}`` — True when the prior step's
      output dict contains ``key`` and ``output[key] == <value>``.
    - ``{"key": <str>, "truthy": true}`` — True when
      ``bool(output.get(key))`` is ``True``.

Unknown condition kinds fail closed (return ``False``). No ``eval()``, no
Python expressions, no user-supplied callables. Pure logic; no storage, no
kernel, no gateway.
"""

from __future__ import annotations

from typing import Any

#: Reserved parameter keys interpreted by the conditional executor.
WHEN_PARAMETER_KEY: str = "when"
#: Legacy alias preserved for compatibility with existing chain builders.
LEGACY_WHEN_PARAMETER_KEY: str = "step_when"


def extract_condition(step_parameters: dict[str, Any]) -> dict[str, Any] | None:
    """Return the condition spec from a step's parameters, or None.

    ``None`` means the step is unconditional (always eligible when its
    declared dependencies are satisfied).
    """
    if not isinstance(step_parameters, dict):
        return None
    for key in (WHEN_PARAMETER_KEY, LEGACY_WHEN_PARAMETER_KEY):
        value = step_parameters.get(key)
        if isinstance(value, dict) and value:
            return value
    return None


def is_supported_condition(condition: dict[str, Any] | None) -> bool:
    """Return True when a condition spec is one of the supported forms.

    Unsupported/malformed specs are detected before evaluation so the
    executor can record a distinct ``unsupported_condition`` skip reason
    and never invoke the tool.
    """
    if not condition:
        return True
    if not isinstance(condition, dict):
        return False
    key = condition.get("key")
    if not isinstance(key, str) or not key:
        return False
    return "equals" in condition or condition.get("truthy") is True


def evaluate_condition(
    condition: dict[str, Any] | None,
    prior_output: dict[str, Any],
) -> bool:
    """Evaluate a condition against a prior step's output dict.

    Deterministic and fail-closed: an unsupported or malformed condition
    evaluates to ``False`` (the dependent step is skipped), never raises.
    """
    if not condition:
        return True
    if not isinstance(prior_output, dict):
        return False

    key = condition.get("key")
    if not isinstance(key, str) or not key:
        return False

    if "equals" in condition:
        return prior_output.get(key) == condition["equals"]
    if condition.get("truthy") is True:
        return bool(prior_output.get(key))
    return False
