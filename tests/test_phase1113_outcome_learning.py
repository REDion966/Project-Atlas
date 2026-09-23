"""Phase 11.13 — Outcome learning / evolution feedback: evidence contract.

Investigation result: outcomes are fed back through the EXISTING
``EvolutionMemory`` (``EvolutionRecord`` + ``EvolutionInsight``). This is not
the Phase-13 continuous-evolution system, and the feedback never triggers
another cycle.
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.self_evolution import (
    EvolutionOutcomeKind,
    SelfEvolutionLoop,
    SelfEvolutionTerminal,
    classify_evolution_outcome,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry

_MODULE = "atlas/example/outcome_handlers.py"
_CAPABILITY = "example.outcomed"


class _StubDevelopmentLoop:
    def __init__(self, result):
        self._result = result

    def run(self, proposal, max_iterations=None):  # noqa: ARG002
        return self._result


def _discovery(verdict=DiscoveryVerdict.ACTIONABLE_GAP):
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
        verdict=verdict,
        rationale="evidence-backed",
        evidence=evidence,
        research_question="what is needed",
    )
    return candidate, assessment


def _run(tmp_path, memory, **kwargs):
    loop = SelfEvolutionLoop(
        evolution_memory=memory,
        change_supplier=kwargs.pop("supplier", None),
        development_loop=kwargs.pop("development_loop", None),
        component_registry=ComponentRegistry(),
        capability_registry=CapabilityRegistry(),
        repo_root=tmp_path,
    )
    candidate, assessment = _discovery(kwargs.pop("verdict", DiscoveryVerdict.ACTIONABLE_GAP))
    return loop.run(
        candidate,
        assessment,
        target_module=_MODULE,
        capability_name=_CAPABILITY,
        **kwargs,
    )


class TestPhase1113OutcomeLearning:
    def test_successful_cycle_records_reusable_evidence(self, tmp_path):
        memory = EvolutionMemory()
        result = _run(tmp_path, memory, owner_approved=True, promotion_authorized=True)
        assert result.terminal is SelfEvolutionTerminal.ACTIVATED
        assert result.outcome is EvolutionOutcomeKind.SUCCESSFUL_EVOLUTION
        assert memory.get_records_by_type("evolution_outcome")
        insights = memory.get_insights()
        assert insights and insights[0].outcome == "successful_evolution"

    def test_governance_rejection_is_classified_and_recorded(self, tmp_path):
        memory = EvolutionMemory()
        result = _run(tmp_path, memory, owner_approved=False)
        assert result.terminal is SelfEvolutionTerminal.STOPPED_AT_APPROVAL
        assert result.outcome is EvolutionOutcomeKind.GOVERNANCE_REJECTION
        record = memory.get_records_by_type("evolution_outcome")[0]
        assert record.metadata["outcome_kind"] == "governance_rejection"

    def test_verification_failure_is_classified(self, tmp_path):
        memory = EvolutionMemory()
        stub = SimpleNamespace(
            status=DevelopmentOutcomeStatus.SUCCESS,
            outcomes=[],
            iterations_used=1,
            message="no evidence",
            plan=None,
        )
        result = _run(
            tmp_path,
            memory,
            owner_approved=True,
            promotion_authorized=True,
            development_loop=_StubDevelopmentLoop(stub),
        )
        assert result.terminal is SelfEvolutionTerminal.VERIFICATION_FAILED
        assert result.outcome is EvolutionOutcomeKind.VERIFICATION_FAILURE

    def test_research_insufficiency_is_classified(self, tmp_path):
        result = _run(
            tmp_path,
            EvolutionMemory(),
            verdict=DiscoveryVerdict.REQUIRES_RESEARCH,
        )
        assert result.outcome is EvolutionOutcomeKind.RESEARCH_INSUFFICIENCY

    def test_every_terminal_state_has_an_outcome(self):
        for terminal in SelfEvolutionTerminal:
            assert isinstance(classify_evolution_outcome(terminal), EvolutionOutcomeKind)
        assert (
            classify_evolution_outcome("garbage") is EvolutionOutcomeKind.PARTIAL_RESULT
        )

    def test_feedback_never_triggers_another_cycle(self, tmp_path):
        memory = EvolutionMemory()
        result = _run(tmp_path, memory, owner_approved=True, promotion_authorized=True)
        assert result.next_cycle_allowed is False
        # Nothing in the module schedules or chains another cycle.
        import atlas.evolution.self_evolution as module

        for banned in ("schedule", "cron", "timer", "next_cycle", "chain"):
            assert not hasattr(module, banned)
