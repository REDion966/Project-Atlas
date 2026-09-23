"""Phase 6.9 — Evidence/reporting: evidence contract.

Investigation result: the development lifecycle already produces auditable
evidence and distinguishes lifecycle states, so no parallel provenance framework
was introduced.

* ``EvolutionRecord`` (event_type ``development`` / ``execution``) — durable
  audit evidence with related ids + metadata, retrievable from
  ``EvolutionMemory`` (the same Phase-3 provenance surface).
* ``DevelopmentLifecycleReport`` — immutable aggregated lifecycle report.
* Proposal statuses distinguish proposed / pending-approval / approved /
  sandbox-authorized; ``assess_usefulness`` distinguishes verified outcomes.
"""

from __future__ import annotations

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.development_cycle import (
    DevelopmentCycleController,
    DevelopmentNeed,
)
from atlas.evolution.development_usefulness import (
    UsefulnessOutcome,
    assess_usefulness,
)
from atlas.evolution.development_verification import DevelopmentVerification
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import EvolutionRecord, ProposalStatus


class _CaptureStore:
    def __init__(self):
        self.proposals = []
        self.requests = []

    def store_proposal(self, proposal):
        self.proposals.append(proposal)

    def store_approval_request(self, request):
        self.requests.append(request)


class TestPhase69EvidenceReporting:
    def test_development_history_records_are_durable_and_linked(self):
        memory = EvolutionMemory()
        memory.store_record(
            EvolutionRecord(
                record_id="DEV-P69-1",
                event_type="development",
                description="Self-development run.",
                related_ids=["PROP-P69", "PLAN-P69"],
                metadata={"terminal_status": "SUCCESS", "success": True},
            )
        )
        records = memory.get_records_by_type("development")
        assert records and records[0].related_ids == ["PROP-P69", "PLAN-P69"]
        assert records[0].metadata["terminal_status"] == "SUCCESS"

    def test_lifecycle_states_are_distinguishable(self):
        assert ProposalStatus.DRAFT is not ProposalStatus.APPROVED
        assert ProposalStatus.PENDING_APPROVAL is not ProposalStatus.APPROVED
        assert ProposalStatus.SANDBOX_AUTHORIZED is not ProposalStatus.APPROVED
        assert ProposalStatus.APPROVED is not ProposalStatus.IMPLEMENTED

    def test_usefulness_distinguishes_verified_from_unverified(self):
        unverified = assess_usefulness(
            proposal_id="P",
            objective="o",
            verification_status="unverified",
            capability_present_before=False,
            capability_present_after=False,
        )
        verified = assess_usefulness(
            proposal_id="P",
            objective="o",
            verification_status="verified",
            capability_present_before=False,
            capability_present_after=True,
        )
        assert unverified.outcome is UsefulnessOutcome.INCONCLUSIVE
        assert verified.outcome is UsefulnessOutcome.USEFUL
        assert verified.effectiveness_score > unverified.effectiveness_score

    def test_cycle_proposal_carries_auditable_unverified_draft_metadata(self):
        store = _CaptureStore()
        controller = DevelopmentCycleController(
            approval_manager=ApprovalManager(),
            proposal_store=store,
            approval_request_store=store,
        )
        result = controller.run_development_cycle(
            DevelopmentNeed(
                title="add a widget capability",
                evidence_knowledge_ids=("k-1",),
                target_components=("atlas/example/widget.py",),
                metadata={
                    "code_changes": [
                        {"path": "atlas/example/widget.py", "content": "V = 1\n"}
                    ]
                },
            )
        )
        assert result.ok is True
        assert result.proposal_status == "PENDING_APPROVAL"
        proposal = store.proposals[0]
        assert proposal.metadata["development_cycle"]["content_status"] == "unverified-draft"
        assert proposal.metadata["development_cycle"]["generated_by"] == "F9-development-cycle"
        assert store.requests  # the approval request was persisted

    def test_verification_and_usefulness_report_evidence(self):
        report = DevelopmentVerification().verify(None)
        assert report.evidence
