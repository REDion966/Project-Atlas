"""Phase 11.11 — Governed promotion and activation: evidence contract.

Investigation result: the loop reuses the EXISTING ``PromotionGate``,
``PromotionExecutor`` and ``CapabilityActivator`` unchanged. Review is not
promotion; promotion is not activation; activation requires the existing
authority path; stale/duplicate/sensitive targets fail closed with rollback.
"""

from __future__ import annotations

from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.promotion_artifact import capture_promotion_artifact
from atlas.evolution.promotion_executor import PromotionExecutor, PromotionOutcome
from atlas.evolution.self_evolution import (
    SelfEvolutionLoop,
    SelfEvolutionTerminal,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry

_MODULE = "atlas/example/promote_handlers.py"
_CAPABILITY = "example.promoted"


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


def _run(
    tmp_path,
    *,
    capability_name=_CAPABILITY,
    supplier=None,
    authorized=True,
    registry=None,
):
    capabilities = registry if registry is not None else CapabilityRegistry()
    loop = SelfEvolutionLoop(
        change_supplier=supplier,
        component_registry=ComponentRegistry(),
        capability_registry=capabilities,
        repo_root=tmp_path,
    )
    candidate, assessment = _discovery()
    return loop.run(
        candidate,
        assessment,
        target_module=_MODULE,
        capability_name=capability_name,
        owner_approved=True,
        promotion_authorized=authorized,
    )


def _no_source_left(tmp_path) -> bool:
    """True when no source file was left behind (bytecode caches aside)."""
    return [
        p for p in tmp_path.rglob("*") if p.is_file() and p.suffix != ".pyc"
    ] == []


class TestPhase1111PromotionActivation:
    def test_review_approval_is_not_promotion(self, tmp_path):
        capabilities = CapabilityRegistry()
        result = _run(tmp_path, authorized=False, registry=capabilities)
        assert result.promotion_review_status == "pending_review"
        assert result.terminal is SelfEvolutionTerminal.PENDING_PROMOTION_REVIEW
        assert result.promotion_outcome == ""
        assert capabilities.registered_names == []
        assert not list(tmp_path.rglob("*"))

    def test_promotion_executor_still_requires_authorization(self, tmp_path):
        result = PromotionExecutor(tmp_path).promote(object(), authorized=False)
        assert result.outcome is PromotionOutcome.REFUSED_UNAUTHORIZED
        assert result.ok is False

    def test_activation_requires_governed_promotion(self, tmp_path):
        capabilities = CapabilityRegistry()
        result = _run(tmp_path, registry=capabilities)
        assert result.terminal is SelfEvolutionTerminal.ACTIVATED
        assert result.promotion_review_status == "approved"
        assert result.promotion_outcome == "promoted"
        assert result.activated_capabilities == (_CAPABILITY,)
        assert capabilities.registered_names == [_CAPABILITY]
        assert (tmp_path / _MODULE).is_file()

    def test_duplicate_capability_activation_fails_closed(self, tmp_path):
        capabilities = CapabilityRegistry()
        capabilities.register(_CAPABILITY, lambda params: None)
        result = _run(tmp_path, registry=capabilities)
        assert result.terminal is SelfEvolutionTerminal.PROMOTION_FAILED
        assert result.promotion_outcome != "promoted"
        assert result.activated_capabilities == ()
        # The whole changeset was rolled back: no source file remains.
        assert _no_source_left(tmp_path)
        assert not (tmp_path / _MODULE).exists()

    def test_drifted_target_is_refused_and_never_overwritten(self, tmp_path):
        """The consistency guard the loop relies on: a target that drifts
        between artifact capture and promotion is refused, never merged."""
        target = tmp_path / _MODULE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ORIGINAL = 1\n", encoding="utf-8")
        artifact = capture_promotion_artifact(
            [{"path": _MODULE, "content": "NEW = 2\n"}],
            proposal_id="P",
            repo_root=tmp_path,
        )
        target.write_text("DRIFTED = 3\n", encoding="utf-8")

        result = PromotionExecutor(tmp_path).promote(artifact, authorized=True)
        assert result.outcome is PromotionOutcome.REFUSED_STALE
        assert result.ok is False
        assert target.read_text(encoding="utf-8") == "DRIFTED = 3\n"

    def test_architecture_sensitive_target_is_refused(self, tmp_path):
        loop = SelfEvolutionLoop(
            component_registry=ComponentRegistry(),
            capability_registry=CapabilityRegistry(),
            repo_root=tmp_path,
        )
        candidate, assessment = _discovery()
        blocked = loop.run(
            candidate,
            assessment,
            target_module="atlas/kernel/evil_handlers.py",
            capability_name="example.evil",
            owner_approved=True,
            promotion_authorized=True,
        )
        assert blocked.ok is False
        assert blocked.activated_capabilities == ()
        assert not (tmp_path / "atlas" / "kernel" / "evil_handlers.py").exists()
        assert not list(tmp_path.rglob("*.py"))
