"""Atlas Orchestration — Data Models (P2/B2.1).

Pure, frozen value objects for the conversational orchestration skeleton.
B2.1 produces a deterministic, inspectable :class:`OrchestrationPlan` — an
intent plus a step graph of *registered* capabilities — with NO execution.

Planning-vs-execution boundary: these models describe *what* Atlas should do.
Execution (dispatch, tools, governed boundaries) is reserved for B2.2.

No infrastructure dependencies. No AI. No storage. No kernel. No runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OrchestrationStatus(str, Enum):
    """Terminal state of an orchestration plan."""

    READY = "ready"
    CLARIFICATION_NEEDED = "clarification_needed"
    FAILED = "failed"
    EMPTY = "empty"


class NodeKind(str, Enum):
    """Kinds of nodes a step graph may contain.

    B2.1 emits only ``CAPABILITY``. ``TOOL``, ``WORKSPACE``, ``RESEARCH``,
    and ``GOAL`` are future node kinds, defined here as the minimal
    structural boundary for B2.2 but never emitted by the planner.
    """

    CAPABILITY = "capability"
    TOOL = "tool"
    WORKSPACE = "workspace"
    RESEARCH = "research"
    GOAL = "goal"


class EdgeKind(str, Enum):
    """Kinds of edges a step graph may contain.

    B2.1 emits only ``SEQUENTIAL`` (a deterministic linear chain). The
    remaining kinds define the future execution-strategy boundary and are
    never emitted yet.
    """

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True)
class StepNode:
    """A single node in an orchestration step graph.

    A ``CAPABILITY`` node references a registered capability by name. A
    ``TOOL`` node would reference a tool name (future — never emitted in
    B2.1).

    Attributes:
        node_id: Stable unique id within the graph.
        kind: The node kind (``CAPABILITY`` in B2.1).
        action: The step action that produced this node (attribution).
        capability_name: Registered capability name (set for CAPABILITY).
        description: Human-readable description of the step.
        parameters: Structured parameters for the step (data only).
        metadata: Additional attribution/context.
    """

    node_id: str
    kind: NodeKind = NodeKind.CAPABILITY
    action: str = ""
    capability_name: str | None = None
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind.value,
            "action": self.action,
            "capability_name": self.capability_name,
            "description": self.description,
            "parameters": dict(self.parameters),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class StepEdge:
    """A directed edge between two step-graph nodes."""

    from_id: str
    to_id: str
    kind: EdgeKind = EdgeKind.SEQUENTIAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_id": self.from_id,
            "to_id": self.to_id,
            "kind": self.kind.value,
        }


@dataclass(frozen=True, slots=True)
class StepGraph:
    """An immutable, ordered step graph (nodes + edges)."""

    nodes: tuple[StepNode, ...] = ()
    edges: tuple[StepEdge, ...] = ()

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @property
    def is_empty(self) -> bool:
        return not self.nodes

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(node.node_id for node in self.nodes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": tuple(node.to_dict() for node in self.nodes),
            "edges": tuple(edge.to_dict() for edge in self.edges),
        }


@dataclass(frozen=True, slots=True)
class OrchestrationPlan:
    """Deterministic, inspectable result of planning a conversational request.

    Carries intent, a step graph of registered capabilities, and *projected*
    session attribution (three strings). The full session object is never
    embedded — the session subsystem remains the source of truth.

    Attributes:
        plan_id: Stable deterministic id (hash of the normalized goal).
        task_type: The TaskIntake classification (string value).
        intent: The bounded intent string.
        goal: The bounded goal string.
        graph: The step graph (nodes + edges). Empty for non-READY statuses.
        status: Terminal status (see :class:`OrchestrationStatus`).
        clarification_questions: Bounded questions when clarification is needed.
        session_id: Projected session attribution (or None).
        principal_id: Projected principal attribution (or None).
        authority: Projected authority string ("owner"/"user") or None.
        created_at: Creation timestamp (attribution only; not part of determinism).
        metadata: Additional context.
    """

    plan_id: str
    task_type: str
    intent: str
    goal: str
    graph: StepGraph = field(default_factory=StepGraph)
    status: OrchestrationStatus = OrchestrationStatus.EMPTY
    clarification_questions: tuple[str, ...] = ()
    session_id: str | None = None
    principal_id: str | None = None
    authority: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        return self.status is OrchestrationStatus.READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task_type": self.task_type,
            "intent": self.intent,
            "goal": self.goal,
            "graph": self.graph.to_dict(),
            "status": self.status.value,
            "clarification_questions": tuple(self.clarification_questions),
            "session_id": self.session_id,
            "principal_id": self.principal_id,
            "authority": self.authority,
            "created_at": self.created_at.isoformat(),
            "metadata": dict(self.metadata),
        }
