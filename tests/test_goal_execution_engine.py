"""
Phase 15 — Goal Execution Engine Tests

Covers: ActionFactory, ExecutionRequestAdapter, ToolExecutionActionBinder,
GoalExecutionEngine (activate, settle, execute), lifecycle transitions,
fail-closed behaviour, authorization guards, gateway refusal, and
GoalExecutionRecord persistence.
"""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from atlas.goals.execution_models import (
    ActionType,
    ExecutionAction,
    ExecutionOutcome,
    GoalAuthorization,
    GoalExecutionRecord,
    GoalExecutorResult,
)
from atlas.goals.execution_request_adapter import ExecutionRequestAdapter
from atlas.goals.goal_execution_engine import ActionFactory, GoalExecutionEngine
from atlas.goals.models import (
    GoalCategory,
    GoalPriority,
    GoalStatus,
    ImprovementGoal,
)
from atlas.goals.goal_repository import GoalRepository
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
    GatewayExecutionResult,
    ExecutionResult,
)
from atlas.tools.models import ToolRequest, ToolResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_goal(
    goal_id: str = "GOAL-001",
    status: GoalStatus = GoalStatus.RECOMMENDED,
    category: GoalCategory = GoalCategory.TOOLING,
    confidence: float = 0.8,
) -> ImprovementGoal:
    return ImprovementGoal(
        goal_id=goal_id,
        title=f"Test Goal {goal_id}",
        description=f"Description for {goal_id}",
        category=category,
        priority=GoalPriority.HIGH,
        status=status,
        evidence_count=5,
        confidence=confidence,
    )


def _make_auth(goal_id: str = "GOAL-001",
               strategy_key: str = "test_strategy",
               strategy_name: str = "Test Strategy",
               planning_context_version: str = "2026-01-01T00:00:00") -> GoalAuthorization:
    return GoalAuthorization(
        goal_id=goal_id,
        authorized_by="user:cli",
        comment="test",
        strategy_key=strategy_key,
        strategy_name=strategy_name,
        planning_context_version=planning_context_version,
    )


def _make_fake_gateway(approve: bool = True, error: str = "") -> MagicMock:
    gw = MagicMock()
    result = MagicMock(spec=GatewayExecutionResult)
    result.success = approve
    result.error = error
    result.record_id = "GW-REC-001"
    result.tracked_goal_id = ""
    gw.execute.return_value = result
    return gw


def _make_fake_tool_engine(success: bool = True) -> MagicMock:
    te = MagicMock()
    te.fulfill.return_value = ToolResult(
        tool_name="echo",
        success=success,
        output={"result": "ok"},
        error="" if success else "tool failure",
        execution_time_ms=42.0,
    )
    return te


# ---------------------------------------------------------------------------
# ActionFactory
# ---------------------------------------------------------------------------


class TestActionFactory(unittest.TestCase):
    def test_build_creates_execution_action(self):
        goal = _make_goal()
        auth = _make_auth()
        action = ActionFactory.build(goal, auth)
        self.assertIsInstance(action, ExecutionAction)
        self.assertEqual(action.goal_id, goal.goal_id)
        self.assertEqual(action.action_type, ActionType.TOOL_INVOCATION)
        self.assertIn(goal.description, action.payload["description"])
        self.assertEqual(action.context["category"], goal.category.name)
        self.assertGreater(action.confidence, 0.0)

    def test_build_action_id_is_unique(self):
        goal = _make_goal()
        auth = _make_auth()
        # action_id includes timestamp to second precision;
        # advance a second to guarantee uniqueness.
        from datetime import datetime
        a1 = ActionFactory.build(goal, auth)
        # Patch datetime.now so the second timestamp advances
        with patch("atlas.goals.goal_execution_engine.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 8, 1, 12, 0, 1)
            mock_dt.strftime = datetime.strftime
            a2 = ActionFactory.build(goal, auth)
        self.assertNotEqual(a1.action_id, a2.action_id)

    def test_build_preserves_strategy_provenance(self):
        goal = _make_goal()
        auth = _make_auth(strategy_key="sk-001")
        action = ActionFactory.build(goal, auth)
        self.assertEqual(action.context["strategy_key"], "sk-001")


# ---------------------------------------------------------------------------
# ExecutionRequestAdapter
# ---------------------------------------------------------------------------


class TestExecutionRequestAdapter(unittest.TestCase):
    def test_to_gateway_request_creates_approved_proposal(self):
        goal = _make_goal()
        auth = _make_auth()
        action = ActionFactory.build(goal, auth)
        proposal = ExecutionRequestAdapter.to_gateway_request(action, auth)
        self.assertIsInstance(proposal, EvolutionProposal)
        self.assertEqual(proposal.status, ProposalStatus.APPROVED)
        self.assertIn("GOALX-", proposal.proposal_id)
        self.assertEqual(proposal.plan.target_components, ["goal_execution"])

    def test_to_gateway_request_includes_auth_metadata(self):
        goal = _make_goal()
        auth = _make_auth(strategy_key="sk-002")
        action = ActionFactory.build(goal, auth)
        proposal = ExecutionRequestAdapter.to_gateway_request(action, auth)
        self.assertEqual(proposal.metadata["goal_id"], goal.goal_id)
        self.assertEqual(proposal.metadata["strategy_key"], "sk-002")
        self.assertEqual(proposal.metadata["planning_context_version"], auth.planning_context_version)

    def test_proposal_id_is_derived_from_goal_id(self):
        goal = _make_goal("GOAL-ABC")
        auth = _make_auth("GOAL-ABC")
        action = ActionFactory.build(goal, auth)
        proposal = ExecutionRequestAdapter.to_gateway_request(action, auth)
        self.assertEqual(proposal.proposal_id, "GOALX-GOAL-ABC")


# ---------------------------------------------------------------------------
# ToolExecutionActionBinder
# ---------------------------------------------------------------------------


class TestToolExecutionActionBinder(unittest.TestCase):
    def setUp(self):
        from atlas.tools.execution_action_binder import ToolExecutionActionBinder
        self.tool_engine = _make_fake_tool_engine()
        self.binder = ToolExecutionActionBinder(tool_engine=self.tool_engine)

    def test_binder_declares_tool_invocation_type(self):
        self.assertEqual(self.binder.action_type, ActionType.TOOL_INVOCATION)

    def test_bind_success(self):
        goal = _make_goal()
        auth = _make_auth()
        action = ActionFactory.build(goal, auth)
        result = self.binder.bind(action)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "echo")

    def test_bind_tool_failure(self):
        from atlas.tools.execution_action_binder import ToolExecutionActionBinder
        te = _make_fake_tool_engine(success=False)
        binder = ToolExecutionActionBinder(tool_engine=te)
        goal = _make_goal()
        auth = _make_auth()
        action = ActionFactory.build(goal, auth)
        result = binder.bind(action)
        self.assertFalse(result.success)
        self.assertEqual(result.error, "tool failure")

    def test_bind_no_tool_engine(self):
        from atlas.tools.execution_action_binder import ToolExecutionActionBinder
        binder = ToolExecutionActionBinder(tool_engine=None)
        goal = _make_goal()
        auth = _make_auth()
        action = ActionFactory.build(goal, auth)
        result = binder.bind(action)
        self.assertFalse(result.success)
        self.assertIn("not available", result.error)


# ---------------------------------------------------------------------------
# GoalExecutionEngine — Activation
# ---------------------------------------------------------------------------


class TestGoalExecutionEngineActivation(unittest.TestCase):
    def setUp(self):
        self.repo = GoalRepository()
        self.repo.store_goal(_make_goal())
        self.engine = GoalExecutionEngine(repository=self.repo)

    def test_activate_recommended_goal(self):
        result = self.engine.activate("GOAL-001")
        self.assertTrue(result.success)
        self.assertEqual(result.status, GoalStatus.APPROVED.name)

    def test_activate_stores_authorization(self):
        self.engine.activate("GOAL-001")
        auth = self.repo.get_authorization("GOAL-001")
        self.assertIsNotNone(auth)
        self.assertEqual(auth.authorized_by, "user:cli")

    def test_activate_transitions_to_approved(self):
        self.engine.activate("GOAL-001")
        goal = self.repo.get_goal("GOAL-001")
        self.assertEqual(goal.status, GoalStatus.APPROVED)

    def test_activate_nonexistent_goal(self):
        result = self.engine.activate("GOAL-NOPE")
        self.assertFalse(result.success)
        self.assertIn("not found", result.error or "")

    def test_activate_invalid_state(self):
        self.repo.store_goal(_make_goal("GOAL-002", status=GoalStatus.COMPLETED))
        result = self.engine.activate("GOAL-002")
        self.assertFalse(result.success)
        self.assertIn("Cannot activate", result.error or "")

    def test_activate_comment(self):
        result = self.engine.activate("GOAL-001", comment="ship it")
        self.assertTrue(result.success)
        auth = self.repo.get_authorization("GOAL-001")
        self.assertEqual(auth.comment, "ship it")

    def test_reactivate_failed_goal(self):
        self.repo.store_goal(_make_goal("GOAL-FAIL", status=GoalStatus.FAILED))
        result = self.engine.activate("GOAL-FAIL")
        self.assertTrue(result.success)


# ---------------------------------------------------------------------------
# GoalExecutionEngine — Execution (fail-closed & lifecycle)
# ---------------------------------------------------------------------------


class TestGoalExecutionEngineExecution(unittest.TestCase):
    def setUp(self):
        self.repo = GoalRepository()
        self.repo.store_goal(_make_goal())
        self.repo.store_authorization(_make_auth())
        # Transition goal to APPROVED
        goal = self.repo.get_goal("GOAL-001")
        self.repo.store_goal(ImprovementGoal(
            goal_id=goal.goal_id,
            title=goal.title,
            description=goal.description,
            category=goal.category,
            priority=goal.priority,
            status=GoalStatus.APPROVED,
            evidence_count=goal.evidence_count,
            confidence=goal.confidence,
            proposed_at=goal.proposed_at,
        ))


class TestGoalExecutionEngineFailClosed(unittest.TestCase):
    def test_settle_no_approved_goals_returns_none(self):
        engine = GoalExecutionEngine()
        result = engine.settle()
        self.assertIsNone(result)

    def test_execute_no_authorization_refuses(self):
        repo = GoalRepository()
        repo.store_goal(_make_goal(status=GoalStatus.APPROVED))
        engine = GoalExecutionEngine(repository=repo,
                                      execution_gateway=_make_fake_gateway())
        result = engine.settle()
        self.assertIsNotNone(result)
        self.assertFalse(result.success)
        self.assertIn("Authorization", result.error or "")

    def test_execute_non_user_authorization_refuses(self):
        repo = GoalRepository()
        repo.store_goal(_make_goal(status=GoalStatus.APPROVED))
        repo.store_authorization(GoalAuthorization(
            goal_id="GOAL-001",
            authorized_by="system",
        ))
        engine = GoalExecutionEngine(repository=repo,
                                      execution_gateway=_make_fake_gateway())
        result = engine.settle()
        self.assertIsNotNone(result)
        self.assertFalse(result.success)
        self.assertIn("not 'user:cli'", result.error or "")

    def test_execute_no_gateway_refuses(self):
        repo = GoalRepository()
        repo.store_goal(_make_goal(status=GoalStatus.APPROVED))
        repo.store_authorization(_make_auth())
        engine = GoalExecutionEngine(repository=repo)
        result = engine.settle()
        self.assertIsNotNone(result)
        self.assertFalse(result.success)
        self.assertIn("Gateway", result.error or "")


class TestGoalExecutionEngineGatewayRefusal(unittest.TestCase):
    def setUp(self):
        self.repo = GoalRepository()
        self.repo.store_goal(_make_goal(status=GoalStatus.APPROVED))
        self.repo.store_authorization(_make_auth())

    def test_gateway_refusal_records_refusal(self):
        gw = _make_fake_gateway(approve=False, error="governance says no")
        engine = GoalExecutionEngine(repository=self.repo, execution_gateway=gw)
        result = engine.settle()
        self.assertIsNotNone(result)
        self.assertFalse(result.success)
        self.assertFalse(result.success)
        # Gateway refusal transitions goal to FAILED before result is built,
        # so the result carries the goal's FAILED status
        goal = self.repo.get_goal("GOAL-001")
        self.assertEqual(goal.status, GoalStatus.FAILED)

    def test_gateway_refusal_transitions_to_failed(self):
        gw = _make_fake_gateway(approve=False)
        engine = GoalExecutionEngine(repository=self.repo, execution_gateway=gw)
        engine.settle()
        goal = self.repo.get_goal("GOAL-001")
        self.assertEqual(goal.status, GoalStatus.FAILED)


# ---------------------------------------------------------------------------
# GoalExecutionEngine — Full execution (gateway + binder + tool)
# ---------------------------------------------------------------------------


class TestGoalExecutionEngineFullExecution(unittest.TestCase):
    def setUp(self):
        self.repo = GoalRepository()
        self.repo.store_goal(_make_goal(status=GoalStatus.APPROVED))
        self.repo.store_authorization(_make_auth())

        self.gateway = _make_fake_gateway(approve=True)

        from atlas.goals.execution_action_binders import ExecutionActionBinderRegistry
        from atlas.tools.execution_action_binder import ToolExecutionActionBinder
        self.binder_registry = ExecutionActionBinderRegistry()
        self.binder_registry.register(
            ToolExecutionActionBinder(tool_engine=_make_fake_tool_engine(success=True))
        )

        self.engine = GoalExecutionEngine(
            repository=self.repo,
            execution_gateway=self.gateway,
            binder_registry=self.binder_registry,
        )

    def test_full_execution_completes(self):
        result = self.engine.settle()
        self.assertIsNotNone(result)
        self.assertTrue(result.success)

    def test_full_execution_transitions_to_completed(self):
        self.engine.settle()
        goal = self.repo.get_goal("GOAL-001")
        self.assertEqual(goal.status, GoalStatus.COMPLETED)

    def test_full_execution_stores_record(self):
        self.engine.settle()
        records = self.repo.get_execution_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].goal_id, "GOAL-001")

    def test_record_carries_strategy_provenance(self):
        self.engine.settle()
        records = self.repo.get_execution_records()
        self.assertEqual(records[0].strategy_key, "test_strategy")
        self.assertEqual(records[0].planning_context_version, "2026-01-01T00:00:00")

    def test_tool_failure_transitions_to_failed(self):
        from atlas.goals.execution_action_binders import ExecutionActionBinderRegistry
        from atlas.tools.execution_action_binder import ToolExecutionActionBinder
        reg = ExecutionActionBinderRegistry()
        reg.register(ToolExecutionActionBinder(tool_engine=_make_fake_tool_engine(success=False)))
        engine = GoalExecutionEngine(
            repository=self.repo,
            execution_gateway=self.gateway,
            binder_registry=reg,
        )
        engine.settle()
        goal = self.repo.get_goal("GOAL-001")
        self.assertEqual(goal.status, GoalStatus.FAILED)

    def test_completed_record_has_effectiveness_1(self):
        self.engine.settle()
        records = self.repo.get_execution_records()
        self.assertEqual(records[0].effectiveness_proxy, 1.0)
        self.assertEqual(records[0].outcome, ExecutionOutcome.COMPLETED)

    def test_failed_record_has_effectiveness_0(self):
        from atlas.goals.execution_action_binders import ExecutionActionBinderRegistry
        from atlas.tools.execution_action_binder import ToolExecutionActionBinder
        reg = ExecutionActionBinderRegistry()
        reg.register(ToolExecutionActionBinder(tool_engine=_make_fake_tool_engine(success=False)))
        engine = GoalExecutionEngine(
            repository=self.repo,
            execution_gateway=self.gateway,
            binder_registry=reg,
        )
        engine.settle()
        records = engine.repository.get_execution_records()
        self.assertEqual(records[0].effectiveness_proxy, 0.0)
        self.assertEqual(records[0].outcome, ExecutionOutcome.FAILED)

    def test_no_binder_registered_refuses(self):
        engine = GoalExecutionEngine(
            repository=self.repo,
            execution_gateway=self.gateway,
            binder_registry=None,
        )
        result = engine.settle()
        self.assertIsNotNone(result)
        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# GoalExecutionEngine — settle() single-slot
# ---------------------------------------------------------------------------


class TestGoalExecutionEngineSettleSingleSlot(unittest.TestCase):
    def test_only_one_goal_per_settle(self):
        repo = GoalRepository()
        from atlas.tools.execution_action_binder import ToolExecutionActionBinder
        from atlas.goals.execution_action_binders import ExecutionActionBinderRegistry
        reg = ExecutionActionBinderRegistry()
        reg.register(ToolExecutionActionBinder(tool_engine=_make_fake_tool_engine()))

        for i in range(3):
            gid = f"GOAL-{i:03d}"
            repo.store_goal(_make_goal(gid))
            repo.store_authorization(_make_auth(gid))
            goal = repo.get_goal(gid)
            repo.store_goal(ImprovementGoal(
                goal_id=goal.goal_id,
                title=goal.title,
                description=goal.description,
                category=goal.category,
                priority=goal.priority,
                status=GoalStatus.APPROVED,
                evidence_count=goal.evidence_count,
                confidence=goal.confidence,
                proposed_at=goal.proposed_at,
            ))

        engine = GoalExecutionEngine(
            repository=repo,
            execution_gateway=_make_fake_gateway(),
            binder_registry=reg,
        )

        r1 = engine.settle()
        r2 = engine.settle()
        self.assertIsNotNone(r1)
        self.assertIsNotNone(r2)
        self.assertNotEqual(r1.goal_id, r2.goal_id)


# ---------------------------------------------------------------------------
# GoalExecutionEngine — no retries
# ---------------------------------------------------------------------------


class TestGoalExecutionEngineNoRetries(unittest.TestCase):
    def test_failed_goal_not_picked_up_again(self):
        repo = GoalRepository()
        repo.store_goal(_make_goal(status=GoalStatus.APPROVED))
        repo.store_authorization(_make_auth())
        gw = _make_fake_gateway(approve=False)
        engine = GoalExecutionEngine(repository=repo, execution_gateway=gw)
        engine.settle()
        # Failed goals are not APPROVED, so settle() returns None
        result = engine.settle()
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# ExecutionActionBinderRegistry
# ---------------------------------------------------------------------------


class TestExecutionActionBinderRegistry(unittest.TestCase):
    def setUp(self):
        from atlas.goals.execution_action_binders import ExecutionActionBinderRegistry
        self.reg = ExecutionActionBinderRegistry()

    def test_register_and_resolve(self):
        from atlas.tools.execution_action_binder import ToolExecutionActionBinder
        binder = ToolExecutionActionBinder(tool_engine=_make_fake_tool_engine())
        self.reg.register(binder)
        resolved = self.reg.resolve(ActionType.TOOL_INVOCATION)
        self.assertIs(resolved, binder)

    def test_double_register_raises(self):
        from atlas.tools.execution_action_binder import ToolExecutionActionBinder
        self.reg.register(ToolExecutionActionBinder(tool_engine=_make_fake_tool_engine()))
        with self.assertRaises(ValueError):
            self.reg.register(ToolExecutionActionBinder(tool_engine=_make_fake_tool_engine()))

    def test_resolve_unknown_returns_none(self):
        self.assertIsNone(self.reg.resolve(ActionType.TOOL_INVOCATION))

    def test_registered_types(self):
        from atlas.tools.execution_action_binder import ToolExecutionActionBinder
        self.reg.register(ToolExecutionActionBinder(tool_engine=_make_fake_tool_engine()))
        self.assertIn(ActionType.TOOL_INVOCATION, self.reg.registered_types)

    def test_clear(self):
        from atlas.tools.execution_action_binder import ToolExecutionActionBinder
        self.reg.register(ToolExecutionActionBinder(tool_engine=_make_fake_tool_engine()))
        self.reg.clear()
        self.assertEqual(self.reg.registered_types, [])


# ---------------------------------------------------------------------------
# GoalExecutionEngine — EvolutionRecord events
# ---------------------------------------------------------------------------


class TestGoalExecutionEngineEvents(unittest.TestCase):
    def test_evolution_records_stored_on_activation(self):
        repo = GoalRepository()
        repo.store_goal(_make_goal())
        ev_memory = MagicMock()
        engine = GoalExecutionEngine(
            repository=repo,
            evolution_memory=ev_memory,
        )
        engine.activate("GOAL-001")
        self.assertTrue(ev_memory.store_record.called)

    def test_evolution_records_stored_on_success(self):
        repo = GoalRepository()
        repo.store_goal(_make_goal(status=GoalStatus.APPROVED))
        repo.store_authorization(_make_auth())
        ev_memory = MagicMock()
        from atlas.goals.execution_action_binders import ExecutionActionBinderRegistry
        from atlas.tools.execution_action_binder import ToolExecutionActionBinder
        reg = ExecutionActionBinderRegistry()
        reg.register(ToolExecutionActionBinder(tool_engine=_make_fake_tool_engine()))
        engine = GoalExecutionEngine(
            repository=repo,
            execution_gateway=_make_fake_gateway(),
            binder_registry=reg,
            evolution_memory=ev_memory,
        )
        engine.settle()
        # Should have stored at least one event
        self.assertTrue(ev_memory.store_record.called)

    def test_evolution_records_stored_on_refusal(self):
        repo = GoalRepository()
        repo.store_goal(_make_goal(status=GoalStatus.APPROVED))
        repo.store_authorization(_make_auth())
        ev_memory = MagicMock()
        engine = GoalExecutionEngine(
            repository=repo,
            execution_gateway=_make_fake_gateway(approve=False),
            evolution_memory=ev_memory,
        )
        engine.settle()
        self.assertTrue(ev_memory.store_record.called)


if __name__ == "__main__":
    unittest.main()