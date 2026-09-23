"""Phase 11.10 — Evolution evidence/history: evidence contract.

Investigation result: the lifecycle is recorded through the EXISTING
``EvolutionMemory`` / ``EvolutionRecord`` (plus ``promotion_review`` records
written by the existing gate). No second evolution-history store is created.
"""

from __future__ import annotations

from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.self_evolution import (
    SelfEvolutionCycleResult,
    SelfEvolutionLoop,
    SelfEvolutionTerminal,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry

_MODULE = "atlas/example/evidence_handlers.py"
_CAPABILITY = "example.evidenced"


def _discovery():
    evidence = ("capability_model:example.missing",)
    candidate = CapabilityDiscoveryCandidate(
        candidate_id="disc:x",
        kind=DiscoverySignalKind.UNAVAILABLE_CAPABILITY,
        subject="example.missing",
        sources=("capability_model",),
        evidence=evidence,
    )
    assessment = DiscoveryAssessment(
        candidate_id="disc:x",
        subject="example.missing",
        verdict=DiscoveryVerdict.ACTIONABLE_GAP,
        rationale="evidence-backed",
        evidence=evidence,
    )
    return candidate, assessment


def _run(tmp_path, memory, *, authorized=True):
    loop = SelfEvolutionLoop(
        evolution_memory=memory,
        component_registry=ComponentRegistry(),
        capability_registry=CapabilityRegistry(),
        repo_root=tmp_path,
    )
    candidate, assessment = _discovery()
    return loop.run(
        candidate,
        assessment,
        target_module=_MODULE,
        capability_name=_CAPABILITY,
        owner_approved=True,
        promotion_authorized=authorized,
    )


class TestPhase1110EvolutionEvidence:
    def test_complete_lifecycle_evidence_is_preserved(self, tmp_path):
        memory = EvolutionMemory()
        result = _run(tmp_path, memory)
        assert result.terminal is SelfEvolutionTerminal.ACTIVATED

        event_types = {r.event_type for r in memory.get_records()}
        assert "self_evolution_development" in event_types
        assert "promotion_review" in event_types
        assert "evolution_outcome" in event_types
        assert result.evidence_records

    def test_evidence_answers_why_what_changed_and_the_outcome(self, tmp_path):
        memory = EvolutionMemory()
        result = _run(tmp_path, memory)

        development = memory.get_records_by_type("self_evolution_development")[0]
        assert development.metadata["objective_id"]
        assert development.metadata["changed_files"] == [_MODULE]
        assert development.related_ids == [result.proposal_id]

        outcome = memory.get_records_by_type("evolution_outcome")[0]
        assert outcome.metadata["terminal"] == "activated"
        assert outcome.metadata["outcome_kind"] == "successful_evolution"
        assert outcome.metadata["cycle_id"] == result.cycle_id

    def test_no_second_evolution_history_store(self):
        import atlas.evolution.self_evolution as module

        for banned in ("EvolutionStore", "HistoryStore", "EvolutionDatabase"):
            assert not hasattr(module, banned)
        # The result is a plain, bounded, JSON-safe projection.
        assert "evidence_records" in SelfEvolutionCycleResult.__dataclass_fields__
