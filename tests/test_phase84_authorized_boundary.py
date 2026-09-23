"""Phase 8.4 — Authorized acquisition boundary: evidence contract.

Investigation result: governed authorization already exists (Development
Envelope / DevelopmentAuthorization + ApprovalManager + the OWNER gate), so no
new boundary was introduced. A capability gap is never permission to acquire.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from atlas.evolution.capability_acquisition import (
    AcquisitionMechanism,
    AcquisitionNeed,
    determine_acquisition_strategy,
)
from atlas.evolution.development_envelope import (
    SANDBOX_DEVELOPMENT,
    DevelopmentAuthority,
    DevelopmentEnvelope,
)
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.improvement_planner import ImprovementPriority
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ProposalStatus,
)
from atlas.evolution.self_development_loop import SelfDevelopmentLoop


def _proposal():
    return SimpleNamespace(
        proposal_id="PROP-P84",
        proposal_fingerprint="fp-84",
        expected_benefit="a value",
    )


def _evolution_proposal(status):
    plan = ImprovementPlan(
        plan_id="IMP-P84",
        title="t",
        description="d",
        priority=ImprovementPriority.MEDIUM,
        target_components=["mod"],
    )
    return EvolutionProposal(
        proposal_id="PROP-P84-LOOP",
        title="t",
        summary="s",
        rationale="r",
        expected_benefit="b",
        risks="low",
        impact_analysis="x",
        implementation_approach="y",
        plan=plan,
        status=status,
        metadata={"code_changes": [{"path": "atlas/x.py", "content": "V = 1\n"}]},
    )


class TestPhase84AuthorizedBoundary:
    def test_envelope_is_disabled_by_default(self):
        authority = DevelopmentAuthority(DevelopmentEnvelope())
        assert authority.check(SANDBOX_DEVELOPMENT).allowed is False
        assert authority.authorize(_proposal()) is None

    def test_enabled_envelope_authorizes_only_sandbox(self):
        envelope = DevelopmentEnvelope(
            enabled=True,
            max_runs_per_window=1,
            window_seconds=3600,
            authorization_ttl_minutes=30,
        )
        authority = DevelopmentAuthority(envelope)
        assert authority.check(SANDBOX_DEVELOPMENT).allowed is True
        # Promotion / live mutation are never inside the envelope.
        assert authority.check("promotion").allowed is False
        assert authority.check("live_repository_write").allowed is False

    def test_forbidden_operations_cannot_be_enabled(self):
        with pytest.raises(ValueError):
            DevelopmentEnvelope(
                enabled=True, allowed_operations=frozenset({"promotion"})
            )

    def test_unauthorized_acquisition_fails_closed(self):
        strategy = determine_acquisition_strategy(
            AcquisitionNeed(
                request="acquire widget search capability",
                target_capability="widget.search",
                knowledge_available=True,
                authorized=False,
            )
        )
        assert strategy.mechanism is AcquisitionMechanism.NONE
        assert strategy.authorization_required is True

    def test_unapproved_proposal_is_refused_by_the_loop(self):
        result = SelfDevelopmentLoop().run(
            _evolution_proposal(ProposalStatus.DRAFT), max_iterations=1
        )
        assert result.status is DevelopmentOutcomeStatus.GOVERNANCE_DENIED
