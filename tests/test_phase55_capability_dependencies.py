"""Phase 5.5 — Capability dependencies: evidence contract.

Investigation result: dependencies are already represented and enforced through
the existing models, so no second dependency framework was introduced.

* Component dependencies: ``ComponentMetadata.dependencies`` projected by
  ``ArchitectureModel`` (declared) — the capability-provider dependency boundary.
* Planning dependencies: ``PlanningPlan.dependencies`` + ``PlanningEngine.validate``
  (unknown/circular dependency detection).
* Execution dependencies: ``ExecutionStep.depends_on`` enforced by
  ``OrchestrationExecutor`` (ordering; blocked-after-failure).
"""

from __future__ import annotations

from atlas.authority.service import AuthorityService
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata
from atlas.orchestration.execution_models import (
    ExecutionRequest,
    ExecutionState,
    ExecutionStep,
)
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.models import NodeKind
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.reasoning.planning.engine import PlanningEngine
from atlas.reasoning.planning.models import PlanningPlan, PlanningStep
from atlas.self_knowledge.architecture_model import build_architecture_model
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager


def _authority_ctx():
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    return authority, SessionContext.from_session(manager.create_session("owner"))


class TestPhase55CapabilityDependencies:
    def test_component_dependencies_are_projected(self):
        registry = ComponentRegistry()
        registry.register(
            ComponentMetadata(
                name="memory_service",
                package="atlas.memory.service",
                module_path="atlas.memory.service.memory_manager_service",
                dependencies=["memory_repository", "ranking_engine"],
                provided_capabilities=["memory_search"],
            )
        )
        model = build_architecture_model(registry)
        entry = next(c for c in model.components if c.name == "memory_service")
        assert entry.declared_dependencies == ("memory_repository", "ranking_engine")

    def test_planning_dependencies_are_detected_and_validated(self):
        planner = PlanningEngine()
        plan = ReasoningPlan(
            goal="g",
            steps=[
                ReasoningStep(description="query", action="query"),
                ReasoningStep(description="analyse", action="analyze"),
            ],
        )
        planning_plan = planner.decompose(plan)
        assert planning_plan.dependencies["step-2"] == ["step-1"]

        unknown = PlanningPlan(
            goal="g", steps=[PlanningStep(id="s1", action="a", depends_on=["nope"])]
        )
        assert any("unknown step" in e for e in planner.validate(unknown))

    def test_circular_dependencies_are_detected(self):
        plan = PlanningPlan(
            goal="g",
            steps=[
                PlanningStep(id="s1", action="a", depends_on=["s2"]),
                PlanningStep(id="s2", action="b", depends_on=["s1"]),
            ],
        )
        assert any("Circular" in e for e in PlanningEngine().validate(plan))

    def test_execution_dependency_failure_blocks_dependents(self):
        registry = CapabilityRegistry()
        registry.register(
            "a", lambda params: ExecutionResult(capability="a", success=False, error="boom")
        )
        registry.register(
            "b", lambda params: ExecutionResult(capability="b", success=True)
        )
        authority, ctx = _authority_ctx()
        executor = OrchestrationExecutor(
            capability_registry=registry,
            capability_dispatcher=CapabilityDispatcher(registry),
            authority_service=authority,
        )
        steps = (
            ExecutionStep(step_id="s1", kind=NodeKind.CAPABILITY, target="a"),
            ExecutionStep(
                step_id="s2", kind=NodeKind.CAPABILITY, target="b", depends_on=("s1",)
            ),
        )
        result = executor.execute(ExecutionRequest(steps=steps, session_context=ctx))

        assert result.steps[0].state is ExecutionState.FAILED
        assert result.steps[1].state is ExecutionState.BLOCKED
        assert result.steps[1].failure_kind == "dependency_failed"
