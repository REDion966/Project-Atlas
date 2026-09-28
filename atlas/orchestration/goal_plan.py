"""Atlas Orchestration — bounded goal-plan composition (Step 2).

Turns a compound conversational goal into a SMALL, explicit, ordered list of
EXISTING-capability steps, reusing the shared :func:`SemanticFrame.decompose`
decomposition. There is NO new parser and NO new planning engine: this is a
thin, deterministic, explicit mapping from already-computed sub-requests to
typed :class:`ExecutionStep` objects.

Supported shapes (the two verified Step 2 slices):

  * investigation clause + explanation clause
        -> INVESTIGATION -> ANALYSIS                (investigation synthesis)
  * research/knowledge clause + explanation clause
        -> RESEARCH -> RESEARCH_ANALYSIS             (validated-knowledge
                                                     conclusion)
  * investigation clause + GAP clause
        -> INVESTIGATION -> EVIDENCE_GAP_ANALYSIS    (concrete evidence gaps
                                                     over the same evidence)

Determinism / safety contract:
  * The plan is derived ONLY from existing bounded semantics — never from a
    model and never from arbitrary user-supplied step names.
  * A governance-sensitive clause is never planned (it keeps its existing OWNER
    approval route).
  * The mapping is CLOSED: only the existing read-only capabilities above are
    emitted. Anything else is left to its existing conversational route (this
    function returns ``None``).
  * Representation only: nothing is dispatched or executed here, and no
    authority is created.

Pure logic: stdlib + the existing conversation/orchestration value objects.
"""

from __future__ import annotations

from typing import Any

from atlas.conversation import semantic_frame as _frame
from atlas.orchestration.execution_models import (
    ExecutionRequest,
    ExecutionState,
    ExecutionStep,
    StepExecutionResult,
)
from atlas.orchestration.models import NodeKind

#: Bounds (a malformed/oversized request can never produce an unbounded plan).
_MAX_STEPS: int = 4
_MAX_TARGET_CHARS: int = 240

#: A read-only repository investigation clause.
_INVESTIGATION_OPS: frozenset[str] = frozenset(
    {"investigate", "diagnose", "inspect", "examine", "trace", "analyze", "analyse"}
)

#: A research/knowledge clause that gathers evidence.
_RESEARCH_OPS: frozenset[str] = frozenset(
    {"research", "acquire", "find", "look", "search", "study"}
)

#: A clause that asks for an explanation/next step over the prior evidence.
_ANALYSIS_OPS: frozenset[str] = frozenset(
    {"explain", "summarize", "summarise", "recommend", "describe", "compare", "relate"}
)

#: Step 2 (gap slice) — the bounded vocabulary that marks an explanation clause
#: as a request for GAPS over the carried investigation evidence, rather than a
#: general explanation. Mirrors the vocabulary the existing conversational
#: gap route already recognizes. A clause outside this set keeps the ANALYSIS
#: route byte-for-byte unchanged.
_GAP_CUES: frozenset[str] = frozenset(
    {
        "gap",
        "gaps",
        "missing",
        "insufficient",
        "limitation",
        "limitations",
        "weakness",
        "weaknesses",
        "coverage",
        "untested",
        "uncovered",
    }
)


#: Leading directive/filler tokens dropped from a RESEARCH clause so the
#: acquisition question is the researched OBJECTIVE (the existing D3 validated
#: retrieval matches on the subject, not on the request verb).
_QUESTION_STRIP: frozenset[str] = frozenset(
    {
        "research", "acquire", "find", "look", "search", "study",
        "out", "up", "about", "into", "the", "a", "an", "and", "then",
    }
)


def _bounded(value: Any, limit: int = _MAX_TARGET_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _is_gap_clause(subject: str) -> bool:
    """True when an explanation clause asks for GAPS (bounded vocabulary only)."""
    tokens = {
        token.strip(".,;:!?()[]\"'")
        for token in (subject or "").lower().split()
    }
    return bool(tokens & _GAP_CUES)


def _question_from(subject: str) -> str:
    """The bounded researched OBJECTIVE of a research clause (deterministic).

    Drops at most three leading directive/filler tokens (``research``, ``find``,
    ``out``, ``about``, articles, …) so the acquisition question is the subject
    itself. Identical input yields identical output; a fully-stripped clause
    falls back to the original subject.
    """
    tokens = (subject or "").split()
    index = 0
    while index < len(tokens) and index < 3 and tokens[index].lower() in _QUESTION_STRIP:
        index += 1
    stripped = " ".join(tokens[index:]).strip()
    return stripped or subject


def build_goal_plan(text: Any) -> tuple[ExecutionStep, ...] | None:
    """Build the bounded ordered steps for a two-stage goal, or ``None``.

    Returns a plan ONLY when the turn decomposes into an evidence-gathering
    clause followed by an explanation clause — one of the two verified Step 2
    slices. Every other shape returns ``None`` so existing routing is
    byte-for-byte unchanged.
    """
    if not isinstance(text, str) or not text.strip():
        return None

    subrequests = _frame.decompose(text)
    if len(subrequests) < 2:
        return None

    first: ExecutionStep | None = None
    first_kind: str = ""
    second: ExecutionStep | None = None

    for sub in subrequests:
        if getattr(sub, "governance_sensitive", False):
            # A governed clause is never planned; it keeps its OWNER route.
            continue
        operation = _bounded(getattr(sub, "operation", ""), 32).lower()
        domain = _bounded(getattr(sub, "domain", ""), 32).lower()
        subject = _bounded(getattr(sub, "subject", ""))

        if first is None:
            if operation in _INVESTIGATION_OPS or domain == "investigation":
                target = subject or _bounded(text)
                if not target:
                    continue
                first = ExecutionStep(
                    step_id="step-0000",
                    kind=NodeKind.INVESTIGATION,
                    target=target,
                    inputs={"objective": subject or target},
                    description=f"Investigate: {subject or target}",
                )
                first_kind = "investigation"
                continue
            if operation in _RESEARCH_OPS or domain == "knowledge":
                question = _question_from(subject) or _bounded(text)
                if not question:
                    continue
                first = ExecutionStep(
                    step_id="step-0000",
                    kind=NodeKind.KNOWLEDGE,
                    target="retrieve",
                    inputs={"question": question},
                    description=f"Knowledge: {question}",
                )
                first_kind = "knowledge"
                continue
            continue

        # The second stage must be an EXPLANATION clause. Keyed on the operation
        # only (not the domain): a second evidence-gathering clause keeps its
        # existing route.
        if second is None and operation in _ANALYSIS_OPS:
            if first_kind == "investigation":
                if _is_gap_clause(subject):
                    second = ExecutionStep(
                        step_id="step-0001",
                        kind=NodeKind.EVIDENCE_GAP_ANALYSIS,
                        target="analyze_gaps",
                        inputs={},
                        depends_on=(first.step_id,),
                        carry_from=(first.step_id,),
                        description=(
                            "Identify the concrete evidence gaps from the "
                            "investigation evidence"
                        ),
                    )
                else:
                    second = ExecutionStep(
                        step_id="step-0001",
                        kind=NodeKind.ANALYSIS,
                        target="synthesize",
                        inputs={},
                        depends_on=(first.step_id,),
                        carry_from=(first.step_id,),
                        description="Explain next steps from the investigation evidence",
                    )
            else:  # knowledge
                second = ExecutionStep(
                    step_id="step-0001",
                    kind=NodeKind.RESEARCH_ANALYSIS,
                    target="conclude",
                    inputs={},
                    depends_on=(first.step_id,),
                    carry_from=(first.step_id,),
                    description="Explain what the validated research evidence supports",
                )
            break

    if first is None or second is None:
        return None
    return (first, second)[:_MAX_STEPS]


def resume_execution_request(
    plan_state: Any,
    session_context: Any = None,
) -> ExecutionRequest | None:
    """A bounded request that CONTINUES a retained unfinished plan, or ``None``.

    Rebuilds only the INCOMPLETE steps from the retained bounded plan (its step
    id / kind / target / bounded inputs / dependency + carry references) and
    seeds the already-COMPLETED steps, so the resumed downstream step reuses the
    SAME bounded result through ``carry_from`` and completed work is never
    repeated. Fail-closed: an absent/inconsistent plan, an unknown step kind, or
    a plan with no incomplete step returns ``None`` (the caller then keeps its
    existing route and does not guess). Representation only; no authority.
    """
    if not isinstance(plan_state, dict):
        return None
    raw_steps = plan_state.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        return None

    remaining: list[ExecutionStep] = []
    completed: list[StepExecutionResult] = []
    for entry in raw_steps[:_MAX_STEPS]:
        if not isinstance(entry, dict):
            return None
        step_id = str(entry.get("step_id") or "")
        target = str(entry.get("target") or "")
        try:
            kind = NodeKind(str(entry.get("kind") or ""))
        except ValueError:
            return None
        if not step_id or not target:
            return None
        if str(entry.get("state") or "") == "completed":
            output = entry.get("output")
            completed.append(
                StepExecutionResult(
                    step_id=step_id,
                    kind=kind,
                    target=target,
                    state=ExecutionState.COMPLETED,
                    output=dict(output) if isinstance(output, dict) else {},
                )
            )
            continue
        inputs = entry.get("inputs")
        depends_on = entry.get("depends_on")
        carry_from = entry.get("carry_from")
        remaining.append(
            ExecutionStep(
                step_id=step_id,
                kind=kind,
                target=target,
                inputs=dict(inputs) if isinstance(inputs, dict) else {},
                depends_on=tuple(d for d in (depends_on or ()) if isinstance(d, str)),
                carry_from=tuple(c for c in (carry_from or ()) if isinstance(c, str)),
            )
        )
    if not remaining:
        return None
    return ExecutionRequest(
        steps=tuple(remaining),
        completed_steps=tuple(completed),
        session_context=session_context,
        max_steps=_MAX_STEPS,
    )
