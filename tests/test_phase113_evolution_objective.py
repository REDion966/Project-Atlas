"""Phase 11.3 — Evolution objective formation: evidence contract.

Investigation result: the objective of record IS the existing
``DevelopmentNeed`` — no parallel planning model is introduced, and a malformed
or escaping target fails closed.
"""

from __future__ import annotations

from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.self_evolution import (
    evolution_candidate_from_discovery,
    form_evolution_objective,
)

_MODULE = "atlas/example/evolve_handlers.py"
_CAPABILITY = "example.evolved"


def _candidate(verdict=DiscoveryVerdict.ACTIONABLE_GAP, subject="example.missing"):
    evidence = (f"capability_model:{subject}",)
    discovery = CapabilityDiscoveryCandidate(
        candidate_id="disc:x",
        kind=DiscoverySignalKind.UNAVAILABLE_CAPABILITY,
        subject=subject,
        sources=("capability_model",),
        evidence=evidence,
    )
    assessment = DiscoveryAssessment(
        candidate_id="disc:x",
        subject=subject,
        verdict=verdict,
        rationale="evidence-backed",
        evidence=evidence,
    )
    return evolution_candidate_from_discovery(discovery, assessment)


class TestPhase113EvolutionObjective:
    def test_objective_renders_the_existing_development_need(self):
        objective = form_evolution_objective(
            _candidate(), target_module=_MODULE, capability_name=_CAPABILITY
        )
        assert objective is not None
        assert objective.to_dict()["objective_id"].startswith("EVOBJ-")
        assert objective.success_criteria  # bounded + verifiable

        need = objective.to_development_need()
        assert isinstance(need, DevelopmentNeed)
        assert need.title
        assert need.target_components == (_MODULE,)
        assert need.evidence_knowledge_ids == objective.evidence
        assert need.metadata["scaffold"] == {
            "module": _MODULE,
            "capability_name": _CAPABILITY,
        }
        assert need.metadata["evolution_objective"]["candidate_id"]

    def test_path_escape_fails_closed(self):
        for bad_module in ("../evil.py", "/abs/evil.py", "atlas/../../evil.py", ""):
            assert (
                form_evolution_objective(
                    _candidate(), target_module=bad_module, capability_name=_CAPABILITY
                )
                is None
            )

    def test_missing_capability_name_fails_closed(self):
        assert (
            form_evolution_objective(
                _candidate(), target_module=_MODULE, capability_name="   "
            )
            is None
        )

    def test_unvalidated_candidate_yields_no_objective(self):
        rejected = evolution_candidate_from_discovery(None, None)
        assert (
            form_evolution_objective(
                rejected, target_module=_MODULE, capability_name=_CAPABILITY
            )
            is None
        )

    def test_objective_is_deterministic(self):
        first = form_evolution_objective(
            _candidate(), target_module=_MODULE, capability_name=_CAPABILITY
        )
        second = form_evolution_objective(
            _candidate(), target_module=_MODULE, capability_name=_CAPABILITY
        )
        assert first.objective_id == second.objective_id
        assert first.to_dict() == second.to_dict()
