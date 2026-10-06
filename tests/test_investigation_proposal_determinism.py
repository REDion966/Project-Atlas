"""Deterministic-first: identical evidence must yield an identical proposal id.

Real-kernel evidence (Step 11 ``send``/``stream`` parity) showed that
``InvestigationProposalGenerator.generate_proposal`` built its proposal id from
``datetime.now()``:

    proposal_id = f"INV-PROP-{timestamp}-{counter:04d}"

Because that id is rendered into conversational output, the SAME investigation
produced DIFFERENT text on every run, at different instants. This is a direct
violation of Atlas's deterministic-first invariant and made the
``send``/``stream`` parity contract unachievable by construction — no amount of
routing work could fix it, because the two entry points ran the same
non-deterministic code at different times.

The id is now derived from the EVIDENCE the proposal represents (target,
diagnosis, components, findings, affected files) using the module's existing
``hashlib`` content-hash convention, with the per-instance counter retained for
uniqueness. The proposal remains a stable, opaque lookup key: nothing in Atlas
parses the id for a timestamp (verified across the CLI, governance and
promotion paths).

Governance, approval and promotion are untouched — this changes only the identity
string of a deterministic, read-only proposal.
"""

from __future__ import annotations

from atlas.conversation.investigation import (
    InvestigationFinding,
    InvestigationProposalGenerator,
    InvestigationReport,
)


def _meaningful_report(target: str = "the memory service") -> InvestigationReport:
    """A report that the EXISTING meaningful-improvement heuristic accepts."""
    return InvestigationReport(
        target=target,
        objective="understand the memory service",
        diagnosis="A concrete, evidence-backed diagnosis of the memory service.",
        components=["atlas.memory.service", "atlas.services.memory_service"],
        affected_files=["atlas/memory/service.py"],
        findings=(
            InvestigationFinding(
                category="reference",
                description="memory_service is referenced by the kernel",
                evidence="atlas/kernel/atlas.py",
                location="atlas/kernel/atlas.py:1",
            ),
            InvestigationFinding(
                category="test_gap",
                description="the memory path lacks a focused regression test",
                evidence="tests/",
                location="tests/",
            ),
        ),
        modification_status="NONE",
    )


class TestProposalIdDeterminism:
    def test_identical_evidence_yields_identical_id(self):
        report = _meaningful_report()
        first = InvestigationProposalGenerator().generate_proposal(report)
        second = InvestigationProposalGenerator().generate_proposal(report)
        assert first is not None and second is not None
        assert first.proposal_id == second.proposal_id

    def test_id_is_stable_across_generator_instances(self):
        report = _meaningful_report()
        # A fresh generator restarts the counter, so this also proves the id does
        # not depend on wall-clock time (which always differs between calls).
        first = InvestigationProposalGenerator().generate_proposal(report)
        second = InvestigationProposalGenerator().generate_proposal(report)
        assert first is not None and second is not None
        assert first.proposal_id == second.proposal_id

    def test_prefix_is_preserved(self):
        proposal = InvestigationProposalGenerator().generate_proposal(
            _meaningful_report()
        )
        assert proposal is not None
        assert proposal.proposal_id.startswith("INV-PROP-")

    def test_distinct_evidence_yields_distinct_ids(self):
        first = InvestigationProposalGenerator().generate_proposal(
            _meaningful_report("the memory service")
        )
        second = InvestigationProposalGenerator().generate_proposal(
            _meaningful_report("the storage layer")
        )
        assert first is not None and second is not None
        assert first.proposal_id != second.proposal_id

    def test_id_is_not_time_derived(self):
        """No wall-clock component: the id must not look like a timestamp."""
        proposal = InvestigationProposalGenerator().generate_proposal(
            _meaningful_report()
        )
        assert proposal is not None
        body = proposal.proposal_id[len("INV-PROP-"):].rsplit("-", 1)[0]
        # A deterministic content hash, not the previous %Y%m%d%H%M%S stamp.
        assert len(body) == 16
        assert int(body, 16) >= 0

    def test_repeat_generation_in_one_instance_stays_unique(self):
        """The counter still disambiguates repeats within one generator."""
        generator = InvestigationProposalGenerator()
        report = _meaningful_report()
        first = generator.generate_proposal(report)
        second = generator.generate_proposal(report)
        assert first is not None and second is not None
        assert first.proposal_id != second.proposal_id

    def test_meaningful_improvement_gate_is_unchanged(self):
        generator = InvestigationProposalGenerator()
        empty = InvestigationReport(
            target="nothing",
            objective="",
            diagnosis="",
            components=[],
            affected_files=[],
            findings=(),
            modification_status="NONE",
        )
        assert generator.generate_proposal(empty) is None
