"""Atlas Toolchain — Capability Handlers (Phase 18.7).

Registers the four Track B capabilities following the Atlas
``CapabilityRegistry`` pattern (``CapabilityHandler = Callable[[dict], ExecutionResult]``):

  toolchain.execute_chain — plan a goal into a tool chain and execute it
  toolchain.run_skill      — look up a registered skill and execute its chain
  toolchain.effectiveness  — query per-tool effectiveness scores
  toolchain.skills         — list and filter registered skills

Handlers are pure bridges: all work is delegated to injected components
(planner, executor, registry, tracker). Deterministic, no mutation,
no evolution, no storage writes from the handlers themselves.

No handler mutates Atlas state. No handler directly mutates the
``CapabilityRegistry`` — the :meth:`ToolchainCapabilityFactory.register`
method is the only registration surface, mirroring the Track A
``ResearchCapabilityFactory`` pattern.
"""

from __future__ import annotations

from typing import Any, Callable

from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.toolchain.effectiveness import ToolEffectivenessTracker
from atlas.toolchain.executor import ToolChainExecutor
from atlas.toolchain.models import (
    Skill,
    SkillKind,
    ToolChain,
    ToolChainPlan,
    ToolChainResult,
    ToolStep,
)
from atlas.toolchain.planner import ToolChainPlanner
from atlas.toolchain.registry import SkillRegistry

CapabilityHandler = Callable[[dict[str, Any]], ExecutionResult]


class ToolchainCapabilityFactory:
    """Constructs the four Track B capability handlers with DI.

    Mirrors :class:`~atlas.research.capability_handlers.ResearchCapabilityFactory`:
    constructor injection of all collaborators, a ``handlers()`` method
    returning the capability map, and a ``register()`` method that adds
    them to a ``CapabilityRegistry``.

    No handler mutates state. No direct registry mutation — ``register()``
    is the only registration surface.
    """

    def __init__(
        self,
        planner: ToolChainPlanner | None = None,
        executor: ToolChainExecutor | None = None,
        registry: SkillRegistry | None = None,
        tracker: ToolEffectivenessTracker | None = None,
    ) -> None:
        """Initialise the factory with optional constructor-injected deps.

        Args:
            planner: Tool chain planner for goal decomposition. If ``None``,
                a default :class:`ToolChainPlanner` (no tool provider) is
                created — plans will be empty until a provider is wired.
            executor: Tool chain executor. If ``None``, a default
                :class:`ToolChainExecutor` (no invoker) is created — all
                executions fail-closed until an invoker is wired.
            registry: Skill registry for skill lookup. If ``None``, a default
                empty :class:`SkillRegistry` is created.
            tracker: Effectiveness tracker for score queries. If ``None``,
                a default empty :class:`ToolEffectivenessTracker` is created.
        """
        self._planner: ToolChainPlanner = planner or ToolChainPlanner()
        self._executor: ToolChainExecutor = executor or ToolChainExecutor()
        self._registry: SkillRegistry = registry or SkillRegistry()
        self._tracker: ToolEffectivenessTracker = tracker or ToolEffectivenessTracker()

    @property
    def planner(self) -> ToolChainPlanner:
        """The injected tool chain planner."""
        return self._planner

    @property
    def executor(self) -> ToolChainExecutor:
        """The injected tool chain executor."""
        return self._executor

    @property
    def registry(self) -> SkillRegistry:
        """The injected skill registry."""
        return self._registry

    @property
    def tracker(self) -> ToolEffectivenessTracker:
        """The injected effectiveness tracker."""
        return self._tracker

    # ------------------------------------------------------------------
    # Registration surface
    # ------------------------------------------------------------------

    def handlers(self) -> dict[str, CapabilityHandler]:
        """Return the four toolchain capabilities keyed by name."""
        return {
            "toolchain.execute_chain": self._execute_chain_handler,
            "toolchain.run_skill": self._run_skill_handler,
            "toolchain.effectiveness": self._effectiveness_handler,
            "toolchain.skills": self._skills_handler,
        }

    def register(self, registry: CapabilityRegistry) -> None:
        """Register all four handlers into a ``CapabilityRegistry``.

        This is the only registration surface — no handler directly mutates
        the registry. Mirrors the Track A ``ResearchCapabilityFactory.register``
        pattern.
        """
        for name, handler in self.handlers().items():
            registry.register(name, handler)

    # ------------------------------------------------------------------
    # toolchain.execute_chain — plan + execute
    # ------------------------------------------------------------------

    def _execute_chain_handler(self, params: dict[str, Any]) -> ExecutionResult:
        """Execute a tool chain from a goal, chain, or plan.

        Params:
            goal (str): High-level goal to decompose and execute.
            chain (ToolChain): Pre-built chain to execute directly.
            plan (ToolChainPlan): Pre-built plan to execute directly.
            parameters (dict): Optional shared parameters for execution.

        If ``goal`` is provided, the planner decomposes it into a plan
        which is then executed. If ``chain`` or ``plan`` is provided, it
        is executed directly. Fail-closed: missing/invalid input returns
        a failed ``ExecutionResult`` with a descriptive error.
        """
        goal = params.get("goal")
        chain = params.get("chain")
        plan = params.get("plan")
        shared_params = params.get("parameters")

        try:
            if isinstance(chain, ToolChain):
                result: ToolChainResult = self._executor.execute(
                    chain, parameters=shared_params
                )
            elif isinstance(plan, ToolChainPlan):
                result = self._executor.execute(plan, parameters=shared_params)
            elif isinstance(goal, str) and goal.strip():
                built_plan: ToolChainPlan = self._planner.plan(goal)
                result = self._executor.execute(built_plan, parameters=shared_params)
            else:
                return ExecutionResult(
                    capability="toolchain.execute_chain",
                    success=False,
                    error=(
                        "'goal' (str), 'chain' (ToolChain), or 'plan' "
                        "(ToolChainPlan) is required"
                    ),
                    metadata={"handler": "toolchain.execute_chain"},
                )

            return ExecutionResult(
                capability="toolchain.execute_chain",
                success=result.success,
                output={"result": result.to_dict()},
                error=result.error,
                metadata={
                    "handler": "toolchain.execute_chain",
                    "chain_id": result.chain_id,
                    "step_count": len(result.step_results),
                },
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="toolchain.execute_chain",
                success=False,
                error=str(exc),
                metadata={"handler": "toolchain.execute_chain"},
            )

    # ------------------------------------------------------------------
    # toolchain.run_skill — look up and execute a registered skill
    # ------------------------------------------------------------------

    def _run_skill_handler(self, params: dict[str, Any]) -> ExecutionResult:
        """Look up a skill by id and execute its chain.

        Params:
            skill_id (str): The id of the skill to run.
            parameters (dict): Optional shared parameters for execution.

        Fail-closed: missing skill_id, unknown skill, inactive skill, or
        a skill without a chain all return a failed ``ExecutionResult``.
        """
        skill_id = params.get("skill_id")
        if not isinstance(skill_id, str) or not skill_id.strip():
            return ExecutionResult(
                capability="toolchain.run_skill",
                success=False,
                error="'skill_id' is required",
                metadata={"handler": "toolchain.run_skill"},
            )

        shared_params = params.get("parameters")

        try:
            skill: Skill | None = self._registry.get(skill_id)
            if skill is None:
                return ExecutionResult(
                    capability="toolchain.run_skill",
                    success=False,
                    error=f"Skill '{skill_id}' not found",
                    metadata={"handler": "toolchain.run_skill"},
                )
            if not skill.is_active:
                return ExecutionResult(
                    capability="toolchain.run_skill",
                    success=False,
                    error=f"Skill '{skill_id}' is not active",
                    metadata={"handler": "toolchain.run_skill"},
                )

            chain: ToolChain | None = self._build_skill_chain(skill)
            if chain is None:
                return ExecutionResult(
                    capability="toolchain.run_skill",
                    success=False,
                    error=f"Skill '{skill_id}' has no chain to execute",
                    metadata={"handler": "toolchain.run_skill"},
                )

            result: ToolChainResult = self._executor.execute(
                chain, parameters=shared_params
            )
            return ExecutionResult(
                capability="toolchain.run_skill",
                success=result.success,
                output={"result": result.to_dict(), "skill": skill.to_dict()},
                error=result.error,
                metadata={
                    "handler": "toolchain.run_skill",
                    "skill_id": skill.skill_id,
                    "chain_id": result.chain_id,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="toolchain.run_skill",
                success=False,
                error=str(exc),
                metadata={"handler": "toolchain.run_skill"},
            )

    # ------------------------------------------------------------------
    # toolchain.effectiveness — query effectiveness scores
    # ------------------------------------------------------------------

    def _effectiveness_handler(self, params: dict[str, Any]) -> ExecutionResult:
        """Query per-tool effectiveness scores.

        Params:
            tool_name (str, optional): Return the score for a single tool.
                If omitted, returns scores for all observed tools.

        Always succeeds (returns ``success=True``) — querying a tool with
        no observations returns a default score, not an error.
        """
        tool_name = params.get("tool_name")
        if isinstance(tool_name, str) and tool_name.strip():
            score = self._tracker.score(tool_name)
            return ExecutionResult(
                capability="toolchain.effectiveness",
                success=True,
                output={"score": score.to_dict()},
                metadata={
                    "handler": "toolchain.effectiveness",
                    "tool_name": tool_name,
                },
            )
        scores = self._tracker.score_all()
        return ExecutionResult(
            capability="toolchain.effectiveness",
            success=True,
            output={"scores": [s.to_dict() for s in scores]},
            metadata={
                "handler": "toolchain.effectiveness",
                "count": len(scores),
            },
        )

    # ------------------------------------------------------------------
    # toolchain.skills — list and filter registered skills
    # ------------------------------------------------------------------

    def _skills_handler(self, params: dict[str, Any]) -> ExecutionResult:
        """List and filter registered skills.

        Params (all optional, mutually exclusive filters applied in order):
            active_only (bool): If true, return only active skills.
            category (str): Filter by category.
            tag (str): Filter by tag.
            kind (str): Filter by skill kind (e.g. "BUILTIN", "COMPOSED").

        Without filters, returns all registered skills sorted by id.
        """
        active_only = bool(params.get("active_only", False))
        category = params.get("category")
        tag = params.get("tag")
        kind_str = params.get("kind")

        try:
            if active_only:
                skills: list[Skill] = self._registry.list_active()
            elif isinstance(category, str) and category.strip():
                skills = self._registry.find_by_category(category)
            elif isinstance(tag, str) and tag.strip():
                skills = self._registry.find_by_tag(tag)
            elif isinstance(kind_str, str) and kind_str.strip():
                try:
                    kind = SkillKind[kind_str.upper()]
                except KeyError:
                    return ExecutionResult(
                        capability="toolchain.skills",
                        success=False,
                        error=f"Unknown skill kind: '{kind_str}'",
                        metadata={"handler": "toolchain.skills"},
                    )
                skills = self._registry.find_by_kind(kind)
            else:
                skills = self._registry.list()

            return ExecutionResult(
                capability="toolchain.skills",
                success=True,
                output={"skills": [s.to_dict() for s in skills]},
                metadata={
                    "handler": "toolchain.skills",
                    "count": len(skills),
                },
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="toolchain.skills",
                success=False,
                error=str(exc),
                metadata={"handler": "toolchain.skills"},
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_skill_chain(skill: Skill) -> ToolChain | None:
        """Build a :class:`ToolChain` from a skill for execution.

        For BUILTIN skills, wraps the single tool in a one-step chain.
        For COMPOSED/LEARNED skills, returns the skill's chain.
        Returns ``None`` if the skill has no executable chain.
        """
        if skill.is_builtin:
            return ToolChain(
                chain_id=f"chain::skill::{skill.skill_id}",
                goal=skill.description or skill.name,
                steps=(
                    ToolStep(
                        step_id="step:0000",
                        tool_name=skill.tool_name,
                        description=skill.description,
                    ),
                ),
                strategy="sequential",
            )
        return skill.chain


# ---------------------------------------------------------------------------
# Module-level convenience for registry registration
# ---------------------------------------------------------------------------

_toolchain_factory: ToolchainCapabilityFactory | None = None


def toolchain_handlers() -> dict[str, CapabilityHandler]:
    """Return the four toolchain capability handlers (cached factory).

    Mirrors the Track A ``research_handlers()`` convenience function.
    """
    global _toolchain_factory
    if _toolchain_factory is None:
        _toolchain_factory = ToolchainCapabilityFactory()
    return _toolchain_factory.handlers()