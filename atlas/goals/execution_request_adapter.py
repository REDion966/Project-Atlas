"""
Atlas Goal Execution — ExecutionRequestAdapter — Phase 15.1

The SOLE translator of ``ExecutionAction`` into the ``ExecutionGateway``
request format.

Phase 15's concrete form is a goal-derived ``EvolutionProposal`` with
``target_components = ["goal_execution"]`` and ``status = APPROVED`` (set
only after a ``GoalAuthorization`` exists).

The ``GoalExecutionEngine`` never reads or writes ``EvolutionProposal``
fields. All proposal construction is owned by this adapter. The engine
passes the adapter's output to ``ExecutionGateway`` blindly.

Pure logic. No infrastructure. No AI.
"""

from datetime import datetime

from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
    Weakness,
)
from atlas.goals.execution_models import ExecutionAction, GoalAuthorization


class ExecutionRequestAdapter:
    """
    Builds a goal-derived ``EvolutionProposal`` for ``ExecutionGateway``.

    The adapter is the single place that knows how to map a generic
    ``ExecutionAction`` + ``GoalAuthorization`` into the concrete request
    form the gateway requires. When future phases add new scopes or
    request types, only this adapter changes.

    Deterministic: the same inputs always produce the same proposal.
    """

    @staticmethod
    def to_gateway_request(
        action: ExecutionAction,
        authorization: GoalAuthorization,
    ) -> EvolutionProposal:
        """
        Build a goal-derived EvolutionProposal ready for ExecutionGateway.

        The proposal:
          - proposal_id = "GOALX-" + action.goal_id
          - title derived from action payload
          - plan.target_components = ["goal_execution"]
          - status = APPROVED (authorization already verified)
          - scope is ``UNKNOWN`` by construction, so governance at
            ADMINISTRATIVE level passes trivially.

        Args:
            action: The generic execution envelope.
            authorization: The verified GoalAuthorization.

        Returns:
            An EvolutionProposal whose status is APPROVED.
        """
        goal_id = action.goal_id
        proposal_id = f"GOALX-{goal_id}"
        title = action.payload.get("description", f"Execute goal {goal_id}")[:200]
        description = action.payload.get("description", "")
        category = action.context.get("category", "unknown")

        # Minimal plan with a single weakness that represents this goal.
        weakness = Weakness(
            area="goal_execution",
            description=description,
            severity=ImprovementPriority.MEDIUM,
        )

        plan = ImprovementPlan(
            plan_id=f"plan-{proposal_id}",
            title=title,
            description=description,
            priority=ImprovementPriority.MEDIUM,
            weaknesses=[weakness],
            expected_benefit="Goal execution via ToolEngine",
            complexity_estimate="low",
            target_components=["goal_execution"],
        )

        return EvolutionProposal(
            proposal_id=proposal_id,
            title=title,
            summary=f"Goal execution: {title[:80]}",
            rationale=(f"User-authorized goal execution. "
                       f"Category: {category}. "
                       f"Authorization: {authorization.authorized_by}"),
            expected_benefit="Execution of prioritized improvement goal",
            risks="Execution bounded by ToolEngine safety; no self-modification",
            impact_analysis="Administrative: records outcome, no system changes",
            implementation_approach="ToolEngine.fulfill() via ToolExecutionActionBinder",
            plan=plan,
            status=ProposalStatus.APPROVED,
            metadata={
                "goal_id": goal_id,
                "action_id": action.action_id,
                "authorized_by": authorization.authorized_by,
                "authorization_comment": authorization.comment,
                "strategy_key": authorization.strategy_key,
                "strategy_name": authorization.strategy_name,
                "planning_context_version": authorization.planning_context_version,
            },
        )