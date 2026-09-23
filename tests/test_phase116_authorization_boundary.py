"""Phase 11.6 — Governed authorization boundary: evidence contract.

Investigation result: the loop stops at the EXISTING approval boundary. The
approval decision is external (human/OWNER); discovery and research never grant
authorization, and no approval means no development execution.
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.approval_manager import ApprovalManager
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

_MODULE = "atlas/example/auth_handlers.py"
_CAPABILITY = "example.authorized"


class _HasKnowledge:
    def retrieve(self, query):  # noqa: ARG002
        return SimpleNamespace(items=[object()])


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


def _run(loop, verdict=DiscoveryVerdict.ACTIONABLE_GAP, **kwargs):
    candidate, assessment = _discovery(verdict=verdict)
    return loop.run(
        candidate,
        assessment,
        target_module=_MODULE,
        capability_name=_CAPABILITY,
        **kwargs,
    )


class TestPhase116AuthorizationBoundary:
    def test_no_approval_means_no_development(self, tmp_path):
        result = _run(_loop(tmp_path), owner_approved=False)
        assert result.terminal is SelfEvolutionTerminal.STOPPED_AT_APPROVAL
        assert result.approval_status == "PENDING_APPROVAL"
        assert result.proposal_id  # a real proposal reached the boundary
        assert not list(tmp_path.rglob("*.py"))

    def test_approval_is_performed_by_the_existing_manager(self, tmp_path):
        manager = ApprovalManager()
        result = _run(
            _loop(tmp_path, approval_manager=manager),
            owner_approved=True,
            promotion_authorized=False,
        )
        assert result.approval_status == "APPROVED"
        assert result.terminal is SelfEvolutionTerminal.PENDING_PROMOTION_REVIEW

    def test_promotion_authorization_cannot_bypass_approval(self, tmp_path):
        result = _run(
            _loop(tmp_path), owner_approved=False, promotion_authorized=True
        )
        assert result.terminal is SelfEvolutionTerminal.STOPPED_AT_APPROVAL
        assert not list(tmp_path.rglob("*.py"))

    def test_discovery_does_not_authorize_development(self, tmp_path):
        result = _run(
            _loop(tmp_path), verdict=DiscoveryVerdict.INSUFFICIENT_EVIDENCE
        )
        assert result.terminal is SelfEvolutionTerminal.REJECTED_CANDIDATE
        assert result.proposal_id == ""
        assert not list(tmp_path.rglob("*.py"))

    def test_research_evidence_does_not_authorize_development(self, tmp_path):
        result = _run(
            _loop(tmp_path),
            verdict=DiscoveryVerdict.REQUIRES_RESEARCH,
            knowledge_retriever=_HasKnowledge(),
            owner_approved=False,
        )
        assert result.terminal is SelfEvolutionTerminal.STOPPED_AT_APPROVAL
        assert not list(tmp_path.rglob("*.py"))
