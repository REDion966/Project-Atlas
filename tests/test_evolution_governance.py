"""
Phase 13.1 — Evolution Governance Foundation Tests.

Tests governance rules, constraint registry, and rule engine.
All tests verify that proposals are correctly evaluated against
explicit auditable governance constraints.

Pure logic tests. No AI. No infrastructure. No storage.
"""

import pytest

from atlas.evolution.models import (
    EvolutionProposal,
    ExecutionLevel,
    ImprovementPlan,
    ImprovementPriority,
)
from atlas.evolution.governance.models import (
    GovernanceDecision,
    GovernanceRule,
    ScopeType,
)
from atlas.evolution.governance.constraint_registry import ConstraintRegistry
from atlas.evolution.governance.rule_engine import RuleEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_proposal(
    title: str = "Test Proposal",
    components: list[str] | None = None,
) -> EvolutionProposal:
    """Create a minimal EvolutionProposal for testing."""
    plan = ImprovementPlan(
        plan_id="IMP-TEST",
        title=title,
        description="Test plan for governance validation.",
        priority=ImprovementPriority.LOW,
        target_components=components or ["runtime"],
    )
    return EvolutionProposal(
        proposal_id="PROP-TEST",
        title=title,
        summary="Test summary.",
        rationale="Test rationale.",
        expected_benefit="Test benefit.",
        risks="No risks.",
        impact_analysis="Minimal impact.",
        implementation_approach="Test approach.",
        plan=plan,
    )


# ---------------------------------------------------------------------------
# Test: ScopeType
# ---------------------------------------------------------------------------


class TestScopeType:

    def test_scope_type_has_expected_values(self):
        """All required ScopeType values exist."""
        assert ScopeType.CONFIG is not None
        assert ScopeType.MEMORY is not None
        assert ScopeType.KNOWLEDGE is not None
        assert ScopeType.CODE is not None
        assert ScopeType.IDENTITY is not None
        assert ScopeType.UNKNOWN is not None

    def test_scope_types_are_unique(self):
        """No duplicate scope type values."""
        values = [s.value for s in ScopeType]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# Test: GovernanceRule
# ---------------------------------------------------------------------------


class TestGovernanceRule:

    def test_create_rule_minimal(self):
        """Minimal GovernanceRule with only required fields."""
        rule = GovernanceRule(
            rule_id="GOV-001",
            description="Identity is protected.",
            scope=ScopeType.IDENTITY,
        )
        assert rule.rule_id == "GOV-001"
        assert rule.scope == ScopeType.IDENTITY
        assert rule.min_execution_level is None
        assert rule.forbidden is False

    def test_create_rule_with_level(self):
        """GovernanceRule with execution level requirement."""
        rule = GovernanceRule(
            rule_id="GOV-002",
            description="Code requires CODE_ARTIFACT level.",
            scope=ScopeType.CODE,
            min_execution_level=ExecutionLevel.CODE_ARTIFACT.value,
        )
        assert rule.min_execution_level == ExecutionLevel.CODE_ARTIFACT.value

    def test_create_rule_forbidden(self):
        """GovernanceRule with forbidden flag."""
        rule = GovernanceRule(
            rule_id="GOV-003",
            description="Dangerous change is forbidden.",
            scope=ScopeType.MEMORY,
            forbidden=True,
        )
        assert rule.forbidden is True

    def test_rule_is_frozen(self):
        """GovernanceRule is immutable after creation."""
        rule = GovernanceRule(
            rule_id="GOV-FROZEN",
            description="Immutable rule.",
            scope=ScopeType.IDENTITY,
        )
        with pytest.raises(AttributeError):
            rule.rule_id = "CHANGED"  # type: ignore


# ---------------------------------------------------------------------------
# Test: GovernanceDecision
# ---------------------------------------------------------------------------


class TestGovernanceDecision:

    def test_approved_decision(self):
        """Approved decision has no violated rules."""
        decision = GovernanceDecision(
            approved=True,
            reason="All checks passed.",
        )
        assert decision.approved is True
        assert decision.reason == "All checks passed."
        assert decision.violated_rules == []

    def test_rejected_decision(self):
        """Rejected decision includes violated rule IDs."""
        decision = GovernanceDecision(
            approved=False,
            reason="Violated governance rules.",
            violated_rules=["GOV-001: Identity requires AUTONOMOUS level."],
        )
        assert decision.approved is False
        assert len(decision.violated_rules) == 1

    def test_decision_is_frozen(self):
        """GovernanceDecision is immutable after creation."""
        decision = GovernanceDecision(
            approved=True,
            reason="Passed.",
        )
        with pytest.raises(AttributeError):
            decision.approved = False  # type: ignore


# ---------------------------------------------------------------------------
# Test: ConstraintRegistry
# ---------------------------------------------------------------------------


class TestConstraintRegistry:

    def test_default_rules_loaded(self):
        """ConstraintRegistry loads all 5 default rules on construction."""
        registry = ConstraintRegistry()
        assert registry.rule_count == 5

        rules = registry.get_rules()
        rule_ids = {r.rule_id for r in rules}
        assert "GOV-001" in rule_ids
        assert "GOV-002" in rule_ids
        assert "GOV-003" in rule_ids
        assert "GOV-004" in rule_ids

    def test_register_custom_rule(self):
        """Custom rules can be registered."""
        registry = ConstraintRegistry()
        rule = GovernanceRule(
            rule_id="GOV-CUSTOM",
            description="Custom test rule.",
            scope=ScopeType.UNKNOWN,
        )
        registry.register(rule)
        assert registry.rule_count == 6

        fetched = registry.get_rule("GOV-CUSTOM")
        assert fetched is not None
        assert fetched.description == "Custom test rule."

    def test_duplicate_rule_id_raises(self):
        """Registering a rule with an existing ID raises ValueError."""
        registry = ConstraintRegistry()
        rule = GovernanceRule(
            rule_id="GOV-001",
            description="Duplicate rule.",
            scope=ScopeType.CODE,
        )
        with pytest.raises(ValueError, match="already registered"):
            registry.register(rule)

    def test_get_rules_for_scope(self):
        """Rules are filtered correctly by scope."""
        registry = ConstraintRegistry()

        identity_rules = registry.get_rules_for_scope(ScopeType.IDENTITY)
        assert len(identity_rules) >= 1
        assert all(r.scope == ScopeType.IDENTITY for r in identity_rules)

        code_rules = registry.get_rules_for_scope(ScopeType.CODE)
        assert len(code_rules) >= 1
        assert all(r.scope == ScopeType.CODE for r in code_rules)

        # UNKNOWN scope has no default rules
        unknown_rules = registry.get_rules_for_scope(ScopeType.UNKNOWN)
        assert len(unknown_rules) == 0

    def test_get_nonexistent_rule_returns_none(self):
        """get_rule returns None for unknown rule IDs."""
        registry = ConstraintRegistry()
        assert registry.get_rule("GOV-NONEXIST") is None

    def test_clear_removes_all_rules(self):
        """clear() removes all rules without reloading defaults."""
        registry = ConstraintRegistry()
        assert registry.rule_count == 5

        registry.clear()
        assert registry.rule_count == 0
        assert registry.get_rules() == []

    def test_duplicate_rule_id_different_case(self):
        """Rule IDs are case-sensitive."""
        registry = ConstraintRegistry()
        registry.clear()

        rule1 = GovernanceRule(
            rule_id="GOV-TEST",
            description="Original rule.",
            scope=ScopeType.CODE,
        )
        rule2 = GovernanceRule(
            rule_id="gov-test",
            description="Different case rule.",
            scope=ScopeType.CONFIG,
        )
        registry.register(rule1)
        registry.register(rule2)
        assert registry.rule_count == 2


# ---------------------------------------------------------------------------
# Test: RuleEngine — Scope Detection
# ---------------------------------------------------------------------------


class TestScopeDetection:

    def test_identity_scope(self):
        """Target component 'identity' maps to IDENTITY scope."""
        scope = RuleEngine.classify_scope(["identity"])
        assert scope == ScopeType.IDENTITY

    def test_config_scope(self):
        """Target component 'config' maps to CONFIG scope."""
        scope = RuleEngine.classify_scope(["config"])
        assert scope == ScopeType.CONFIG

    def test_configuration_scope(self):
        """Target component 'configuration' maps to CONFIG scope."""
        scope = RuleEngine.classify_scope(["configuration"])
        assert scope == ScopeType.CONFIG

    def test_code_scope(self):
        """Target component 'code' maps to CODE scope."""
        scope = RuleEngine.classify_scope(["code"])
        assert scope == ScopeType.CODE

    def test_memory_scope(self):
        """Target component 'memory' maps to MEMORY scope."""
        scope = RuleEngine.classify_scope(["memory"])
        assert scope == ScopeType.MEMORY

    def test_knowledge_scope(self):
        """Target component 'knowledge' maps to KNOWLEDGE scope."""
        scope = RuleEngine.classify_scope(["knowledge"])
        assert scope == ScopeType.KNOWLEDGE

    def test_capability_scope(self):
        """Target component 'capability' maps to CAPABILITY scope."""
        scope = RuleEngine.classify_scope(["capability"])
        assert scope == ScopeType.CAPABILITY

    def test_capability_scope_mixed_components(self):
        """A proposal with 'capability' among other components maps to CAPABILITY."""
        scope = RuleEngine.classify_scope(["capability", "autonomy:capability"])
        assert scope == ScopeType.CAPABILITY

    def test_unknown_scope(self):
        """Unrecognized components map to UNKNOWN scope."""
        scope = RuleEngine.classify_scope(["runtime", "reasoning"])
        assert scope == ScopeType.UNKNOWN

    def test_empty_scope(self):
        """Empty target components map to UNKNOWN scope."""
        scope = RuleEngine.classify_scope([])
        assert scope == ScopeType.UNKNOWN

    def test_mixed_scope_order(self):
        """First matching keyword determines scope."""
        scope = RuleEngine.classify_scope(["runtime", "identity", "code"])
        assert scope == ScopeType.IDENTITY  # identity checked first


# ---------------------------------------------------------------------------
# Test: RuleEngine — Evaluate
# ---------------------------------------------------------------------------


class TestEvaluate:

    def test_allowed_proposal_passes(self):
        """
        A config-scope proposal at SELF_CONFIG level passes governance.
        """
        proposal = _make_proposal(
            title="Config Update",
            components=["config"],
        )
        engine = RuleEngine()

        decision = engine.evaluate(
            proposal=proposal,
            current_level=ExecutionLevel.SELF_CONFIG,
        )

        assert decision.approved is True
        assert len(decision.violated_rules) == 0

    def test_identity_modification_rejected_at_administrative(self):
        """
        An identity-scope proposal at ADMINISTRATIVE level is rejected.
        GOV-001 requires AUTONOMOUS level.
        """
        proposal = _make_proposal(
            title="Modify Identity",
            components=["identity"],
        )
        engine = RuleEngine()

        decision = engine.evaluate(
            proposal=proposal,
            current_level=ExecutionLevel.ADMINISTRATIVE,
        )

        assert decision.approved is False
        assert len(decision.violated_rules) >= 1
        assert any("GOV-001" in v for v in decision.violated_rules)

    def test_insufficient_execution_level_rejected(self):
        """
        A code-scope proposal at ADMINISTRATIVE level is rejected.
        GOV-002 requires CODE_ARTIFACT level.
        """
        proposal = _make_proposal(
            title="Code Change",
            components=["code"],
        )
        engine = RuleEngine()

        decision = engine.evaluate(
            proposal=proposal,
            current_level=ExecutionLevel.ADMINISTRATIVE,
        )

        assert decision.approved is False
        assert len(decision.violated_rules) >= 1
        assert any("GOV-002" in v for v in decision.violated_rules)

    def test_rejected_decision_contains_explanation(self):
        """
        A rejected decision includes the reason and violated rule IDs.
        """
        proposal = _make_proposal(
            title="Identity Change",
            components=["identity"],
        )
        engine = RuleEngine()

        decision = engine.evaluate(
            proposal=proposal,
            current_level=ExecutionLevel.ADMINISTRATIVE,
        )

        assert decision.approved is False
        assert len(decision.reason) > 0
        assert "PROP-TEST" in decision.reason
        assert len(decision.violated_rules) >= 1

    def test_empty_registry_approves_all(self):
        """
        When the registry has no rules, all proposals pass.
        """
        empty_registry = ConstraintRegistry()
        empty_registry.clear()

        engine = RuleEngine(constraint_registry=empty_registry)

        # Identity proposal should pass with an empty registry
        proposal = _make_proposal(
            title="Identity Change",
            components=["identity"],
        )
        decision = engine.evaluate(
            proposal=proposal,
            current_level=ExecutionLevel.ADMINISTRATIVE,
        )

        assert decision.approved is True

    def test_memory_modification_rejected_at_administrative(self):
        """
        A memory-scope proposal at ADMINISTRATIVE level is rejected.
        GOV-004 requires INFORMATION level.
        """
        proposal = _make_proposal(
            title="Memory Update",
            components=["memory"],
        )
        engine = RuleEngine()

        decision = engine.evaluate(
            proposal=proposal,
            current_level=ExecutionLevel.ADMINISTRATIVE,
        )

        assert decision.approved is False
        assert any("GOV-004" in v for v in decision.violated_rules)

    def test_memory_modification_allowed_at_information(self):
        """
        A memory-scope proposal at INFORMATION level passes.
        """
        proposal = _make_proposal(
            title="Memory Update",
            components=["memory"],
        )
        engine = RuleEngine()

        decision = engine.evaluate(
            proposal=proposal,
            current_level=ExecutionLevel.INFORMATION,
        )

        assert decision.approved is True

    def test_capability_modification_rejected_at_administrative(self):
        """
        A capability-scope proposal at ADMINISTRATIVE level is rejected.
        GOV-005 requires SELF_CONFIG level.
        """
        proposal = _make_proposal(
            title="Capability Update",
            components=["capability"],
        )
        engine = RuleEngine()

        decision = engine.evaluate(
            proposal=proposal,
            current_level=ExecutionLevel.ADMINISTRATIVE,
        )

        assert decision.approved is False
        assert any("GOV-005" in v for v in decision.violated_rules)

    def test_capability_modification_allowed_at_self_config(self):
        """
        A capability-scope proposal at SELF_CONFIG level passes.
        """
        proposal = _make_proposal(
            title="Capability Update",
            components=["capability"],
        )
        engine = RuleEngine()

        decision = engine.evaluate(
            proposal=proposal,
            current_level=ExecutionLevel.SELF_CONFIG,
        )

        assert decision.approved is True

    def test_unknown_scope_allowed_at_any_level(self):
        """
        Proposals with UNKNOWN scope have no default rules and pass.
        """
        proposal = _make_proposal(
            title="Runtime Tuning",
            components=["runtime"],
        )
        engine = RuleEngine()

        decision = engine.evaluate(
            proposal=proposal,
            current_level=ExecutionLevel.ADMINISTRATIVE,
        )

        assert decision.approved is True

    def test_approved_decision_includes_reason(self):
        """
        An approved decision includes a human-readable reason.
        """
        proposal = _make_proposal(
            title="Config Tweak",
            components=["config"],
        )
        engine = RuleEngine()

        decision = engine.evaluate(
            proposal=proposal,
            current_level=ExecutionLevel.SELF_CONFIG,
        )

        assert decision.approved is True
        assert "passed all governance checks" in decision.reason
        assert "PROP-TEST" in decision.reason


# ---------------------------------------------------------------------------
# Test: RuleEngine — Forbidden Rule
# ---------------------------------------------------------------------------


class TestForbiddenRule:

    def test_forbidden_rule_rejects_proposal(self):
        """
        A rule with forbidden=True rejects proposals regardless of level.
        """
        registry = ConstraintRegistry()
        registry.register(
            GovernanceRule(
                rule_id="GOV-FORBID",
                description="Dangerous scope is forbidden.",
                scope=ScopeType.UNKNOWN,
                forbidden=True,
            )
        )
        engine = RuleEngine(constraint_registry=registry)

        proposal = _make_proposal(
            title="Dangerous Operation",
            components=["undefined"],
        )
        decision = engine.evaluate(
            proposal=proposal,
            current_level=ExecutionLevel.AUTONOMOUS,
        )

        assert decision.approved is False
        assert any("GOV-FORBID" in v for v in decision.violated_rules)
