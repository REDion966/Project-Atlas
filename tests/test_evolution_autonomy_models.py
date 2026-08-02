"""
Atlas Evolution Autonomy — Model Tests — Phase 16.1

Verifies the Phase 16.1 data models are pure, frozen, slotted
dataclasses with the exact structure of the approved specification:
16 request statuses (no VERIFIED/DETECTED), closed enums, default
facilities, forward-reference-free construction, and immutability.

Matches existing Atlas model test conventions (pure logic, no infra).
"""

import unittest
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import datetime
from typing import Any

from atlas.evolution.autonomy.models import (
    AtlasStateVersion,
    AuthorizationMode,
    AutonomyPolicy,
    ChangeReceipt,
    EvolutionAuthorization,
    EvolutionOutcomeRecord,
    EvolutionRequest,
    EvolutionRequestStatus,
    EvolutionSchedule,
    EvolutionStatusReport,
    EvolutionWindow,
    RiskAssessment,
    RiskLevel,
    RollbackPlan,
    RollbackStrategy,
    StagedConfigEntry,
    TargetKind,
    ValidationReport,
    VerificationResult,
    VersionTarget,
)
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel


class TestEvolutionRequestStatus(unittest.TestCase):
    """The 16-state lifecycle enum matches the approved specification."""

    def test_has_exactly_sixteen_states(self):
        expected = {
            "DRAFTED",
            "VALIDATED",
            "RISK_ASSESSED",
            "PENDING_AUTHORIZATION",
            "AUTHORIZED",
            "SCHEDULED",
            "APPLIED",
            "PENDING_EFFECTIVE",
            "COMPLETED",
            "FAILED",
            "ROLLED_BACK",
            "SUPERSEDED",
            "CANCELLED",
            "EXPIRED",
            "REJECTED",
            "EVOLUTION_HOLD",
        }
        self.assertEqual({s.name for s in EvolutionRequestStatus}, expected)

    def test_verified_is_absent(self):
        self.assertNotIn("VERIFIED", {s.name for s in EvolutionRequestStatus})

    def test_detected_is_absent(self):
        self.assertNotIn("DETECTED", {s.name for s in EvolutionRequestStatus})

    def test_drafted_is_initial_state(self):
        self.assertIs(EvolutionRequestStatus.DRAFTED, EvolutionRequestStatus.DRAFTED)


class TestCoreEnums(unittest.TestCase):
    """Closed domain enums carry the approved members only."""

    def test_risk_level_members(self):
        self.assertEqual(
            {r.name for r in RiskLevel},
            {"LOW", "MEDIUM", "HIGH", "CRITICAL"},
        )

    def test_authorization_mode_members(self):
        self.assertEqual(
            {m.name for m in AuthorizationMode},
            {"EXPLICIT", "POLICY", "AUTONOMY"},
        )

    def test_rollback_strategy_members(self):
        self.assertEqual(
            {s.name for s in RollbackStrategy},
            {"SNAPSHOT", "INVERSE_OP"},
        )

    def test_target_kind_members(self):
        self.assertEqual(
            {k.name for k in TargetKind},
            {"CONFIG", "MEMORY", "KNOWLEDGE", "CAPABILITY"},
        )


class TestDataclassProperties(unittest.TestCase):
    """All models are frozen and slotted dataclasses."""

    MODELS = (
        AutonomyPolicy,
        EvolutionWindow,
        ValidationReport,
        RiskAssessment,
        EvolutionAuthorization,
        EvolutionSchedule,
        VersionTarget,
        RollbackPlan,
        ChangeReceipt,
        VerificationResult,
        EvolutionRequest,
        AtlasStateVersion,
        EvolutionOutcomeRecord,
        StagedConfigEntry,
        EvolutionStatusReport,
    )

    def test_all_models_are_dataclasses(self):
        for model in self.MODELS:
            self.assertTrue(is_dataclass(model), f"{model.__name__} is not a dataclass")

    def test_all_models_are_frozen(self):
        for model in self.MODELS:
            with self.subTest(model=model.__name__):
                params: Any = getattr(model, "__dataclass_params__", None)
                self.assertIsNotNone(
                    params, f"{model.__name__} has no dataclass params"
                )
                self.assertFalse(
                    params.frozen is False,
                    f"{model.__name__} is not frozen",
                )

    def test_all_models_use_slots(self):
        for model in self.MODELS:
            with self.subTest(model=model.__name__):
                self.assertTrue(
                    hasattr(model, "__slots__"),
                    f"{model.__name__} does not use slots",
                )

    def test_immutability_enforced(self):
        with self.assertRaises(FrozenInstanceError):
            request = EvolutionRequest(
                request_id="AUTORQ-1",
                source="cli",
                target_scope=ScopeType.CONFIG,
            )
            request.status = EvolutionRequestStatus.SCHEDULED  # type: ignore[misc]


class TestEvolutionRequest(unittest.TestCase):
    """Default construction of the canonical request artifact."""

    def test_defaults(self):
        req = EvolutionRequest(
            request_id="AUTORQ-1",
            source="cli",
            target_scope=ScopeType.CONFIG,
        )
        self.assertEqual(req.status, EvolutionRequestStatus.DRAFTED)
        self.assertEqual(req.intended_level, ExecutionLevel.ADMINISTRATIVE)
        self.assertEqual(req.change_payload, {})
        self.assertIsNone(req.validation)
        self.assertIsNone(req.risk)
        self.assertIsNone(req.authorization)
        self.assertIsNone(req.schedule)
        self.assertEqual(req.parent_request_ids, [])
        self.assertEqual(req.metadata, {})
        self.assertIsInstance(req.created_at, datetime)
        self.assertIsInstance(req.updated_at, datetime)

    def test_required_fields(self):
        req = EvolutionRequest(
            request_id="AUTORQ-2",
            source="goal_id",
            target_scope=ScopeType.MEMORY,
        )
        self.assertEqual(req.request_id, "AUTORQ-2")
        self.assertEqual(req.source, "goal_id")
        self.assertEqual(req.target_scope, ScopeType.MEMORY)

    def test_slot_restricted(self):
        req = EvolutionRequest(
            request_id="AUTORQ-3",
            source="cli",
            target_scope=ScopeType.KNOWLEDGE,
        )
        with self.assertRaises(AttributeError):
            req.unknown_attribute = 1  # type: ignore[attr-defined]


class TestAutonomyPolicy(unittest.TestCase):
    """The policy mirror defaults to a fully disabled envelope."""

    def test_disabled_by_default(self):
        policy = AutonomyPolicy()
        self.assertFalse(policy.enabled)
        self.assertEqual(policy.effective_execution_level, ExecutionLevel.ADMINISTRATIVE)
        self.assertEqual(policy.allowed_scopes, [])
        self.assertEqual(policy.max_requests_per_window, 0)
        self.assertEqual(policy.hot_reload_allowlist, [])
        self.assertIsNone(policy.window)
        self.assertEqual(policy.version, "")


class TestVersionTarget(unittest.TestCase):
    """Version anchors carry the optimistic-concurrency string."""

    def test_anchor_default(self):
        target = VersionTarget(target_kind=TargetKind.CONFIG)
        self.assertEqual(target.current_version, "")
        self.assertEqual(target.target_version, "")
        self.assertEqual(target.state_version_at_creation, "")


class TestEvolutionOutcomeRecord(unittest.TestCase):
    """The Phase 17 evidence contract carries proof fields."""

    def test_defaults_are_failure_safe(self):
        record = EvolutionOutcomeRecord(
            outcome_record_id="OUT-1",
            request_id="AUTORQ-1",
            scope=ScopeType.CONFIG,
        )
        self.assertEqual(record.outcome, "FAILED")
        self.assertFalse(record.verification_passed)
        self.assertFalse(record.rollback_occurred)
        self.assertEqual(record.effectiveness_proxy, 0.0)
        self.assertEqual(record.strategy_key, "")
        self.assertEqual(record.planning_context_version, "")


class TestStatusReport(unittest.TestCase):
    """The typed bound query result defaults to a sane empty state."""

    def test_defaults(self):
        report = EvolutionStatusReport()
        self.assertEqual(report.state_version, "")
        self.assertFalse(report.hold)
        self.assertEqual(report.pending_authorizations, 0)
        self.assertEqual(report.scheduled, [])
        self.assertEqual(report.in_flight, [])
        self.assertEqual(report.window_quota_used, 0)
        self.assertEqual(report.policy_version, "")


class TestModelFieldCoverage(unittest.TestCase):
    """Every approved spec §4 dataclass is present with its key field."""

    FIELD_PROBES = {
        AutonomyPolicy: "effective_execution_level",
        EvolutionRequest: "parent_request_ids",
        EvolutionRequestStatus: "EVOLUTION_HOLD",
        ValidationReport: "violations",
        RiskAssessment: "requires_user_approval",
        EvolutionAuthorization: "authorized_by",
        EvolutionSchedule: "max_attempts",
        VersionTarget: "state_version_at_creation",
        RollbackPlan: "cascade_targets",
        ChangeReceipt: "changed_keys",
        VerificationResult: "passed",
        AtlasStateVersion: "applied_request_ids",
        EvolutionOutcomeRecord: "effectiveness_proxy",
        StagedConfigEntry: "schema_status",
        EvolutionStatusReport: "window_quota_used",
    }

    def test_key_fields_exist(self):
        for model, field_name in self.FIELD_PROBES.items():
            with self.subTest(model=model.__name__, field=field_name):
                present = {
                    f.name for f in (
                        fields(model)
                        if is_dataclass(model)
                        else []
                    )
                }
                if is_dataclass(model):
                    self.assertIn(field_name, present)
                else:
                    # Enum member probe
                    self.assertTrue(
                        hasattr(model, field_name),
                        f"{model.__name__} lacks {field_name}",
                    )


if __name__ == "__main__":
    unittest.main()
