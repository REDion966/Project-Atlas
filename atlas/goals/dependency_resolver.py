"""
Atlas DependencyResolver — Phase 8.3

Builds a dependency graph from improvement opportunities.
Detects cycles, blocked goals, independent goals, and prerequisites.
Produces execution ordering. Pure logic.
"""

from typing import Any

from atlas.goals.models import (
    GoalDependency,
    GoalEvaluation,
    GoalStatus,
    ImprovementOpportunity,
)


class DependencyResolver:
    """Resolves dependencies and produces execution ordering."""

    def build_graph(
        self,
        opportunities: list[ImprovementOpportunity],
    ) -> dict[str, list[str]]:
        """
        Build adjacency list from opportunity dependencies.

        Returns: {goal_id: [dependent_goal_ids]}
        """
        graph: dict[str, list[str]] = {}
        for opp in opportunities:
            if opp.opportunity_id not in graph:
                graph[opp.opportunity_id] = []
            for dep in opp.dependencies:
                if dep.source_goal_id not in graph:
                    graph[dep.source_goal_id] = []
                graph[dep.source_goal_id].append(dep.target_goal_id)
        return graph

    def find_independent(
        self,
        opportunities: list[ImprovementOpportunity],
    ) -> list[ImprovementOpportunity]:
        """Return opportunities with zero dependencies."""
        return [o for o in opportunities if o.dependency_count == 0]

    def find_blocked(
        self,
        opportunities: list[ImprovementOpportunity],
    ) -> list[GoalEvaluation]:
        """Return evaluations for opportunities blocked by dependencies."""
        blocked: list[GoalEvaluation] = []
        for opp in opportunities:
            if opp.dependency_count > 0:
                blockers = [d.target_goal_id for d in opp.dependencies]
                blocked.append(GoalEvaluation(
                    goal_id=opp.opportunity_id,
                    status=GoalStatus.ANALYZED,
                    current_progress=f"Blocked by {len(blockers)} dependencies",
                    blockers=blockers,
                    evidence_quality=opp.confidence,
                ))
        return blocked

    def detect_cycles(self, graph: dict[str, list[str]]) -> list[list[str]]:
        """
        Detect cycles in dependency graph using DFS.

        Returns list of cycles found.
        """
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:])

            path.pop()
            rec_stack.discard(node)

        for node in graph:
            if node not in visited:
                dfs(node)

        return cycles

    def resolve_order(
        self,
        opportunities: list[ImprovementOpportunity],
    ) -> list[ImprovementOpportunity]:
        """
        Produce topological execution ordering.
        Independent goals first, then by dependency count ascending.
        """
        independent = self.find_independent(opportunities)
        dependent = [o for o in opportunities if o.dependency_count > 0]
        dependent.sort(key=lambda o: o.dependency_count)

        return independent + dependent

    def summary(self, opportunities: list[ImprovementOpportunity]) -> dict[str, Any]:
        blocked = self.find_blocked(opportunities)
        independent = self.find_independent(opportunities)
        return {
            "total": len(opportunities),
            "independent": len(independent),
            "blocked": len(blocked),
            "blocked_details": [
                {"goal_id": b.goal_id, "blockers": b.blockers}
                for b in blocked
            ],
        }