"""Phase 9.10 — Self-development evidence and history: evidence contract.

Investigation result: Atlas already records development evidence/history through
``EvolutionRecord`` (durable, linked) and aggregates a
``DevelopmentLifecycleReport``; no new history store was created. Lifecycle
states remain distinct.
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.development_report import (
    DevelopmentLifecycleReport,
    DevelopmentReportBuilder,
    FinalConclusion,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import EvolutionRecord, ProposalStatus


class TestPhase910EvidenceHistory:
    def test_development_history_is_recorded_and_linked(self):
        memory = EvolutionMemory()
        memory.store_record(
            EvolutionRecord(
                record_id="DEV-P910-1",
                event_type="development",
                description="Self-development run.",
                related_ids=["PROP-P910", "PLAN-P910"],
                metadata={"terminal_status": "SUCCESS", "success": True},
            )
        )
        records = memory.get_records_by_type("development")
        assert records and records[0].related_ids == ["PROP-P910", "PLAN-P910"]
        assert records[0].metadata["terminal_status"] == "SUCCESS"

    def test_lifecycle_states_are_distinguishable(self):
        assert ProposalStatus.DRAFT is not ProposalStatus.PENDING_APPROVAL
        assert ProposalStatus.PENDING_APPROVAL is not ProposalStatus.APPROVED
        assert ProposalStatus.SANDBOX_AUTHORIZED is not ProposalStatus.APPROVED
        assert ProposalStatus.APPROVED is not ProposalStatus.IMPLEMENTED

    def test_lifecycle_report_aggregates_evidence(self):
        proposal = SimpleNamespace(
            proposal_id="P-P910",
            metadata={"execution": {"result_status": "SUCCESS"}},
        )
        approval = SimpleNamespace(request_id="APPR-P910")

        report = DevelopmentReportBuilder().build(
            state=SimpleNamespace(), proposal=proposal, approval=approval
        )
        assert isinstance(report, DevelopmentLifecycleReport)
        assert report.original_proposal_id == "P-P910"
        assert report.original_approval_id == "APPR-P910"
        assert isinstance(report.final_conclusion, FinalConclusion)
        assert report.evidence
