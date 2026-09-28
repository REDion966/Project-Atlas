"""Atlas Conversation — bounded multi-intent / multi-step understanding (Step 10).

A bounded, deterministic *representation* of a request that carries more than one
distinct intent or step: the ordered steps Atlas actually read, whether the
language expressed an order, which steps depend on an earlier step's RESULT, and
what each step would be routed to (an existing read-only mechanism, the
deterministic builtin surface, or nothing at all).

It exists because the baseline (real Atlas/kernel, multi-turn) demonstrated that
Step 6 (``split_intents`` + the builtin multi-intent answer) reads only *casual*
multi-intent turns, and the Step 2 goal plan only composes a fixed closed set of
two-stage slices. A genuinely unseen multi-intent/multi-step OPERATIONAL request
("Investigate A and also research B", "First investigate A, then research B",
"Investigate A, then analyze the findings, then tell me what you can do") was
therefore handed to a single operational route that acted on the WHOLE sentence
and silently dropped the other intents, and explicit sequencing/dependency was
never represented.

This module is representation only:

  * it never executes, plans autonomously, authorizes or mutates anything;
  * it derives steps ONLY from the existing bounded semantics
    (:func:`atlas.conversation.semantic_frame.interpret`) — never from a model;
  * it is CLOSED: a step maps to an existing read-only mechanism, the builtin
    surface, or nothing; a governance-sensitive clause is never an executable
    step;
  * it never invents an order that the language did not express, and it never
    invents a dependency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from atlas.conversation import semantic_frame as _frame

#: Upper bound on steps read from one request.
MAX_REQUEST_STEPS: int = 4

#: Bound applied to a retained clause / subject.
_MAX_CLAUSE_CHARS: int = 240

#: Connectors that CARRY an explicit order ("A, then B").
_ORDER_CONNECTORS: tuple[str, ...] = (
    "and then",
    "after that",
    "afterwards",
    "then",
    "next",
    "finally",
)

#: STRONG coordinators — a second reading is taken even when the following clause
#: only *states* what is wanted (the Step 6 shape).
_STRONG_CONNECTORS: tuple[str, ...] = (
    "and also",
    "as well as",
    "plus also",
    "plus",
    "also",
)

#: WEAK coordinators — a second reading is taken only when BOTH sides name a
#: bounded OPERATION, so a single multi-clause intent (one verb, two objects) is
#: never over-split.
_WEAK_CONNECTORS: tuple[str, ...] = ("and",)

_ALL_CONNECTORS: tuple[str, ...] = tuple(
    sorted(
        set(_ORDER_CONNECTORS + _STRONG_CONNECTORS + _WEAK_CONNECTORS),
        key=len,
        reverse=True,
    )
)

#: Leading order markers (stripped from a clause; they mark explicit ordering).
_ORDER_MARKER_WORDS: frozenset[str] = frozenset(
    {
        "first", "firstly", "second", "secondly", "third", "thirdly",
        "then", "next", "finally", "afterwards", "lastly",
    }
)

_NUMBERING_RE = re.compile(r"(?:^|\s)\(?\d+[\).:]\s+")
_WHITESPACE_RE = re.compile(r"\s+")

#: Read-only work operations.
_WORK_OPS: frozenset[str] = frozenset(
    {"investigate", "diagnose", "inspect", "examine", "trace"}
)
_KNOWLEDGE_OPS: frozenset[str] = frozenset(
    {"research", "acquire", "find", "look", "search", "study"}
)
#: Explicit analysis cues (a clause that reasons over an earlier RESULT).
_ANALYSIS_STRONG_CUES: frozenset[str] = frozenset(
    {"analyze", "analyse", "summarize", "summarise", "explain", "describe"}
)
_ANALYSIS_OPS: frozenset[str] = frozenset(
    {"explain", "summarize", "summarise", "describe"}
)
_RESULT_CUES: frozenset[str] = frozenset(
    {
        "findings", "finding", "result", "results", "output", "outputs",
        "it", "that", "this", "them", "those", "these", "evidence",
    }
)
_GAP_CUES: frozenset[str] = frozenset(
    {
        "gap", "gaps", "missing", "insufficient", "limitation", "limitations",
        "weakness", "weaknesses", "coverage", "untested", "uncovered",
    }
)

#: Executor labels.
EXEC_BUILTIN: str = "builtin"
EXEC_INVESTIGATION: str = "investigation"
EXEC_KNOWLEDGE: str = "knowledge"
EXEC_ANALYSIS: str = "analysis"
EXEC_NONE: str = "none"

#: Step status values (the *reading*, before any execution).
STATUS_READY: str = "ready"
STATUS_BLOCKED: str = "blocked"
STATUS_UNSUPPORTED: str = "unsupported"
STATUS_GOVERNED: str = "governed"

#: Dependency kinds.
DEP_NONE: str = "none"
DEP_RESULT: str = "result"


def _bounded(value: Any, limit: int = _MAX_CLAUSE_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _tokens(text: Any) -> frozenset[str]:
    return frozenset(
        token
        for token in re.findall(r"[a-z0-9][a-z0-9'-]*", str(text or "").lower())
    )


@dataclass(frozen=True, slots=True)
class StepClause:
    """One bounded clause of a request, with whether an order was expressed."""

    text: str
    ordered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "ordered": self.ordered}


@dataclass(frozen=True, slots=True)
class RequestStep:
    """One bounded intent/step read from the request (facts only)."""

    step_id: str
    clause: str
    operation: str
    domain: str
    subject: str
    executor: str
    order: "int | None" = None
    depends_on: str = ""
    dependency: str = DEP_NONE
    status: str = STATUS_READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "clause": self.clause,
            "operation": self.operation,
            "domain": self.domain,
            "subject": self.subject,
            "executor": self.executor,
            "order": self.order,
            "depends_on": self.depends_on,
            "dependency": self.dependency,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class MultiStepRequest:
    """Bounded multi-intent/multi-step understanding of one request."""

    steps: tuple[RequestStep, ...]
    ordered: bool = False
    raw_text: str = ""

    @property
    def executable(self) -> tuple[RequestStep, ...]:
        """Steps that a bounded read-only mechanism can actually run."""
        return tuple(
            step
            for step in self.steps
            if step.executor in (EXEC_INVESTIGATION, EXEC_KNOWLEDGE, EXEC_ANALYSIS)
            and step.status == STATUS_READY
        )

    @property
    def builtin_steps(self) -> tuple[RequestStep, ...]:
        return tuple(step for step in self.steps if step.executor == EXEC_BUILTIN)

    @property
    def reported_steps(self) -> tuple[RequestStep, ...]:
        """Steps that are recognised but cannot be run (unsupported/governed/blocked)."""
        return tuple(
            step
            for step in self.steps
            if step.status in (STATUS_UNSUPPORTED, STATUS_GOVERNED, STATUS_BLOCKED)
        )

    @property
    def has_operational_step(self) -> bool:
        return bool(self.executable)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ordered": self.ordered,
            "steps": [step.to_dict() for step in self.steps],
        }


# ---------------------------------------------------------------------------
# Clause splitting (ordering-aware)
# ---------------------------------------------------------------------------


def _strip_order_marker(clause: str) -> str:
    tokens = clause.split(" ", 1)
    if tokens and tokens[0].lower().strip(".,;:") in _ORDER_MARKER_WORDS:
        return tokens[1].strip() if len(tokens) > 1 else ""
    return clause


def split_clauses(text: Any) -> tuple[StepClause, ...]:
    """Split ``text`` into bounded clauses, tracking expressed order.

    Deterministic and bounded. Numbering ("1) … 2) …") always expresses order;
    the order connectors (:data:`_ORDER_CONNECTORS`) express an explicit
    successor. A weak "and" is kept as a clause boundary — the caller decides
    whether both sides are genuinely separate intents.
    """
    if not isinstance(text, str) or not text.strip():
        return ()
    working = _WHITESPACE_RE.sub(" ", re.sub(r"[,;]", " ", text)).strip()

    if _NUMBERING_RE.search(working):
        parts = [p.strip() for p in _NUMBERING_RE.split(working) if p.strip()]
        if len(parts) >= 2:
            return tuple(
                StepClause(text=_strip_order_marker(p), ordered=True)
                for p in parts[:MAX_REQUEST_STEPS]
            )

    parts: list[str] = []
    #: ``boundary_order[i]`` — the connector BEFORE part ``i`` carried an order.
    boundary_order: list[bool] = []
    pending_order = False
    remainder = working
    for _ in range(MAX_REQUEST_STEPS - 1):
        chosen: "tuple[int, int, str] | None" = None
        for connector in _ALL_CONNECTORS:
            match = re.search(rf"\s+{re.escape(connector)}\s+", remainder, re.IGNORECASE)
            if match is not None:
                chosen = (match.start(), match.end(), connector)
                break
        if chosen is None:
            break
        start, end, connector = chosen
        head = remainder[:start].strip()
        if head:
            parts.append(head)
            boundary_order.append(pending_order)
            pending_order = connector in _ORDER_CONNECTORS
        remainder = remainder[end:].strip()
    if remainder:
        parts.append(remainder)
        boundary_order.append(pending_order)

    clauses: list[StepClause] = []
    for index, part in enumerate(parts):
        leading = part.split(" ", 1)[0].lower().strip(".,;:") if part else ""
        had_marker = leading in _ORDER_MARKER_WORDS
        stripped = _strip_order_marker(part)
        if not stripped:
            continue
        preceding_order = index < len(boundary_order) and bool(boundary_order[index])
        clauses.append(
            StepClause(text=_bounded(stripped), ordered=had_marker or preceding_order)
        )
    return tuple(clauses[:MAX_REQUEST_STEPS])


def _has_strong_connector(text: str) -> bool:
    lowered = f" {str(text or '').lower()} "
    return any(f" {connector} " in lowered for connector in _STRONG_CONNECTORS)


# ---------------------------------------------------------------------------
# Step classification
# ---------------------------------------------------------------------------


def _classify(clause: str) -> "tuple[str, str, str, str]":
    """Return ``(operation, domain, subject, executor)`` for one clause."""
    frame = _frame.interpret(clause)
    operation = _bounded(getattr(frame, "operation", ""), 32).lower()
    domain = _bounded(getattr(frame.domain, "value", ""), 32).lower()
    subject = _bounded(getattr(frame, "subject", ""))
    tokens = _tokens(clause)

    analysis = bool(tokens & _ANALYSIS_STRONG_CUES) and (
        bool(tokens & _RESULT_CUES) or operation in _ANALYSIS_OPS
    )
    if analysis:
        return operation or "analyze", domain, subject, EXEC_ANALYSIS
    if operation in _WORK_OPS or domain == "investigation":
        return operation, domain, subject, EXEC_INVESTIGATION
    if operation in _KNOWLEDGE_OPS or domain == "knowledge":
        return operation, domain, subject, EXEC_KNOWLEDGE
    if domain in ("capabilities", "status", "self_knowledge", "casual"):
        return operation, domain, subject, EXEC_BUILTIN
    return operation, domain, subject, EXEC_NONE


def is_gap_clause(subject: str) -> bool:
    """True when an analysis clause asks for GAPS (bounded vocabulary only)."""
    return bool(_tokens(subject) & _GAP_CUES)


# ---------------------------------------------------------------------------
# Request builder
# ---------------------------------------------------------------------------


def build_multi_step(text: Any) -> "MultiStepRequest | None":
    """Build the bounded multi-step reading of ``text``, or ``None``.

    Returns ``None`` when the request is not a genuine multi-intent/multi-step
    request — fewer than two clauses, no runnable read-only step, or a single
    multi-clause intent that a weak connector must not split — so every existing
    route keeps its precedence.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    clauses = split_clauses(text)
    if len(clauses) < 2:
        return None

    classified = [_classify(clause.text) for clause in clauses]

    # Anti-over-split: without a STRONG connector, every clause must name a
    # bounded reading, so one multi-clause intent ("investigate the component
    # that handles X and Y") is never split.
    if not _has_strong_connector(text):
        if any(executor == EXEC_NONE for _op, _dom, _sub, executor in classified):
            return None

    ordered_request = any(clause.ordered for clause in clauses)

    steps: list[RequestStep] = []
    prev_work_id: str = ""
    for index, clause in enumerate(clauses):
        operation, domain, subject, executor = classified[index]
        step_id = f"step-{index:04d}"
        depends_on = ""
        dependency = DEP_NONE
        if executor == EXEC_BUILTIN:
            status = STATUS_READY
        elif executor == EXEC_NONE:
            frame = _frame.interpret(clause.text)
            status = (
                STATUS_GOVERNED
                if getattr(frame, "governance_sensitive", False)
                else STATUS_UNSUPPORTED
            )
        elif executor == EXEC_ANALYSIS:
            if prev_work_id:
                depends_on = prev_work_id
                dependency = DEP_RESULT
                status = STATUS_READY
            else:
                # An analysis of a result that was never produced is BLOCKED:
                # Atlas will not invent the missing prerequisite.
                status = STATUS_BLOCKED
        else:
            status = STATUS_READY
        if executor in (EXEC_INVESTIGATION, EXEC_KNOWLEDGE) and status == STATUS_READY:
            prev_work_id = step_id
        steps.append(
            RequestStep(
                step_id=step_id,
                clause=clause.text,
                operation=operation,
                domain=domain,
                subject=subject or clause.text,
                executor=executor,
                order=index if ordered_request else None,
                depends_on=depends_on,
                dependency=dependency,
                status=status,
            )
        )

    request = MultiStepRequest(
        steps=tuple(steps), ordered=ordered_request, raw_text=_bounded(text)
    )
    if not request.has_operational_step:
        return None
    return request


def build_execution_steps(request: MultiStepRequest) -> "tuple[Any, ...] | None":
    """Map the request's runnable steps onto the EXISTING executor's step kinds.

    Only the existing read-only kinds are emitted (INVESTIGATION / KNOWLEDGE /
    ANALYSIS / EVIDENCE_GAP_ANALYSIS); a step that cannot be run (unsupported,
    governed, or blocked without its prerequisite) is never emitted. Returns
    ``None`` when nothing is runnable, so the caller keeps its existing route.
    """
    from atlas.orchestration.execution_models import ExecutionStep
    from atlas.orchestration.models import NodeKind

    steps: list[Any] = []
    for step in request.executable:
        if step.executor == EXEC_INVESTIGATION:
            target = step.subject or step.clause
            steps.append(
                ExecutionStep(
                    step_id=step.step_id,
                    kind=NodeKind.INVESTIGATION,
                    target=target,
                    inputs={"objective": target},
                    description=f"Investigate: {target}",
                )
            )
        elif step.executor == EXEC_KNOWLEDGE:
            question = _frame.knowledge_subject(step.clause) or step.subject
            if not question:
                continue
            steps.append(
                ExecutionStep(
                    step_id=step.step_id,
                    kind=NodeKind.KNOWLEDGE,
                    target="retrieve",
                    inputs={"question": question},
                    description=f"Knowledge: {question}",
                )
            )
        elif step.executor == EXEC_ANALYSIS:
            # An analysis step runs ONLY over the RESULT it depends on; without
            # a satisfied prerequisite it is never executed (no invented input).
            if step.dependency != DEP_RESULT or not step.depends_on:
                continue
            if is_gap_clause(step.subject):
                kind = NodeKind.EVIDENCE_GAP_ANALYSIS
                target = "analyze_gaps"
            else:
                kind = NodeKind.ANALYSIS
                target = "synthesize"
            steps.append(
                ExecutionStep(
                    step_id=step.step_id,
                    kind=kind,
                    target=target,
                    inputs={},
                    depends_on=(step.depends_on,),
                    carry_from=(step.depends_on,),
                    description=f"Analyze the result of {step.depends_on}",
                )
            )
    return tuple(steps) if steps else None
