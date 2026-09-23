"""Phase 11.4 — Evidence/research completion before development: evidence contract.

Investigation result: where evidence already exists, no research runs (the
existing ``DevelopmentCycleController`` evidence-sufficiency gate is reused);
where evidence is insufficient, the cycle stops before development and requires
bounded research. Unverified/unavailable knowledge never becomes development
truth.
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.self_evolution import (
    SelfEvolutionLoop,
    SelfEvolutionTerminal,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry

_MODULE = "atlas/example/research_handlers.py"
_CAPABILITY = "example.researched"


def _discovery(verdict=DiscoveryVerdict.ACTIONABLE_GAP, subject="example.missing"):
    evidence = (f"capability_model:{subject}",)
    candidate = CapabilityDiscoveryCandidate(
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
        research_question=f"what is required to {subject}",
    )
    return candidate, assessment


def _loop(tmp_path, **kwargs):
    return SelfEvolutionLoop(
        component_registry=ComponentRegistry(),
        capability_registry=CapabilityRegistry(),
        repo_root=tmp_path,
        **kwargs,
    )


class _RaisingRetriever:
    def retrieve(self, query):  # noqa: ARG002
        raise RuntimeError("knowledge unavailable")


class _EmptyRetriever:
    def retrieve(self, query):  # noqa: ARG002
        return SimpleNamespace(items=[])


def _run(loop, verdict=DiscoveryVerdict.ACTIONABLE_GAP, **kwargs):
    candidate, assessment = _discovery(verdict=verdict)
    return loop.run(
        candidate,
        assessment,
        target_module=_MODULE,
        capability_name=_CAPABILITY,
        **kwargs,
    )


class TestPhase114ResearchCompletion:
    def test_sufficient_evidence_requires_no_research(self, tmp_path):
        def _boom(**kwargs):  # pragma: no cover - must never be called
            raise AssertionError("unnecessary research was performed")

        result = _run(
            _loop(tmp_path, researcher=_boom),
            owner_approved=True,
            promotion_authorized=True,
        )
        assert result.terminal is SelfEvolutionTerminal.ACTIVATED

    def test_insufficient_evidence_stops_before_development(self, tmp_path):
        result = _run(
            _loop(tmp_path), verdict=DiscoveryVerdict.REQUIRES_RESEARCH
        )
        assert result.terminal is SelfEvolutionTerminal.RESEARCH_REQUIRED
        assert result.eligibility.research_question
        # Nothing was planned, developed, or written.
        assert not list(tmp_path.rglob("*.py"))

    def test_unverified_or_unavailable_knowledge_stays_blocked(self, tmp_path):
        for retriever in (_RaisingRetriever(), _EmptyRetriever()):
            result = _run(
                _loop(tmp_path),
                verdict=DiscoveryVerdict.REQUIRES_RESEARCH,
                knowledge_retriever=retriever,
                owner_approved=True,
                promotion_authorized=True,
            )
            assert result.terminal is SelfEvolutionTerminal.RESEARCH_REQUIRED
            assert not list(tmp_path.rglob("*.py"))

    def test_research_required_outcome_is_classified_as_research_insufficiency(
        self, tmp_path
    ):
        result = _run(
            _loop(tmp_path), verdict=DiscoveryVerdict.REQUIRES_RESEARCH
        )
        assert result.outcome.value == "research_insufficiency"
