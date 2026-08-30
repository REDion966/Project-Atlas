"""Atlas Orchestration — Target Resolution (P2/B2.3).

Maps a B2 :class:`TaskSpec` into bounded :class:`ExecutionStep` objects
for the B2.2 :class:`OrchestrationExecutor`. This is a pure, deterministic
INTENT→TARGET translator: only ACTION_REQUEST and INFORMATION_REQUEST specs
may produce steps. Every other task type is refused.

Returns ``None`` when the spec cannot be safely resolved into a bounded
target/operation (underspecified / ambiguous / no registered target, etc.) —
the caller is responsible for asking for clarification.

No AI. No storage. No EventBus. No handler invocation.
"""

from __future__ import annotations

from typing import Any

from atlas.conversation.task_intake import TaskSpec, TaskType
from atlas.orchestration.execution_models import ExecutionStep
from atlas.orchestration.models import NodeKind

#: Only ACTION/INFORMATION requests may be translated into executable work.
#: The existing DEVELOPMENT_REQUEST → governed development pipeline is the
#: sole route for self-development.
_ROUTABLE_TYPES: tuple[TaskType, ...] = (TaskType.ACTION_REQUEST, TaskType.INFORMATION_REQUEST)

#: Ordered preference for slot extraction; INTENT is authoritative.
#: Constraints are factored out of the goal string as bounded step params
#: so a constraint can never accidentally become an executable target.
_MAX_INPUTS_CHARS: int = 1_000


def _slot_value(spec: TaskSpec) -> str:
    """Canonical bounded subject text for a request.

    Uses the deterministic ``intent`` (the objective extracted from the raw
    text), not raw user input, so a constraint like "keep it short" cannot
    become a target name.
    """
    return (spec.intent or "").strip()[:_MAX_INPUTS_CHARS]


def _inputs_for(spec: TaskSpec) -> dict[str, Any]:
    """Bounded step-input dict derived from a spec.

    Each input is a short, deterministic string; together they allow a
    handler to distinguish requests without requiring a model.
    """
    slot = _slot_value(spec)
    inputs: dict[str, Any] = {"goal": spec.goal_string()}
    if slot:
        # ``slot`` is the minimal subject/object the request acts on.
        inputs["slot"] = slot
    # Constraints are context (bounded), not targets.
    if spec.constraints:
        inputs["constraints"] = list(spec.constraints)
    if spec.priorities:
        inputs["priorities"] = list(spec.priorities)
    if spec.success_criteria:
        inputs["success_criteria"] = list(spec.success_criteria)
    # ``source`` is a deterministic provenance hint (no raw prompt).
    inputs["source"] = spec.source
    return inputs


def task_spec_to_execution_steps(
    spec: TaskSpec | None,
    *,
    tool_targets: set[str] = frozenset(),
) -> tuple[ExecutionStep, ...] | None:
    """Translate a B2 TaskSpec into bounded :class:`ExecutionStep` tuples.

    Returns ``None`` when the spec cannot produce safe, bounded execution:

    * ``spec`` is not a ``TaskSpec`` or not ACTION/INFORMATION,
    * the spec ``needs_clarification`` (ambiguous/underspecified),
    * the intent slot is empty (no bounded target subject),
    * an ACTION_REQUEST names no registered tool (never fabricate a target).

    INFORMATION requests that are research-shaped map to a single governed
    RESEARCH step against ``InformationAcquisitionService.acquire(question=...)``.
    ACTION requests map to a single governed TOOL step only when the bounded
    intent/goal names a supplied registered tool; otherwise they are refused
    (``None`` → clarification) rather than routed to a placeholder capability.

    Args:
        spec: The parsed :class:`TaskSpec`.
        tool_targets: Registered tool names the caller is willing to match by
            keyword. Only tool names that actually appear in the lowercased
            slot/goal are emitted (never from raw text or invented).

    Returns:
        A bounded ``tuple[ExecutionStep, ...]`` of length 1, or ``None`` when
        the translation must not be executed without clarification.
    """
    if spec is None or not isinstance(spec, TaskSpec):
        return None
    if spec.task_type not in _ROUTABLE_TYPES:
        return None
    # Preserve existing clarification semantics — do not execute
    # underspecified work.
    if bool(getattr(spec, "needs_clarification", False)):
        return None

    slot = _slot_value(spec)
    # Reject empty-slot specs: an "ACTION_REQUEST" with no bounded intent is
    # not actionable. The caller should ask for clarification.
    if not slot:
        return None

    lowered_slot = slot.lower()
    lowered_goal = (spec.goal or "").lower()
    hint_blob = f"{lowered_slot} {lowered_goal}"

    # INFORMATION requests that are research-shaped route to the governed
    # research seam. The bounded step carries ONLY the supported ``question``
    # input so the executor's research dispatch never forwards unsupported
    # parameters to ``InformationAcquisitionService.acquire``.
    if spec.task_type is TaskType.INFORMATION_REQUEST:
        requires_research = any(
            word in hint_blob for word in ("research", "acquire", "find the latest", "look up", "search", "investigate")
        )
        if requires_research:
            return (
                ExecutionStep(
                    step_id="step-0000",
                    kind=NodeKind.RESEARCH,
                    target="acquire",
                    inputs={"question": slot},
                    description=spec.intent,
                ),
            )
        # Non-research information requests are not safely resolvable here;
        # refuse (clarification) rather than guess a target.
        return None

    # ACTION_REQUEST: resolve to a real registered tool only when the bounded
    # intent/goal actually names one of the supplied tool targets. Otherwise
    # refuse — there is no fabricated-success placeholder path.
    tool_hits = [
        t for t in tool_targets if t and t.lower() in hint_blob
    ]
    if not tool_hits:
        return None
    # Deterministic winner: shortest then lexicographic (not insertion order).
    winner = sorted(tool_hits, key=lambda x: (len(x), x))[0]
    return (
        ExecutionStep(
            step_id="step-0000",
            kind=NodeKind.TOOL,
            target=winner,
            inputs=_inputs_for(spec),
            description=spec.intent,
        ),
    )
