"""
Phase 13.4 — Evolution Execution Gateway Tests.

Tests that the EvolutionExecutionGateway:
  - evaluates proposals with RuleEngine before execution
  - refuses execution when governance rejects
  - never mutates proposal status on refusal
  - never calls EvolutionExecutionEngine when governance denies
  - delegates governance-approved proposals unchanged to the engine
  - fails CLOSED when RuleEngine is missing
  - degrades gracefully when EvolutionMemory is missing

Pure logic tests. No AI. No infrastructure. No storage.
"""

from unittest.mock import ANY, MagicMock

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.execution_engine import EvolutionExecutionEngine
from atlas.evolution.execution_gateway import EvolutionExecutionGateway
from atlas.evolution.governance.rule_engine import RuleEngine
from atlas.evolution.models import (
    ApprovalRequest,
    EvolutionProposal,
    ExecutionLevel,
    GatewayExecutionResult,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_proposal(
    proposal_id="PROP-001",
    status=ProposalStatus.APPROVED,
    components=None,
):
    """Create a test EvolutionProposal targeting the given components."""
    plan = ImprovementPlan(
        plan_id="IMP-001",
        title="Test Plan",
        description="A test improvement plan",
        priority=ImprovementPriority.LOW,
        target_components=components or ["runtime"],
    )
    return EvolutionProposal(
        proposal_id=proposal_id,
        title="Test Proposal",
        summary="A test proposal for testing",
        rationale="This change is needed for testing.",
        expected_benefit="Better testability.",
        risks="Low risk.",
        impact_analysis="Affects test components.",
        implementation_approach="1. Test. 2. Verify.",
        plan=plan,
        status=status,
    )


def make_approval_request(proposal_id="PROP-001"):
    """Create a test ApprovalRequest linked to a proposal."""
    return ApprovalRequest(
        request_id="APPR-001",
        proposal_id=proposal_id,
        title="Test Approval",
        description="Test description",
        rationale="Test rationale",
        risks="Test risks",
        expected_benefit="Test benefit",
    )


def make_gateway(
    rule_engine=None,
    execution_engine=None,
    evolution_memory=None,
    execution_level=ExecutionLevel.ADMINISTRATIVE,
):
    """Create an EvolutionExecutionGateway with test defaults."""
    if execution_engine is None:
        execution_engine = EvolutionExecutionEngine(
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
        )
    if rule_engine is None:
        rule_engine = RuleEngine()
    return EvolutionExecutionGateway(
        execution_engine=execution_engine,
        rule_engine=rule_engine,
        evolution_memory=evolution_memory,
        current_execution_level=execution_level,
    )


def approve_proposal(
    proposal: EvolutionProposal,
    request: ApprovalRequest,
) -> EvolutionProposal:
    """Drive a proposal through ApprovalManager to APPROVED status."""
    manager = ApprovalManager()
    manager.approve(request)
    manager.update_proposal_from_decision(proposal, request)
    return proposal


# ---------------------------------------------------------------------------
# Test: Gateway construction and defaults
# ---------------------------------------------------------------------------


class TestGatewayConstruction:

    def test_default_execution_level(self):
        """Gateway defaults to ADMINISTRATIVE level."""
        gateway = make_gateway()
        assert gateway.execution_level == ExecutionLevel.ADMINISTRATIVE

    def test_custom_execution_level(self):
        """Gateway accepts a custom execution level."""
        gateway = make_gateway(execution_level=ExecutionLevel.SELF_CONFIG)
        assert gateway.execution_level == ExecutionLevel.SELF_CONFIG

    def test_properties_reflect_injected_deps(self):
        """Properties return the injected dependencies."""
        engine = EvolutionExecutionEngine()
        rules = RuleEngine()
        memory = EvolutionMemory()
        gateway = EvolutionExecutionGateway(
            execution_engine=engine,
            rule_engine=rules,
            evolution_memory=memory,
        )
        assert gateway.execution_engine is engine
        assert gateway.rule_engine is rules
        assert gateway.evolution_memory is memory

    def test_set_execution_level_updates(self):
        """set_execution_level changes the active level."""
        gateway = make_gateway()
        gateway.set_execution_level(ExecutionLevel.INFORMATION)
        assert gateway.execution_level == ExecutionLevel.INFORMATION


# ---------------------------------------------------------------------------
# Test: Deterministic evaluation through evaluate()
# ---------------------------------------------------------------------------


class TestDeterministicEvaluation:

    def test_evaluate_is_side_effect_free(self):
        """evaluate() does not mutate the proposal status."""
        proposal = make_proposal(components=["code"])
        gateway = make_gateway()

        gateway.evaluate(proposal)

        assert proposal.status == ProposalStatus.APPROVED

    def test_evaluate_same_input_same_decision(self):
        """The same proposal always yields the same decision."""
        gateway = make_gateway()
        proposal = make_proposal(components=["memory"])

        first = gateway.evaluate(proposal)
        second = gateway.evaluate(proposal)

        assert first.approved == second.approved
        assert first.reason == second.reason
        assert first.violated_rules == second.violated_rules

    def test_evaluate_without_rule_engine_fails_closed(self):
        """Missing RuleEngine yields a fail-closed denial."""
        gateway = EvolutionExecutionGateway(
            execution_engine=EvolutionExecutionEngine(),
        )

        decision = gateway.evaluate(make_proposal())

        assert decision.approved is False
        assert "GATEWAY-FAIL-CLOSED" in decision.violated_rules


# ---------------------------------------------------------------------------
# Test: Governance denials by scope at ADMINISTRATIVE level
# ---------------------------------------------------------------------------


class TestGovernanceDenials:

    def test_identity_rejection(self):
        """Identity-scope proposal is refused at ADMINISTRATIVE level (GOV-001)."""
        gateway = make_gateway()
        proposal = make_proposal(components=["identity"])

        result = gateway.execute(proposal)

        assert result.success is False
        assert result.status == "REFUSED"
        assert result.governance_decision.approved is False
        assert any("GOV-001" in r for r in result.governance_decision.violated_rules)

    def test_config_rejection(self):
        """Config-scope proposal is refused at ADMINISTRATIVE level (GOV-003)."""
        gateway = make_gateway()
        proposal = make_proposal(components=["config"])

        result = gateway.execute(proposal)

        assert result.success is False
        assert result.status == "REFUSED"
        assert any("GOV-003" in r for r in result.governance_decision.violated_rules)

    def test_code_rejection(self):
        """Code-scope proposal is refused at ADMINISTRATIVE level (GOV-002)."""
        gateway = make_gateway()
        proposal = make_proposal(components=["code"])

        result = gateway.execute(proposal)

        assert result.success is False
        assert result.status == "REFUSED"
        assert any("GOV-002" in r for r in result.governance_decision.violated_rules)

    def test_memory_rejection(self):
        """Memory-scope proposal is refused at ADMINISTRATIVE level (GOV-004)."""
        gateway = make_gateway()
        proposal = make_proposal(components=["memory"])

        result = gateway.execute(proposal)

        assert result.success is False
        assert result.status == "REFUSED"
        assert any("GOV-004" in r for r in result.governance_decision.violated_rules)

    def test_memory_allowed_at_information_level(self):
        """Memory-scope proposal executes at INFORMATION level."""
        gateway = make_gateway(execution_level=ExecutionLevel.INFORMATION)
        proposal = make_proposal(components=["memory"])

        result = gateway.execute(proposal)

        assert result.success is True
        assert result.status == ProposalStatus.IMPLEMENTED.name

    def test_unknown_scope_approved(self):
        """Unknown-scope proposal executes at ADMINISTRATIVE level."""
        gateway = make_gateway()
        proposal = make_proposal(components=["runtime"])

        result = gateway.execute(proposal)

        assert result.success is True
        assert result.status == ProposalStatus.IMPLEMENTED.name


# ---------------------------------------------------------------------------
# Test: Successful delegation to the execution engine
# ---------------------------------------------------------------------------


class TestSuccessfulDelegation:

    def test_engine_executed_for_approved_proposal(self):
        """Governance-approved proposal delegates to the engine."""
        gateway = make_gateway()
        proposal = make_proposal(components=["runtime"])

        result = gateway.execute(proposal)

        assert result.success is True
        assert result.status == ProposalStatus.IMPLEMENTED.name
        assert proposal.status == ProposalStatus.IMPLEMENTED
        assert result.governance_decision.approved is True

    def test_execution_record_id_passed_through(self):
        """Engine record_id is surfaced in the gateway result."""
        gateway = make_gateway()
        proposal = make_proposal(components=["runtime"])

        result = gateway.execute(proposal)

        assert result.record_id.startswith("EVR-")

    def test_latest_experience_id_forwards_to_engine(self):
        """latest_experience_id is forwarded to the engine."""
        engine = MagicMock()
        result_engine = MagicMock()
        result_engine.success = True
        result_engine.proposal_id = "PROP-001"
        result_engine.status = "IMPLEMENTED"
        result_engine.record_id = "EVR-1"
        result_engine.tracked_goal_id = ""
        result_engine.error = ""
        engine.execute.return_value = result_engine
        gateway = EvolutionExecutionGateway(
            execution_engine=engine,
            rule_engine=RuleEngine(),
        )

        gateway.execute(make_proposal(components=["runtime"]), latest_experience_id="EXP-1")

        engine.execute.assert_called_once_with(
            proposal=ANY,
            latest_experience_id="EXP-1",
        )


# ---------------------------------------------------------------------------
# Test: Refusal audit records
# ---------------------------------------------------------------------------


class TestRefusalAuditRecord:

    def test_refusal_stores_record(self):
        """Governance refusal stores a 'refusal' record in EvolutionMemory."""
        memory = EvolutionMemory()
        gateway = make_gateway(evolution_memory=memory)
        proposal = make_proposal(components=["code"])

        gateway.execute(proposal)

        assert memory.record_count == 1
        record = memory.get_records(1)[0]
        assert record.event_type == "refusal"
        assert record.related_ids == ["PROP-001"]
        assert record.metadata["execution_level"] == "ADMINISTRATIVE"
        assert any("GOV-002" in r for r in record.metadata["violated_rules"])

    def test_refusal_record_id_in_result(self):
        """The refusal record ID is returned in the result."""
        memory = EvolutionMemory()
        gateway = make_gateway(evolution_memory=memory)
        proposal = make_proposal(components=["code"])

        result = gateway.execute(proposal)

        assert result.record_id.startswith("GWR-")

    def test_refusal_without_memory_skips_persistence(self):
        """Missing EvolutionMemory skips persistence but still refuses."""
        gateway = make_gateway(evolution_memory=None)
        proposal = make_proposal(components=["code"])

        result = gateway.execute(proposal)

        assert result.success is False
        assert result.status == "REFUSED"
        assert result.record_id == ""


# ---------------------------------------------------------------------------
# Test: Proposal state preservation on refusal
# ---------------------------------------------------------------------------


class TestProposalStatePreservation:

    def test_refusal_does_not_mutate_proposal(self):
        """Refused proposals keep their APPROVED status and metadata."""
        proposal = make_proposal(components=["identity"])
        original_metadata = dict(proposal.metadata)
        gateway = make_gateway()

        gateway.execute(proposal)

        assert proposal.status == ProposalStatus.APPROVED
        assert proposal.metadata == original_metadata

    def test_refusal_does_not_call_engine(self):
        """EvolutionExecutionEngine is never called on refusal."""
        engine = MagicMock()
        gateway = EvolutionExecutionGateway(
            execution_engine=engine,
            rule_engine=RuleEngine(),
        )
        proposal = make_proposal(components=["identity"])

        gateway.execute(proposal)

        engine.execute.assert_not_called()

    def test_refusal_creates_no_tracked_goal(self):
        """Refusal results carry no tracked_goal_id."""
        gateway = make_gateway(
            evolution_memory=EvolutionMemory(),
        )
        proposal = make_proposal(components=["code"])

        result = gateway.execute(proposal)

        assert result.tracked_goal_id == ""


# ---------------------------------------------------------------------------
# Test: Fail-closed and missing dependencies
# ---------------------------------------------------------------------------


class TestFailClosed:

    def test_missing_rule_engine_refuses(self):
        """Missing RuleEngine fails CLOSED — execution is refused."""
        gateway = EvolutionExecutionGateway(
            execution_engine=EvolutionExecutionEngine(),
        )
        proposal = make_proposal(components=["runtime"])

        result = gateway.execute(proposal)

        assert result.success is False
        assert result.status == "REFUSED"
        assert "RuleEngine" in result.error

    def test_missing_rule_engine_never_calls_engine(self):
        """Missing RuleEngine blocks the engine entirely."""
        engine = MagicMock()
        gateway = EvolutionExecutionGateway(execution_engine=engine)

        gateway.execute(make_proposal())

        engine.execute.assert_not_called()

    def test_missing_execution_engine_returns_error(self):
        """Missing EvolutionExecutionEngine returns an error result."""
        gateway = EvolutionExecutionGateway(
            execution_engine=None,
            rule_engine=RuleEngine(),
        )
        proposal = make_proposal(components=["runtime"])

        result = gateway.execute(proposal)

        assert result.success is False
        assert "EvolutionExecutionEngine" in result.error

    def test_non_approved_proposal_rejected(self):
        """Non-APPROVED proposals return an error before governance."""
        gateway = make_gateway()
        proposal = make_proposal(
            components=["runtime"],
            status=ProposalStatus.PENDING_APPROVAL,
        )

        result = gateway.execute(proposal)

        assert result.success is False
        assert "must be APPROVED" in result.error

    def test_missing_memory_graceful_degradation(self):
        """Approved execution works without EvolutionMemory."""
        gateway = make_gateway(evolution_memory=None)
        proposal = make_proposal(components=["runtime"])

        result = gateway.execute(proposal)

        assert result.success is True
        assert result.status == ProposalStatus.IMPLEMENTED.name


# ---------------------------------------------------------------------------
# Test: GatewayExecutionResult model
# ---------------------------------------------------------------------------


class TestGatewayExecutionResult:

    def test_defaults(self):
        """GatewayExecutionResult defaults are empty/safe."""
        result = GatewayExecutionResult(success=True)
        assert result.proposal_id == ""
        assert result.status == ""
        assert result.governance_decision is None
        assert result.record_id == ""
        assert result.tracked_goal_id == ""
        assert result.error == ""

    def test_full_construction(self):
        """GatewayExecutionResult carries all fields."""
        decision = RuleEngine().evaluate(make_proposal(components=["runtime"]))
        result = GatewayExecutionResult(
            success=True,
            proposal_id="PROP-001",
            status="IMPLEMENTED",
            governance_decision=decision,
            record_id="EVR-1",
            tracked_goal_id="TRK-1",
        )
        assert result.success is True
        assert result.governance_decision is decision
        assert result.record_id == "EVR-1"


# ---------------------------------------------------------------------------
# Test: Full lifecycle through ApprovalManager and Gateway
# ---------------------------------------------------------------------------


class TestFullLifecycle:

    def test_identity_proposal_full_cycle_is_refused(self):
        """An approved identity proposal is refused by the gateway."""
        proposal = make_proposal(components=["identity"])
        request = make_approval_request()
        approve_proposal(proposal, request)
        assert proposal.status == ProposalStatus.APPROVED

        gateway = make_gateway()
        result = gateway.execute(proposal)

        assert result.success is False
        assert result.status == "REFUSED"
        assert proposal.status == ProposalStatus.APPROVED

    def test_runtime_proposal_full_cycle_executes(self):
        """An approved runtime proposal executes through the gateway."""
        proposal = make_proposal(components=["runtime"])
        request = make_approval_request()
        approve_proposal(proposal, request)
        assert proposal.status == ProposalStatus.APPROVED

        gateway = make_gateway()
        result = gateway.execute(proposal)

        assert result.success is True
        assert result.status == ProposalStatus.IMPLEMENTED.name
        assert proposal.status == ProposalStatus.IMPLEMENTED


# ---------------------------------------------------------------------------
# Test: Atlas kernel integration wiring
# ---------------------------------------------------------------------------


class TestAtlasIntegration:

    def test_gateway_created_and_registered_in_container(self):
        """Atlas.start() creates the gateway and registers it."""
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()

            gateway = atlas.container.get("execution_gateway")
            assert gateway is not None
            assert isinstance(gateway, EvolutionExecutionGateway)

            assert atlas.execution_gateway is gateway
            assert atlas.rule_engine is gateway.rule_engine
            assert atlas.execution_engine is gateway.execution_engine
        finally:
            atlas.shutdown()

    def test_gateway_functions_after_atlas_start(self):
        """The wired gateway governs execution correctly."""
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()

            gateway = atlas.container.get("execution_gateway")
            proposal = make_proposal(components=["identity"])
            request = make_approval_request()
            approve_proposal(proposal, request)

            result = gateway.execute(proposal)

            assert result.success is False
            assert result.status == "REFUSED"
            assert proposal.status == ProposalStatus.APPROVED
        finally:
            atlas.shutdown()

    def test_shutdown_cleans_up_gateway(self):
        """Atlas.shutdown() nullifies the gateway and rule engine."""
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        atlas.shutdown()

        assert atlas._execution_gateway is None
        assert atlas._rule_engine is None

    def test_shutdown_removes_gateway_from_container(self):
        """Container is cleared on shutdown — gateway no longer present."""
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        atlas.shutdown()

        assert atlas.container.names() == []

    def test_rule_engine_and_gateway_registered_as_components(self):
        """ComponentRegistry observes the new components after start."""
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()

            registry = atlas.component_registry
            names = registry.get_all_component_names()
            assert "execution_gateway" in names
            assert "rule_engine" in names

            gateway_meta = registry.get("execution_gateway")
            assert gateway_meta is not None
            assert gateway_meta.status.name == "HEALTHY"
        finally:
            atlas.shutdown()
