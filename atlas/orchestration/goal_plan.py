"""Atlas Orchestration — bounded goal-plan composition (Step 2, first slice).

Turns a compound conversational goal into a SMALL, explicit, ordered list of
EXISTING-capability steps, reusing the shared :func:`SemanticFrame.decompose`
decomposition. There is NO new parser and NO new planning engine: this is a
thin, deterministic, explicit mapping from already-computed sub-requests to
typed :class:`ExecutionStep` objects.

Determinism / safety contract:
  * The plan is derived ONLY from existing bounded semantics — never from a
    model and never from arbitrary user-supplied step names.
  * A governance-sensitive clause is never planned (it keeps its existing OWNER
    approval route).
  * The mapping is closed: only the two EXISTING read-only capabilities of the
    first vertical slice are emitted (repository investigation, then
    deterministic synthesis over its result). Anything else is left to its
    existing conversational route (this function returns ``None``).
  * Representation only: nothing is dispatched or executed here, and no
    authority is created.

Pure logic: stdlib + the existing conversation/orchestration value objects.
"""

from __future__ import annotations

from typing import Any

from atlas.conversation import semantic_frame as _frame
from atlas.orchestration.execution_models import ExecutionStep
from atlas.orchestration.models import NodeKind

#: Bounds (a malformed/oversized request can never produce an unbounded plan).
_MAX_STEPS: int = 4
_MAX_TARGET_CHARS: int = 240

#: A read-only repository investigation clause.
_INVESTIGATION_OPS: frozenset[str] = frozenset(
    {"investigate", "diagnose", "inspect", "examine", "trace", "analyze", "analyse"}
)

#: A clause that asks for an explanation/next step over the prior evidence.
_ANALYSIS_OPS: frozenset[str] = frozenset(
    {"explain", "summarize", "summarise", "recommend", "compare", "describe"}
)


def _bounded(value: Any, limit: int = _MAX_TARGET_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def build_goal_plan(text: Any) -> tuple[ExecutionStep, ...] | None:
    """Build the bounded ordered steps for a two-stage goal, or ``None``.

    Returns a plan ONLY when the turn decomposes into at least two sub-requests
    that include an investigation clause followed by an explanation clause —
    the first vertical slice. Every other shape returns ``None`` so existing
    routing is byte-for-byte unchanged.
    """
    if not isinstance(text, str) or not text.strip():
        return None

    subrequests = _frame.decompose(text)
    if len(subrequests) < 2:
        return None

    investigation: ExecutionStep | None = None
    analysis: ExecutionStep | None = None

    for sub in subrequests:
        if getattr(sub, "governance_sensitive", False):
            # A governed clause is never planned; it keeps its OWNER route.
            continue
        operation = _bounded(getattr(sub, "operation", ""), 32).lower()
        subject = _bounded(getattr(sub, "subject", ""))
        domain = _bounded(getattr(sub, "domain", ""), 32).lower()

        if investigation is None and (
            operation in _INVESTIGATION_OPS or domain == "investigation"
        ):
            target = subject or _bounded(text)
            if not target:
                continue
            investigation = ExecutionStep(
                step_id="step-0000",
                kind=NodeKind.INVESTIGATION,
                target=target,
                inputs={"objective": subject or target},
                description=f"Investigate: {subject or target}",
            )
            continue

        if (
            investigation is not None
            and analysis is None
            and (operation in _ANALYSIS_OPS or domain == "knowledge")
        ):
            analysis = ExecutionStep(
                step_id="step-0001",
                kind=NodeKind.ANALYSIS,
                target="synthesize",
                inputs={},
                depends_on=(investigation.step_id,),
                carry_from=(investigation.step_id,),
                description="Explain next steps from the investigation evidence",
            )
            break

    if investigation is None or analysis is None:
        return None
    return (investigation, analysis)[:_MAX_STEPS]
