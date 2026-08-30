"""Atlas Orchestration — Orchestrator Skeleton (P2/B2.1).

Converts a casual conversational request into a deterministic, inspectable
:class:`OrchestrationPlan` (intent + step graph of registered capabilities)
WITHOUT executing anything.

Pipeline (planning only):
    TaskIntake → PlanningEngine.decompose → CapabilityAnalyzer.analyze_step
    → CapabilityRegistry.has (routability check) → StepGraph

The strict planning-vs-execution boundary is preserved: no
``CapabilityDispatcher.dispatch``, no tool execution, no repository mutation,
no side effects. B2.2 owns execution.

Pure: no kernel, runtime, AI, storage, or evolution imports.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.reasoning.planning.engine import PlanningEngine
from atlas.reasoning.planning.models import PlanningPlan, PlanningStep

from atlas.orchestration.models import (
    EdgeKind,
    NodeKind,
    OrchestrationPlan,
    OrchestrationStatus,
    StepEdge,
    StepGraph,
    StepNode,
)

if TYPE_CHECKING:
    from atlas.conversation.task_intake import TaskIntake, TaskSpec
    from atlas.session.context import SessionContext


class Orchestrator:
    """Pure, deterministic conversational-orchestration planner.

    All collaborators are injected and optional. Missing collaborators
    degrade to a safe ``FAILED``/``EMPTY`` plan — the orchestrator never
    raises and never fabricates an executable capability.

    Args:
        task_intake: Converts raw text into a structured :class:`TaskSpec`.
        planning_engine: Decomposes a reasoning plan into ordered steps.
        capability_analyzer: Maps a planning step to a capability.
        capability_registry: Validates that a capability is registered
            (routability check only; never used for dispatch).
    """

    def __init__(
        self,
        task_intake: TaskIntake | None = None,
        planning_engine: PlanningEngine | None = None,
        capability_analyzer: CapabilityAnalyzer | None = None,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self._task_intake = task_intake
        self._planning_engine = planning_engine
        self._capability_analyzer = capability_analyzer
        self._capability_registry = capability_registry

    def plan(
        self,
        text: str,
        session_context: SessionContext | None = None,
    ) -> OrchestrationPlan:
        """Plan a conversational request into an ``OrchestrationPlan``.

        Fail-closed and deterministic. Never raises. Performs no execution.

        Args:
            text: The casual user request to plan.
            session_context: Optional attribution envelope. Only its
                ``session_id``, ``principal_id``, and ``authority`` values
                are projected onto the plan; the object is never stored.

        Returns:
            A deterministic :class:`OrchestrationPlan`.
        """
        if not isinstance(text, str) or not text.strip():
            return self._terminal(OrchestrationStatus.EMPTY, "", "", "", session_context)

        spec = self._intake(text)
        if spec is None:
            return self._terminal(
                OrchestrationStatus.FAILED, "", "", "", session_context
            )

        goal = spec.goal_string()
        intent = spec.intent
        task_type = spec.task_type.value

        if spec.needs_clarification:
            questions = tuple(
                getattr(spec.ambiguity, "clarification_questions", ()) or ()
            )
            return self._terminal(
                OrchestrationStatus.CLARIFICATION_NEEDED,
                task_type,
                intent,
                goal,
                session_context,
                clarification_questions=questions,
            )

        graph = self._build_graph(spec)
        if graph.is_empty:
            return self._terminal(
                OrchestrationStatus.FAILED,
                task_type,
                intent,
                goal,
                session_context,
            )

        return OrchestrationPlan(
            plan_id=self._plan_id(goal),
            task_type=task_type,
            intent=intent,
            goal=goal,
            graph=graph,
            status=OrchestrationStatus.READY,
            session_id=self._project(session_context, "session_id"),
            principal_id=self._project(session_context, "principal_id"),
            authority=self._project(session_context, "authority"),
        )

    # ------------------------------------------------------------------
    # Planning stages
    # ------------------------------------------------------------------

    def _intake(self, text: str) -> TaskSpec | None:
        if self._task_intake is None:
            return None
        try:
            return self._task_intake.intake(text)
        except Exception:
            return None

    def _build_graph(self, spec: TaskSpec) -> StepGraph:
        """Build a deterministic step graph from a structured TaskSpec.

        Returns an empty graph when no registered capability is routable.
        """
        planning_plan = self._decompose(spec)
        if planning_plan is None:
            return StepGraph()

        nodes: list[StepNode] = []
        for step in planning_plan.steps:
            node = self._node_for_step(step, index=len(nodes))
            if node is not None:
                nodes.append(node)

        if not nodes:
            return StepGraph()

        edges = _sequential_edges([node.node_id for node in nodes])
        return StepGraph(nodes=tuple(nodes), edges=tuple(edges))

    def _decompose(self, spec: TaskSpec) -> PlanningPlan | None:
        if self._planning_engine is None:
            return None
        plan = ReasoningPlan(
            goal=spec.goal_string(),
            steps=[ReasoningStep(action="process", description=spec.intent)],
        )
        try:
            return self._planning_engine.decompose(plan)
        except Exception:
            return None

    def _node_for_step(self, step: PlanningStep, index: int) -> StepNode | None:
        """Map one planning step to a StepNode, or None if not routable.

        Only registered capabilities are emitted. Unregistered capabilities
        (and any missing analyzer) are dropped — never fabricated.
        """
        if self._capability_analyzer is None or self._capability_registry is None:
            return None
        capability = self._capability_analyzer.analyze_step(step)
        if not self._capability_registry.has(capability.name):
            return None
        return StepNode(
            node_id=f"node-{index:04d}",
            kind=NodeKind.CAPABILITY,
            action=step.action or capability.name,
            capability_name=capability.name,
            description=step.description or capability.reason,
            parameters=dict(step.parameters),
            metadata={"reason": capability.reason},
        )

    # ------------------------------------------------------------------
    # Terminal / attribution helpers
    # ------------------------------------------------------------------

    def _terminal(
        self,
        status: OrchestrationStatus,
        task_type: str,
        intent: str,
        goal: str,
        session_context: SessionContext | None,
        clarification_questions: tuple[str, ...] = (),
    ) -> OrchestrationPlan:
        return OrchestrationPlan(
            plan_id=self._plan_id(goal),
            task_type=task_type,
            intent=intent,
            goal=goal,
            graph=StepGraph(),
            status=status,
            clarification_questions=clarification_questions,
            session_id=self._project(session_context, "session_id"),
            principal_id=self._project(session_context, "principal_id"),
            authority=self._project(session_context, "authority"),
        )

    @staticmethod
    def _project(session_context: SessionContext | None, field: str) -> str | None:
        """Project one attribution string from a session envelope.

        Returns ``None`` when absent or when the value is not a str. The
        full session object is never retained.
        """
        if session_context is None:
            return None
        value = getattr(session_context, field, None)
        if not isinstance(value, str):
            # ``authority`` is an ``AuthorityLevel`` enum on SessionContext;
            # accept enums via ``.value``.
            value = getattr(value, "value", None)
        return value if isinstance(value, str) else None

    @staticmethod
    def _plan_id(goal: str) -> str:
        """Deterministic plan id from the goal string (sha256[:16])."""
        normalized = (goal or "").strip()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        return f"orchestration::{digest}"


def _sequential_edges(node_ids: list[str]) -> list[StepEdge]:
    """Build a deterministic linear chain of SEQUENTIAL edges."""
    return [
        StepEdge(from_id=node_ids[i], to_id=node_ids[i + 1], kind=EdgeKind.SEQUENTIAL)
        for i in range(len(node_ids) - 1)
    ]
