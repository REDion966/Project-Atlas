"""
Atlas Planning Engine

Pure logic component that decomposes flat ReasoningPlan instances into
structured PlanningPlan instances with sub-goals, dependency analysis,
and validation.

This is a pure logic component with no infrastructure dependencies.
It does not call AI providers, access memory, query knowledge, or
interact with the EventBus.

Phase 6.8 — Planning Engine.
"""

from typing import Any

from atlas.reasoning.models import ReasoningPlan
from atlas.reasoning.planning.models import PlanningPlan, PlanningStep


class PlanningEngine:
    """
    Decomposes flat ReasoningPlan instances into structured PlanningPlan
    instances with sub-goals, dependency analysis, and validation.

    Pure logic component — no infrastructure dependencies.
    """

    def decompose(
        self,
        plan: ReasoningPlan,
    ) -> PlanningPlan:
        """
        Analyze a ReasoningPlan and produce a decomposed PlanningPlan.

        Strategy:
        1. Parse the goal to identify potential sub-goals.
        2. Create steps with dependency ordering.
        3. Validate the resulting plan.
        4. Return the enriched PlanningPlan.

        When the plan is already simple (single step, no decomposition
        needed), returns a PlanningPlan with a single step and no
        dependencies — preserving the original behavior.

        Args:
            plan: The ReasoningPlan to decompose.

        Returns:
            A PlanningPlan with sub-goals, steps, and dependency
            information.
        """
        if not plan.steps:
            return PlanningPlan(
                goal=plan.goal,
                status="completed",
                metadata=dict(plan.metadata),
            )

        if len(plan.steps) == 1:
            # Simple plan — no decomposition needed
            step = plan.steps[0]
            planning_step = PlanningStep(
                id="step-1",
                description=step.description,
                action=step.action,
                parameters=dict(step.parameters),
                status="pending",
            )
            return PlanningPlan(
                goal=plan.goal,
                sub_goals=[plan.goal],
                steps=[planning_step],
                dependencies={},
                status="pending",
                metadata=dict(plan.metadata),
            )

        # Multi-step plan — decompose into sub-goals with dependencies
        sub_goals = self._extract_sub_goals(plan)
        steps = self._build_steps(plan, sub_goals)
        dependencies = self._build_dependencies(steps)

        planning_plan = PlanningPlan(
            goal=plan.goal,
            sub_goals=sub_goals,
            steps=steps,
            dependencies=dependencies,
            status="pending",
            metadata=dict(plan.metadata),
        )

        validation_errors = self.validate(planning_plan)
        planning_plan.validation_errors = validation_errors

        return planning_plan

    def validate(
        self,
        plan: PlanningPlan,
    ) -> list[str]:
        """
        Validate a PlanningPlan for internal consistency.

        Checks:
        - No circular dependencies.
        - All dependency references resolve to existing steps.
        - Steps have non-empty actions.
        - Sub-goals are non-empty (if present).

        Args:
            plan: The PlanningPlan to validate.

        Returns:
            A list of validation error strings. Returns an empty list
            if the plan is valid.
        """
        errors: list[str] = []

        if not plan.steps:
            return errors

        step_ids = {step.id for step in plan.steps}

        # Check for empty actions
        for step in plan.steps:
            if not step.action.strip():
                errors.append(
                    f"Step '{step.id}' has an empty action."
                )

        # Check for unresolved dependency references
        for step in plan.steps:
            for dep_id in step.depends_on:
                if dep_id not in step_ids:
                    errors.append(
                        f"Step '{step.id}' depends on unknown step "
                        f"'{dep_id}'."
                    )

        # Check for circular dependencies
        circular = self._detect_circular_dependencies(plan)
        errors.extend(circular)

        # Check for empty sub-goals (if any sub-goals exist)
        if plan.sub_goals:
            empty_sub_goals = [
                sg for sg in plan.sub_goals if not sg.strip()
            ]
            if empty_sub_goals:
                errors.append(
                    "Plan contains empty sub-goal entries."
                )

        return errors

    def next_steps(
        self,
        plan: PlanningPlan,
    ) -> list[PlanningStep]:
        """
        Return the next executable steps in a plan.

        A step is executable when:
        - Its status is 'pending'.
        - All dependencies have status 'completed'.

        Args:
            plan: The PlanningPlan to query.

        Returns:
            A list of PlanningStep instances that are ready to execute.
            Returns an empty list if no steps are ready.
        """
        if plan.status in ("completed", "failed"):
            return []

        completed_ids = {
            step.id
            for step in plan.steps
            if step.status == "completed"
        }

        ready: list[PlanningStep] = []
        for step in plan.steps:
            if step.status != "pending":
                continue
            if all(dep_id in completed_ids for dep_id in step.depends_on):
                ready.append(step)

        return ready

    def _extract_sub_goals(
        self,
        plan: ReasoningPlan,
    ) -> list[str]:
        """
        Extract sub-goals from a multi-step ReasoningPlan.

        For plans with multiple steps, each step description is treated
        as a potential sub-goal. If the goal contains common delimiters
        (e.g. 'then', 'and', ';'), it is split into sub-goals.

        Args:
            plan: The ReasoningPlan to extract sub-goals from.

        Returns:
            A list of sub-goal strings.
        """
        sub_goals: list[str] = []

        # Try to split the goal by common delimiters
        goal = plan.goal
        for delimiter in [";", "\n", " and then ", " then "]:
            if delimiter in goal:
                parts = [
                    part.strip()
                    for part in goal.split(delimiter)
                    if part.strip()
                ]
                if len(parts) > 1:
                    sub_goals.extend(parts)
                    break

        # Fall back to step descriptions as sub-goals
        if not sub_goals:
            for step in plan.steps:
                if step.description.strip():
                    sub_goals.append(step.description)

        return sub_goals

    def _build_steps(
        self,
        plan: ReasoningPlan,
        sub_goals: list[str],
    ) -> list[PlanningStep]:
        """
        Build PlanningStep instances from a ReasoningPlan.

        Each step in the original plan becomes a PlanningStep. When
        there are more sub-goals than steps, additional steps are
        created for the extra sub-goals.

        Args:
            plan: The source ReasoningPlan.
            sub_goals: The extracted sub-goals.

        Returns:
            A list of PlanningStep instances.
        """
        steps: list[PlanningStep] = []

        for i, step in enumerate(plan.steps):
            step_id = f"step-{i + 1}"
            planning_step = PlanningStep(
                id=step_id,
                description=step.description,
                action=step.action,
                parameters=dict(step.parameters),
                status="pending",
            )
            steps.append(planning_step)

        # Create additional steps for extra sub-goals beyond existing steps
        for i in range(len(plan.steps), len(sub_goals)):
            step_id = f"step-{i + 1}"
            planning_step = PlanningStep(
                id=step_id,
                description=sub_goals[i],
                action="process",
                parameters={},
                status="pending",
            )
            steps.append(planning_step)

        return steps

    def _build_dependencies(
        self,
        steps: list[PlanningStep],
    ) -> dict[str, list[str]]:
        """
        Build a dependency map from a list of PlanningStep instances.

        Steps are ordered sequentially by default: step N depends on
        step N-1. Explicit dependencies from step.depends_on are
        preserved.

        Args:
            steps: The list of PlanningStep instances.

        Returns:
            A dict mapping step_id to a list of dependency step IDs.
        """
        dependencies: dict[str, list[str]] = {}

        for i, step in enumerate(steps):
            deps: list[str] = []

            # Include explicit dependencies
            deps.extend(step.depends_on)

            # Add sequential dependency (previous step)
            if i > 0 and steps[i - 1].id not in deps:
                deps.append(steps[i - 1].id)

            if deps:
                dependencies[step.id] = deps
            else:
                dependencies[step.id] = []

        return dependencies

    def _detect_circular_dependencies(
        self,
        plan: PlanningPlan,
    ) -> list[str]:
        """
        Detect circular dependencies in a PlanningPlan.

        Uses DFS-based cycle detection on the dependency graph.

        Args:
            plan: The PlanningPlan to check.

        Returns:
            A list of error strings describing any circular
            dependencies found. Returns an empty list if no cycles
            exist.
        """
        step_ids = {step.id for step in plan.steps}
        errors: list[str] = []

        # Build adjacency list
        adj: dict[str, list[str]] = {}
        for step in plan.steps:
            adj[step.id] = list(step.depends_on)

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {sid: WHITE for sid in step_ids}

        def dfs(node: str, path: list[str]) -> bool:
            color[node] = GRAY
            path.append(node)

            for neighbor in adj.get(node, []):
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    errors.append(
                        f"Circular dependency detected: "
                        f"{' -> '.join(cycle)}"
                    )
                    path.pop()
                    color[node] = BLACK
                    return True
                if color[neighbor] == WHITE:
                    if dfs(neighbor, path):
                        path.pop()
                        color[node] = BLACK
                        return True

            path.pop()
            color[node] = BLACK
            return False

        for sid in step_ids:
            if color[sid] == WHITE:
                dfs(sid, [])

        return errors