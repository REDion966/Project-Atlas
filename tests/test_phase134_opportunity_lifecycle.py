"""Phase 13.4 — Evolution opportunity lifecycle: evidence contract.

Validation result: the lifecycle is *derived*, never stored, so invalid
transitions are structurally impossible. It reuses the EXISTING
``ImprovementStatus`` vocabulary by mapping to it instead of defining a
competing lifecycle, and only ``READY`` is attemptable.
"""

from __future__ import annotations

import dataclasses

import pytest

from atlas.evolution.evolution_continuity import (
    EvolutionOpportunity,
    EvolutionOpportunityState,
    project_opportunities,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import ImprovementStatus
from atlas.evolution.self_evolution import SelfEvolutionTerminal
from tests.phase13_support import record_outcome

#: Phase-11 terminal -> expected continuity state (the authoritative mapping).
_EXPECTED: dict[str, EvolutionOpportunityState] = {
    "activated": EvolutionOpportunityState.COMPLETED,
    "stopped_at_approval": EvolutionOpportunityState.DEFERRED,
    "pending_promotion_review": EvolutionOpportunityState.DEFERRED,
    "promotion_not_ready": EvolutionOpportunityState.DEFERRED,
    "promotion_not_authorized": EvolutionOpportunityState.BLOCKED,
    "invalid_lifecycle_state": EvolutionOpportunityState.BLOCKED,
    "self_model_inconsistent": EvolutionOpportunityState.BLOCKED,
    "ineligible": EvolutionOpportunityState.BLOCKED,
    "rejected_candidate": EvolutionOpportunityState.REJECTED,
    "promotion_failed": EvolutionOpportunityState.REJECTED,
    "sandbox_failed": EvolutionOpportunityState.EVIDENCE_REQUIRED,
    "verification_failed": EvolutionOpportunityState.EVIDENCE_REQUIRED,
    "preparation_failed": EvolutionOpportunityState.EVIDENCE_REQUIRED,
    "invalid_objective": EvolutionOpportunityState.EVIDENCE_REQUIRED,
    "research_required": EvolutionOpportunityState.EVIDENCE_REQUIRED,
}


def _state_for(terminal: str) -> EvolutionOpportunityState:
    memory = EvolutionMemory()
    record_outcome(
        memory,
        cycle_id="SEV-1",
        subject="cap.x",
        terminal=terminal,
        outcome_kind="x",
    )
    return project_opportunities(memory)[0].state


class TestPhase134OpportunityLifecycle:
    def test_every_phase11_terminal_maps_to_a_state(self):
        for terminal in SelfEvolutionTerminal:
            assert terminal.value in _EXPECTED, terminal
        for terminal, expected in _EXPECTED.items():
            assert _state_for(terminal) is expected, terminal

    def test_states_map_onto_the_existing_improvement_lifecycle(self):
        memory = EvolutionMemory()
        record_outcome(
            memory,
            cycle_id="SEV-1",
            subject="cap.done",
            terminal="activated",
            outcome_kind="successful_evolution",
        )
        opportunity = project_opportunities(memory)[0]
        assert opportunity.to_improvement_status() is ImprovementStatus.COMPLETED
        assert opportunity.to_dict()["improvement_status"] == "COMPLETED"

    def test_only_ready_is_attemptable(self):
        for terminal, expected in _EXPECTED.items():
            memory = EvolutionMemory()
            record_outcome(
                memory,
                cycle_id="SEV-1",
                subject="cap.x",
                terminal=terminal,
                outcome_kind="x",
            )
            opportunity = project_opportunities(memory)[0]
            assert opportunity.state is expected
            assert opportunity.attemptable is (
                expected is EvolutionOpportunityState.READY
            ), terminal

    def test_in_progress_is_never_derived_from_history(self):
        for terminal in _EXPECTED:
            assert _state_for(terminal) is not EvolutionOpportunityState.IN_PROGRESS

    def test_unrecognised_or_missing_terminal_fails_closed(self):
        for terminal in ("", "something-new", "ACTIVATED?", "unknown"):
            memory = EvolutionMemory()
            record_outcome(
                memory,
                cycle_id="SEV-1",
                subject="cap.x",
                terminal=terminal,
                outcome_kind="x",
            )
            opportunity = project_opportunities(memory)[0]
            assert opportunity.state is EvolutionOpportunityState.DEFERRED
            assert opportunity.attemptable is False
            assert "fail closed" in opportunity.rationale

    def test_state_is_derived_so_invalid_transitions_are_impossible(self):
        opportunity = project_opportunities(None)
        assert opportunity == ()
        memory = EvolutionMemory()
        record_outcome(
            memory,
            cycle_id="SEV-1",
            subject="cap.x",
            terminal="activated",
            outcome_kind="successful_evolution",
        )
        derived = project_opportunities(memory)[0]
        assert dataclasses.is_dataclass(derived)
        with pytest.raises(dataclasses.FrozenInstanceError):
            derived.state = EvolutionOpportunityState.READY  # type: ignore[misc]
        assert not hasattr(derived, "set_state")
        # The derived state is stable under repeated projection (no drift).
        assert project_opportunities(memory)[0] == derived

    def test_ordering_is_deterministic_and_score_free(self):
        memory = EvolutionMemory()
        for index, (subject, terminal) in enumerate(
            (
                ("cap.done", "activated"),
                ("cap.failed", "sandbox_failed"),
                ("cap.blocked", "ineligible"),
                ("cap.deferred", "stopped_at_approval"),
            ),
            start=1,
        ):
            record_outcome(
                memory,
                cycle_id=f"SEV-{index}",
                subject=subject,
                terminal=terminal,
                outcome_kind="x",
            )
        ordered = [o.subject for o in project_opportunities(memory)]
        assert ordered == ["cap.blocked", "cap.done", "cap.deferred", "cap.failed"]
        assert ordered == [o.subject for o in project_opportunities(memory)]
        for banned in ("score", "priority", "rank", "weight"):
            assert not hasattr(EvolutionOpportunity, banned)
