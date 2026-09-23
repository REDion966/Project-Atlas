"""Phase 8.8 — Knowledge and provenance internalization: evidence contract.

Investigation result: provenance already exists (research citations,
``EvolutionRecord``, ``DevelopmentVerification``, development authorization), so
no second knowledge store was created. The acquisition strategy carries its
rationale and expected capability; lifecycle states stay distinct.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from atlas.evolution.capability_acquisition import (
    AcquisitionNeed,
    determine_acquisition_strategy,
)
from atlas.evolution.development_authorization import (
    DevelopmentAuthorizationMode,
    build_development_authorization,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import EvolutionRecord, ProposalStatus


class TestPhase88Provenance:
    def test_lifecycle_states_are_distinct(self):
        assert ProposalStatus.DRAFT is not ProposalStatus.APPROVED
        assert ProposalStatus.PENDING_APPROVAL is not ProposalStatus.APPROVED
        assert ProposalStatus.SANDBOX_AUTHORIZED is not ProposalStatus.APPROVED
        assert ProposalStatus.APPROVED is not ProposalStatus.IMPLEMENTED

    def test_acquisition_evidence_is_recorded_as_evolution_records(self):
        memory = EvolutionMemory()
        memory.store_record(
            EvolutionRecord(
                record_id="ACQ-1",
                event_type="capability_acquisition",
                description="Internal development acquisition of example.widget.",
                related_ids=["PROP-1", "example.widget"],
                metadata={
                    "mechanism": "internal_development",
                    "authorized_by": "user:owner",
                    "verification": "verified",
                },
            )
        )
        records = memory.get_records_by_type("capability_acquisition")
        assert records and records[0].related_ids == ["PROP-1", "example.widget"]
        assert records[0].metadata["mechanism"] == "internal_development"

    def test_authorization_records_its_provenance(self):
        authorization = build_development_authorization(
            SimpleNamespace(proposal_id="P", proposal_fingerprint="fp"),
            mode=DevelopmentAuthorizationMode.OWNER,
            granted_at=datetime(2026, 1, 1, 12, 0, 0),
        )
        assert authorization.authorized_by == "user:owner"
        assert authorization.is_owner is True
        assert authorization.expires_at is None

    def test_strategy_records_rationale_and_expected_capability(self):
        strategy = determine_acquisition_strategy(
            AcquisitionNeed(
                request="acquire widget search capability",
                target_capability="widget.search",
                knowledge_available=True,
                evidence=("https://example.com/design",),
            )
        )
        payload = strategy.to_dict()
        assert payload["expected_resulting_capability"] == "widget.search"
        assert payload["rationale"]
        assert payload["validation_required"]

    def test_acquisition_outcome_is_evidence_assessed(self):
        # The closest existing "benchmark" is the evidence-based usefulness
        # assessment (objective / capability improvement / regression /
        # verification evidence); it is never a performance prediction.
        from atlas.evolution.development_usefulness import (
            UsefulnessOutcome,
            assess_usefulness,
        )

        assessment = assess_usefulness(
            proposal_id="P",
            objective="acquire example.widget",
            verification_status="verified",
            capability_present_before=False,
            capability_present_after=True,
        )
        assert assessment.outcome is UsefulnessOutcome.USEFUL
        assert assessment.capability_improvement.value == "demonstrated"
