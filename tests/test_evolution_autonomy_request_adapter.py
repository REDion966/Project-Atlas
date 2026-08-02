"""
Atlas Evolution Autonomy — AutonomyRequestAdapter Tests — Phase 16.1

Verifies the SOLE translator ``EvolutionRequest -> EvolutionProposal``:

- ``target_components`` are derived EXCLUSIVELY from ``target_scope`` via
  the closed scope map (Decision D2).
- The translated proposal status is APPROVED and deterministic.
- UNKNOWN-scope requests translate to UNKNOWN components and would be
  refused at the gateway's UNKNOWN-close invariant (later sub-phase).
- No payload or user input can smuggle a different component set.

Pure logic. No infra. No AI.
"""

import unittest

from atlas.evolution.autonomy.autonomy_request_adapter import (
    AutonomyRequestAdapter,
    _area_for_scope,
    _expected_benefit_for_scope,
)
from atlas.evolution.autonomy.models import EvolutionRequest
from atlas.evolution.autonomy.scope_classifier import components_for_scope
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel, ProposalStatus


class _RequestFactory:
    """Builds minimal EvolutionRequests for adapter tests."""

    @staticmethod
    def request(scope: ScopeType, payload: dict | None = None) -> EvolutionRequest:
        return EvolutionRequest(
            request_id="AUTORQ-1",
            source="cli",
            target_scope=scope,
            change_payload=payload or {},
            intended_level=ExecutionLevel.SELF_CONFIG,
        )


class TestAutonomyRequestAdapter(unittest.TestCase):
    """The SOLE translator derives components only from target_scope."""

    def test_proposal_id_prefix(self):
        req = _RequestFactory.request(ScopeType.CONFIG)
        proposal = AutonomyRequestAdapter.to_proposal(req)
        self.assertEqual(proposal.proposal_id, "AUTOX-AUTORQ-1")

    def test_status_is_approved(self):
        req = _RequestFactory.request(ScopeType.MEMORY)
        proposal = AutonomyRequestAdapter.to_proposal(req)
        self.assertEqual(proposal.status, ProposalStatus.APPROVED)

    def test_config_components_derived_from_scope_only(self):
        # Payload attempts to claim a different component set.
        payload = {"target_components": ["kernel", "ai"], "title": "Sneaky"}
        req = _RequestFactory.request(ScopeType.CONFIG, payload)
        proposal = AutonomyRequestAdapter.to_proposal(req)
        self.assertEqual(
            set(proposal.plan.target_components),
            set(components_for_scope(ScopeType.CONFIG)),
        )

    def test_memory_components_derived_from_scope_only(self):
        req = _RequestFactory.request(ScopeType.MEMORY)
        proposal = AutonomyRequestAdapter.to_proposal(req)
        self.assertEqual(
            set(proposal.plan.target_components),
            {"memory", "autonomy:memory"},
        )

    def test_knowledge_components_derived_from_scope_only(self):
        req = _RequestFactory.request(ScopeType.KNOWLEDGE)
        proposal = AutonomyRequestAdapter.to_proposal(req)
        self.assertEqual(
            set(proposal.plan.target_components),
            {"knowledge", "autonomy:knowledge"},
        )

    def test_capability_components_derived_from_scope_only(self):
        req = _RequestFactory.request(ScopeType.CAPABILITY)
        proposal = AutonomyRequestAdapter.to_proposal(req)
        self.assertEqual(
            set(proposal.plan.target_components),
            {"capability", "autonomy:capability"},
        )

    def test_unknown_scope_yields_unknown_components(self):
        req = _RequestFactory.request(ScopeType.UNKNOWN)
        proposal = AutonomyRequestAdapter.to_proposal(req)
        self.assertEqual(proposal.plan.target_components, ["governance:unknown"])

    def test_title_from_payload(self):
        req = _RequestFactory.request(ScopeType.CONFIG, {"title": "My config change"})
        proposal = AutonomyRequestAdapter.to_proposal(req)
        self.assertEqual(proposal.title, "My config change")

    def test_metadata_carries_request_provenance(self):
        req = _RequestFactory.request(ScopeType.KNOWLEDGE)
        proposal = AutonomyRequestAdapter.to_proposal(req)
        self.assertEqual(proposal.metadata["source_request_id"], "AUTORQ-1")
        self.assertEqual(proposal.metadata["source"], "cli")
        self.assertEqual(proposal.metadata["target_scope"], "KNOWLEDGE")

    def test_plan_weakness_area_is_scope_aligned(self):
        req = _RequestFactory.request(ScopeType.CAPABILITY)
        proposal = AutonomyRequestAdapter.to_proposal(req)
        self.assertEqual(proposal.plan.weaknesses[0].area, "capability")

    def test_expected_benefit_is_scope_aligned(self):
        req = _RequestFactory.request(ScopeType.MEMORY)
        proposal = AutonomyRequestAdapter.to_proposal(req)
        self.assertIn("Memory", proposal.expected_benefit)

    def test_deterministic_same_request_same_proposal(self):
        req = _RequestFactory.request(ScopeType.CONFIG, {"title": "X"})
        first = AutonomyRequestAdapter.to_proposal(req)
        second = AutonomyRequestAdapter.to_proposal(req)
        self.assertEqual(first.proposal_id, second.proposal_id)
        self.assertEqual(first.title, second.title)
        self.assertEqual(first.plan.target_components, second.plan.target_components)

    def test_state_scope_never_unknown(self):
        for scope in (ScopeType.CONFIG, ScopeType.MEMORY,
                      ScopeType.KNOWLEDGE, ScopeType.CAPABILITY):
            with self.subTest(scope=scope.name):
                req = _RequestFactory.request(scope)
                proposal = AutonomyRequestAdapter.to_proposal(req)
                self.assertNotEqual(proposal.plan.target_components, ["governance:unknown"])


class TestScopeDomainMappings(unittest.TestCase):
    """Deterministic scope → area / expected-benefit helpers."""

    def test_area_mappings(self):
        self.assertEqual(_area_for_scope(ScopeType.CONFIG), "config")
        self.assertEqual(_area_for_scope(ScopeType.MEMORY), "memory")
        self.assertEqual(_area_for_scope(ScopeType.KNOWLEDGE), "knowledge")
        self.assertEqual(_area_for_scope(ScopeType.CAPABILITY), "capability")
        self.assertEqual(_area_for_scope(ScopeType.UNKNOWN), "governance:unknown")

    def test_expected_benefit_mappings(self):
        self.assertIn("Configuration", _expected_benefit_for_scope(ScopeType.CONFIG))
        self.assertIn("Memory", _expected_benefit_for_scope(ScopeType.MEMORY))
        self.assertIn("Knowledge", _expected_benefit_for_scope(ScopeType.KNOWLEDGE))
        self.assertIn("Capability", _expected_benefit_for_scope(ScopeType.CAPABILITY))


if __name__ == "__main__":
    unittest.main()
