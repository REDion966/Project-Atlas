"""Phase 13.3 — Future opportunity formation: evidence contract.

Validation result: a deterministic bridge converts validated historical
evidence (persisted evolution outcomes) into future candidate signals, and it
composes with the EXISTING Phase-10 discovery rather than competing with it.
No opaque score, no LLM, no second discovery engine.
"""

from __future__ import annotations

from atlas.evolution.capability_discovery import run_discovery_cycle
from atlas.evolution.evolution_continuity import (
    EvolutionOpportunityState,
    continuation_view,
    gate_candidates,
    project_opportunities,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.self_knowledge.capability_model import build_capability_model
from tests.phase13_support import candidate, record_outcome


def _memory_with(*outcomes) -> EvolutionMemory:
    memory = EvolutionMemory()
    for index, (subject, terminal, kind) in enumerate(outcomes, start=1):
        record_outcome(
            memory,
            cycle_id=f"SEV-{index:06d}",
            subject=subject,
            terminal=terminal,
            outcome_kind=kind,
        )
    return memory


class TestPhase133FutureOpportunityFormation:
    def test_opportunities_are_formed_from_recorded_outcomes(self):
        memory = _memory_with(
            ("cap.a", "activated", "successful_evolution"),
            ("cap.b", "sandbox_failed", "unsuccessful_attempt"),
            ("cap.c", "research_required", "research_insufficiency"),
        )
        opportunities = project_opportunities(memory)
        by_subject = {o.subject: o for o in opportunities}
        assert set(by_subject) == {"cap.a", "cap.b", "cap.c"}
        assert by_subject["cap.a"].state is EvolutionOpportunityState.COMPLETED
        assert (
            by_subject["cap.b"].state is EvolutionOpportunityState.EVIDENCE_REQUIRED
        )
        assert (
            by_subject["cap.c"].state is EvolutionOpportunityState.EVIDENCE_REQUIRED
        )
        assert all(o.rationale for o in opportunities)

    def test_repeated_failures_are_visible_as_attempt_history(self):
        memory = _memory_with(
            ("cap.repeat", "sandbox_failed", "unsuccessful_attempt"),
            ("cap.repeat", "verification_failed", "verification_failure"),
        )
        opportunity = project_opportunities(memory)[0]
        assert opportunity.attempts == 2
        # The most recent outcome is authoritative for the current state.
        assert opportunity.last_terminal == "verification_failed"
        assert opportunity.requires_new_evidence is True

    def test_no_repeated_attempt_is_admitted_without_new_evidence(self):
        memory = _memory_with(
            ("cap.broken", "promotion_failed", "unsuccessful_attempt"),
            ("cap.denied", "promotion_not_authorized", "governance_rejection"),
        )
        view = continuation_view(memory)
        assert view.may_attempt("cap.broken")[0] is False
        assert view.may_attempt("cap.denied")[0] is False
        # A subject with no history at all remains attemptable (fresh evidence
        # is supplied by discovery, not by history).
        assert view.may_attempt("cap.fresh")[0] is True

    def test_bridge_composes_with_phase10_discovery(self):
        memory = _memory_with(
            ("example.missing", "activated", "successful_evolution"),
        )
        view = continuation_view(memory)

        # Phase 10 discovers the gap again (its own registry says unavailable)...
        registry = ComponentRegistry()
        registry.register(
            ComponentMetadata(
                name="down_provider",
                package="atlas.example",
                module_path="atlas.example.down",
                status=ComponentStatus.OFFLINE,
                provided_capabilities=["example.missing"],
            )
        )
        discovery = run_discovery_cycle(
            capability_model=build_capability_model(registry)
        )
        assessment = next(
            a for a in discovery.assessments if a.verdict.value == "actionable_gap"
        )
        found = next(
            c
            for c in discovery.candidates
            if c.candidate_id == assessment.candidate_id
        )

        # ...but the continuity gate refuses to repeat an already-activated one.
        gate = gate_candidates([found], view)
        assert gate.admitted == ()
        assert "already activated" in gate.excluded[0][1]

    def test_gate_is_advisory_and_produces_no_score(self):
        gate = gate_candidates([candidate("cap.fresh")[0]], continuation_view(None))
        assert gate.admitted_ids == ("disc:cap.fresh",)
        payload = gate.to_dict()
        for banned in ("score", "priority", "rank", "weight"):
            assert banned not in payload
        assert "excluded" in payload and "admitted" in payload
