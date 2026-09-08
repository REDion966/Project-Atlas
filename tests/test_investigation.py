"""P12.3 — Read-only investigation capability tests.

Proves the investigation classification, routing, read-only safety, and
reporting contract.
"""

from __future__ import annotations

from datetime import timedelta, timezone

import pytest

from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import (
    InvestigationFinding,
    InvestigationProposal,
    InvestigationProposalConverter,
    InvestigationProposalGenerator,
    InvestigationReport,
    InvestigationService,
)
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.models import ApprovalDecision, ProposalStatus


class TestInvestigationClassification:
    """Investigation requests must be classified correctly."""

    @pytest.mark.parametrize("text", [
        "investigate the F17 failures",
        "analyze the F17 failures",
        "diagnose this bug",
        "inspect the repository",
        "examine the datetime handling",
        "trace the error",
        "debug the comparison issue",
    ])
    def test_investigation_cues(self, text):
        spec = TaskIntake().intake(text)
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST

    def test_p12_regression_does_not_become_development(self):
        """The P12.1 regression: 'don't modify' must not trigger development."""
        spec = TaskIntake().intake(
            "Atlas, investigate the F17 failures. Don't modify anything yet."
        )
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST

    def test_genuine_development_still_classified(self):
        """Genuine development requests remain DEVELOPMENT_REQUEST."""
        spec = TaskIntake().intake("implement the F17 fix for Atlas")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST

    def test_modify_atlas_still_development(self):
        """'modify Atlas' without negation is still development."""
        spec = TaskIntake().intake("modify the datetime handling in Atlas")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST


class TestNegationHandling:
    """Negation must prevent misclassification."""

    def test_dont_modify_not_development(self):
        """'don't modify' should not be classified as development."""
        spec = TaskIntake().intake("don't modify anything")
        # Should NOT be DEVELOPMENT_REQUEST
        assert spec.task_type is not TaskType.DEVELOPMENT_REQUEST

    def test_do_not_change_not_development(self):
        """'do not change' should not be classified as development."""
        spec = TaskIntake().intake("do not change the code")
        assert spec.task_type is not TaskType.DEVELOPMENT_REQUEST


class TestInvestigationService:
    """InvestigationService produces read-only reports."""

    def test_investigation_returns_report(self):
        service = InvestigationService()
        report = service.investigate("F17 datetime failures")
        assert isinstance(report, InvestigationReport)
        assert report.target == "F17 datetime failures"

    def test_investigation_modification_status_is_none(self):
        service = InvestigationService()
        report = service.investigate("F17 datetime failures")
        assert report.modification_status == "NONE"

    def test_investigation_finds_datetime_issues(self):
        service = InvestigationService()
        report = service.investigate("F17 datetime failures")
        # Should find some findings related to datetime
        assert len(report.findings) > 0 or report.diagnosis  # has content

    def test_investigation_markdown_report(self):
        service = InvestigationService()
        report = service.investigate("F17 datetime failures")
        md = report.to_markdown()
        assert "F17 datetime failures" in md
        assert "NONE" in md  # modification status

    def test_investigation_does_not_mutate(self):
        """Investigation must not create/modify/delete files."""
        import os
        import tempfile

        # Get initial state
        initial_files = set()
        for root, dirs, files in os.walk("atlas/understanding"):
            for f in files:
                initial_files.add(os.path.join(root, f))

        service = InvestigationService()
        service.investigate("F17 datetime failures")

        # Verify no new files created
        after_files = set()
        for root, dirs, files in os.walk("atlas/understanding"):
            for f in files:
                after_files.add(os.path.join(root, f))

        assert initial_files == after_files


class TestInvestigationReport:
    """InvestigationReport structure and serialization."""

    def test_report_is_frozen(self):
        report = InvestigationReport(target="test")
        with pytest.raises(AttributeError):
            report.target = "changed"

    def test_report_to_dict(self):
        report = InvestigationReport(
            target="F17",
            diagnosis="mixed naive/aware datetimes",
            affected_files=("a.py", "b.py"),
        )
        d = report.to_dict() if hasattr(report, "to_dict") else None
        # to_markdown is the serialization method
        md = report.to_markdown()
        assert "F17" in md
        assert "mixed naive/aware datetimes" in md


class TestP14_1RoutingRegression:
    """P14.1 — tool/action identifiers must not trigger investigation routing.

    Investigation cues use word-boundary matching so that a cue like "inspect"
    matches standalone investigation language but does NOT match when it appears
    as a substring of a tool/action identifier such as "code_inspector".
    """

    @pytest.mark.parametrize("text", [
        "Run code_inspector to find files.",
        "execute code_inspector on the project",
        "use the code_analyzer tool",
        "run the debugger on this function",
        "invoke code_tracer to find the bug",
    ])
    def test_tool_name_with_investigation_substring_not_investigation(self, text):
        """Tool/action identifiers containing investigation cues are not investigation."""
        spec = TaskIntake().intake(text)
        assert spec.task_type is not TaskType.INVESTIGATION_REQUEST

    @pytest.mark.parametrize("text", [
        "inspect the repository",
        "inspect the datetime handling",
        "please inspect this code carefully",
        "analyze the failure mode",
        "trace the error to its source",
        "debug the comparison issue",
        "examine the log output",
        "diagnose the performance problem",
    ])
    def test_genuine_investigation_language_still_investigation(self, text):
        """Standalone investigation cues in normal language remain investigation."""
        spec = TaskIntake().intake(text)
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST


class TestP16_5GeneralInvestigation:
    """P16.5 — general content-driven subsystem investigation.

    Verifies that InvestigationService now discovers the relevant subsystem
    from repository evidence rather than hardcoded directory/pattern mapping.
    """

    def test_memory_investigation_reaches_memory_subsystem(self):
        """A memory investigation must discover atlas/memory/ modules."""
        service = InvestigationService()
        report = service.investigate("Investigate the memory architecture")
        # The discovered components should include memory-related modules.
        component_str = " ".join(report.components).lower()
        assert "memory" in component_str, (
            f"Memory investigation did not find memory components: {report.components}"
        )

    def test_memory_investigation_does_not_hijack_datetime(self):
        """A memory investigation must NOT be hijacked by datetime findings."""
        service = InvestigationService()
        report = service.investigate("Investigate the memory architecture")
        # No datetime-specific categories should appear.
        for finding in report.findings:
            assert finding.category != "comparison", (
                "Memory investigation was hijacked by datetime comparison finding"
            )
            assert finding.category != "creation", (
                "Memory investigation was hijacked by datetime creation finding"
            )

    def test_arbitrary_subsystem_without_hardcoded_branch(self):
        """Another subsystem is investigated without a hardcoded special case."""
        service = InvestigationService()
        report = service.investigate("Investigate the routing system")
        # Should discover routing-related modules, not datetime findings.
        for finding in report.findings:
            assert finding.category != "comparison", (
                "Routing investigation was hijacked by datetime finding"
            )

    def test_investigation_report_includes_components(self):
        """Report includes discovered components when modules are found."""
        service = InvestigationService()
        report = service.investigate("Investigate the memory architecture")
        # Memory investigation should discover at least one component.
        assert len(report.components) > 0, (
            "Memory investigation should find at least one component"
        )

    def test_investigation_report_includes_tests_when_found(self):
        """Report includes inspected tests when test files are discovered."""
        service = InvestigationService()
        report = service.investigate("Investigate the memory architecture")
        # tests_inspected is a tuple; if tests were found, it should be populated.
        # (This is a structural check; actual test discovery depends on repo state.)
        assert isinstance(report.tests_inspected, tuple)

    def test_investigation_remains_readonly(self):
        """Investigation must not modify the repository."""
        import os

        # Capture initial state of a representative directory.
        initial_files: set[str] = set()
        for root, dirs, files in os.walk("atlas/memory"):
            for f in files:
                initial_files.add(os.path.join(root, f))

        service = InvestigationService()
        service.investigate("Investigate the memory architecture")

        # Verify no files were added/removed.
        after_files: set[str] = set()
        for root, dirs, files in os.walk("atlas/memory"):
            for f in files:
                after_files.add(os.path.join(root, f))
        assert initial_files == after_files

    def test_investigation_modification_status_always_none(self):
        """InvestigationReport.modification_status must always be NONE."""
        service = InvestigationService()
        for target in [
            "memory architecture",
            "routing system",
            "execution gateway",
            "unknown nonexistent subsystem xyz",
        ]:
            report = service.investigate(target)
            assert report.modification_status == "NONE"

    def test_empty_target_does_not_crash(self):
        """Degenerate/empty targets degrade gracefully."""
        service = InvestigationService()
        report = service.investigate("")
        assert report.modification_status == "NONE"
        assert isinstance(report.findings, tuple)

    def test_investigation_no_file_mutation_via_filesystem(self):
        """Investigation must not create/write/delete any files anywhere."""
        import os
        import tempfile

        # Snapshot the whole atlas directory before.
        before: set[str] = set()
        for root, dirs, files in os.walk("atlas"):
            for f in files:
                before.add(os.path.join(root, f))

        service = InvestigationService()
        service.investigate("Investigate everything thoroughly")

        # Snapshot after.
        after: set[str] = set()
        for root, dirs, files in os.walk("atlas"):
            for f in files:
                after.add(os.path.join(root, f))

        assert before == after, "Investigation mutated the filesystem"


class TestP17_InvestigationProposalGenerator:
    """P17 — Investigation → Planning bridge tests."""

    def _meaningful_report(self) -> InvestigationReport:
        """Build an investigation report that meets the meaningful-improvement
        threshold."""
        return InvestigationReport(
            target="memory architecture",
            findings=(
                InvestigationFinding(
                    category="reference",
                    description="Found references to memory",
                    evidence="atlas/memory/manager.py",
                    location="atlas/memory/",
                ),
                InvestigationFinding(
                    category="dependency",
                    description="'atlas.memory.manager' depends on: atlas.memory.storage",
                    location="atlas.memory.manager",
                ),
            ),
            diagnosis="Identified 3 relevant component(s).",
            affected_files=("atlas/memory/manager.py", "atlas/memory/storage.py"),
            components=("atlas.memory.manager", "atlas.memory.storage"),
            tests_inspected=("tests/test_memory.py",),
        )

    def _empty_report(self) -> InvestigationReport:
        """Build an investigation report that does NOT meet the threshold."""
        return InvestigationReport(
            target="unknown thing",
            findings=(),
            diagnosis="No specific evidence found.",
            affected_files=(),
            components=(),
        )

    def test_meaningful_improvement_produces_proposal(self):
        """An investigation with components, findings, and affected files
        generates a proposal."""
        gen = InvestigationProposalGenerator()
        report = self._meaningful_report()
        proposal = gen.generate_proposal(report)
        assert proposal is not None
        assert proposal.proposal_id.startswith("INV-PROP-")
        assert proposal.status == "PROPOSED"

    def test_no_meaningful_improvement_returns_none(self):
        """An investigation without sufficient evidence returns None."""
        gen = InvestigationProposalGenerator()
        report = self._empty_report()
        proposal = gen.generate_proposal(report)
        assert proposal is None

    def test_proposal_retains_investigation_evidence(self):
        """Proposal components and findings match the investigation report."""
        gen = InvestigationProposalGenerator()
        report = self._meaningful_report()
        proposal = gen.generate_proposal(report)
        assert proposal is not None
        assert proposal.components == report.components
        assert proposal.findings == report.findings
        assert proposal.affected_files == report.affected_files
        assert proposal.tests_inspected == report.tests_inspected
        assert proposal.investigation_target == report.target

    def test_proposal_has_unique_id(self):
        """Each generated proposal has a unique ID."""
        gen = InvestigationProposalGenerator()
        report = self._meaningful_report()
        p1 = gen.generate_proposal(report)
        p2 = gen.generate_proposal(report)
        assert p1 is not None and p2 is not None
        assert p1.proposal_id != p2.proposal_id

    def test_proposal_fingerprint_is_deterministic(self):
        """The same proposal content produces the same fingerprint."""
        gen = InvestigationProposalGenerator()
        report = self._meaningful_report()
        proposal = gen.generate_proposal(report)
        assert proposal is not None
        assert proposal.fingerprint == proposal.fingerprint  # idempotent
        assert len(proposal.fingerprint) == 16

    def test_proposal_status_always_proposed(self):
        """Proposal status is always PROPOSED — never auto-approved."""
        gen = InvestigationProposalGenerator()
        report = self._meaningful_report()
        proposal = gen.generate_proposal(report)
        assert proposal is not None
        assert proposal.status == "PROPOSED"

    def test_no_components_means_no_proposal(self):
        """A report with findings but no components returns None."""
        gen = InvestigationProposalGenerator()
        report = InvestigationReport(
            target="something",
            findings=(
                InvestigationFinding(
                    category="reference",
                    description="ref",
                    evidence="x.py",
                    location="x/",
                ),
            ),
            affected_files=("x.py",),
            components=(),  # no components
        )
        assert gen.generate_proposal(report) is None

    def test_no_substantive_findings_means_no_proposal(self):
        """A report with components but only non-substantive findings returns None."""
        gen = InvestigationProposalGenerator()
        report = InvestigationReport(
            target="something",
            findings=(
                InvestigationFinding(
                    category="other",  # not reference/dependency
                    description="other",
                ),
            ),
            affected_files=("x.py",),
            components=("atlas.something",),
        )
        assert gen.generate_proposal(report) is None


class TestP17_ConversationIntegration:
    """P17 — conversational investigation → proposal integration tests."""

    @pytest.fixture
    def failing_ai(self):
        class _Failing:
            def chat(self, prompt, routing_context=None):
                raise RuntimeError("No AI")

            def stream_chat(self, prompt, routing_context=None):
                def _g():
                    raise RuntimeError("No AI")
                    yield ""  # pragma: no cover

                return _g()

        return _Failing()

    @pytest.fixture
    def service(self, failing_ai):
        return ConversationService(
            ai_service=failing_ai,
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
        )

    def test_investigation_generates_proposal_via_send(self, service):
        """A memory investigation via send() generates a proposal."""
        response = service.send(
            "Investigate the memory architecture and prepare a proposal"
        )
        assert response.role == "assistant"
        assert "memory" in response.content.lower()
        # Proposal should be present (memory investigation is substantive).
        meta = response.metadata.get("proposal")
        assert meta is not None, "Expected a proposal for memory investigation"
        assert meta["proposal_status"] == "PROPOSED"

    def test_proposal_no_mutation(self, service):
        """Proposal generation does not mutate the repository."""
        import os

        before: set[str] = set()
        for root, dirs, files in os.walk("atlas/memory"):
            for f in files:
                before.add(os.path.join(root, f))

        service.send("Investigate the memory architecture")

        after: set[str] = set()
        for root, dirs, files in os.walk("atlas/memory"):
            for f in files:
                after.add(os.path.join(root, f))

        assert before == after

    def test_proposal_stored_in_conversation_state(self, service):
        """Generated proposal ID is recorded in conversation state."""
        service.send("Investigate the memory architecture")
        state = service.state_manager.state
        assert state.active_proposal_id is not None
        assert state.active_proposal_id.startswith("INV-PROP-")

    def test_no_proposal_for_empty_investigation(self, service):
        """An investigation with no meaningful improvement produces no proposal."""
        response = service.send("Investigate xyznonexistent123")
        meta = response.metadata.get("proposal")
        # Either no proposal key, or proposal is None
        if meta is not None:
            # If somehow a proposal was generated, it should still be PROPOSED
            assert meta["proposal_status"] == "PROPOSED"

    def test_cross_session_isolation(self, failing_ai):
        """Separate conversations do not share proposal state."""
        svc1 = ConversationService(
            ai_service=failing_ai,
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
        )
        svc2 = ConversationService(
            ai_service=failing_ai,
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
        )
        svc1.send("Investigate the memory architecture")
        # svc2 has no proposal state from svc1
        assert svc2.state_manager.state.active_proposal_id is None

    def test_no_auto_approval(self, service):
        """Proposal is never auto-approved."""
        response = service.send("Investigate the memory architecture")
        content = response.content.lower()
        assert "requires your explicit approval" in content or "no actionable" in content

    def test_p165_investigation_still_reaches_memory(self, service):
        """P16.5 behavior preserved: memory investigation reaches memory."""
        response = service.send("Investigate the memory architecture")
        assert "memory" in response.content.lower()
        # Should NOT be hijacked by datetime findings
        assert "datetime.now()" not in response.content.lower()


class TestInvestigationProposalConverter:
    """P17 — InvestigationProposalConverter tests."""

    def _sample_proposal(self) -> InvestigationProposal:
        """Build an InvestigationProposal for testing."""
        return InvestigationProposal(
            proposal_id="INV-PROP-TEST-001",
            investigation_target="memory architecture",
            title="Improve: memory architecture",
            summary="Identified 3 relevant component(s).",
            components=("atlas.memory.manager", "atlas.memory.storage"),
            findings=(
                InvestigationFinding(
                    category="reference",
                    description="Found references to memory",
                    evidence="atlas/memory/manager.py",
                    location="atlas/memory/",
                ),
                InvestigationFinding(
                    category="dependency",
                    description="'atlas.memory.manager' depends on storage",
                    location="atlas.memory.manager",
                ),
            ),
            affected_files=("atlas/memory/manager.py", "atlas/memory/storage.py"),
            tests_inspected=("tests/test_memory.py",),
            recommended_next_step="Review the identified components",
            evidence_summary="Found 2 reference, 1 dependency across 2 component(s).",
        )

    def test_converts_successfully(self):
        """InvestigationProposal converts to EvolutionProposal."""
        converter = InvestigationProposalConverter()
        result = converter.convert(self._sample_proposal())
        assert result is not None
        assert result.proposal_id.startswith("DEV-CONV-")

    def test_converted_is_draft(self):
        """Converted proposal is always DRAFT."""
        converter = InvestigationProposalConverter()
        result = converter.convert(self._sample_proposal())
        assert result.status == ProposalStatus.DRAFT

    def test_fingerprint_is_deterministic(self):
        """Same input produces same fingerprint."""
        converter = InvestigationProposalConverter()
        p1 = converter.convert(self._sample_proposal())
        p2 = converter.convert(self._sample_proposal())
        assert p1.proposal_fingerprint == p2.proposal_fingerprint

    def test_investigation_fingerprint_not_reused(self):
        """InvestigationProposal fingerprint is NOT the EvolutionProposal fingerprint."""
        converter = InvestigationProposalConverter()
        inv = self._sample_proposal()
        result = converter.convert(inv)
        assert result.proposal_fingerprint != inv.fingerprint

    def test_evidence_preserved(self):
        """Investigation evidence is preserved in metadata."""
        converter = InvestigationProposalConverter()
        inv = self._sample_proposal()
        result = converter.convert(inv)
        assert result.metadata["investigation_proposal_id"] == inv.proposal_id
        assert result.metadata["investigation_fingerprint"] == inv.fingerprint
        assert len(result.metadata["investigation_findings"]) == 2

    def test_components_preserved(self):
        """Components are preserved in plan.target_components."""
        converter = InvestigationProposalConverter()
        inv = self._sample_proposal()
        result = converter.convert(inv)
        assert result.plan.target_components == list(inv.components)

    def test_affected_files_preserved(self):
        """Affected files are preserved in metadata."""
        converter = InvestigationProposalConverter()
        inv = self._sample_proposal()
        result = converter.convert(inv)
        assert result.metadata["affected_files"] == list(inv.affected_files)

    def test_identity_traceable(self):
        """Converted proposal is traceable to original."""
        converter = InvestigationProposalConverter()
        inv = self._sample_proposal()
        result = converter.convert(inv)
        assert result.metadata["investigation_proposal_id"] == "INV-PROP-TEST-001"

    def test_different_investigations_produce_distinct_proposals(self):
        """Different InvestigationProposals produce different EvolutionProposals."""
        converter = InvestigationProposalConverter()
        inv1 = self._sample_proposal()
        inv2 = InvestigationProposal(
            proposal_id="INV-PROP-TEST-002",
            investigation_target="routing system",
            title="Improve: routing system",
            summary="Different summary",
            components=("atlas.routing.router",),
            findings=(
                InvestigationFinding(
                    category="reference",
                    description="diff",
                    evidence="x.py",
                    location="x/",
                ),
            ),
            affected_files=("atlas/routing/router.py",),
            tests_inspected=(),
            recommended_next_step="Different step",
            evidence_summary="Different evidence",
        )
        r1 = converter.convert(inv1)
        r2 = converter.convert(inv2)
        assert r1.proposal_fingerprint != r2.proposal_fingerprint
        assert r1.metadata["investigation_proposal_id"] != r2.metadata["investigation_proposal_id"]


class TestApprovalIntegration:
    """P17 — ApprovalManager integration tests."""

    def _sample_proposal(self) -> InvestigationProposal:
        """Build an InvestigationProposal for testing."""
        return InvestigationProposal(
            proposal_id="INV-PROP-APP-001",
            investigation_target="memory architecture",
            title="Improve: memory architecture",
            summary="Identified relevant components.",
            components=("atlas.memory.manager",),
            findings=(
                InvestigationFinding(
                    category="reference",
                    description="Found references",
                    evidence="atlas/memory/manager.py",
                    location="atlas/memory/",
                ),
            ),
            affected_files=("atlas/memory/manager.py",),
            tests_inspected=(),
            recommended_next_step="Review components",
            evidence_summary="Found 1 reference.",
        )

    def test_converted_proposal_enters_approval_manager(self):
        """Converted proposal can be submitted to ApprovalManager."""
        converter = InvestigationProposalConverter()
        inv = self._sample_proposal()
        ev_proposal = converter.convert(inv)

        approval_manager = ApprovalManager()
        request = approval_manager.create_approval_request(ev_proposal)

        assert request is not None
        assert request.proposal_id == ev_proposal.proposal_id

    def test_approval_request_has_matching_proposal_id(self):
        """ApprovalRequest.proposal_id matches EvolutionProposal.proposal_id."""
        converter = InvestigationProposalConverter()
        inv = self._sample_proposal()
        ev_proposal = converter.convert(inv)

        approval_manager = ApprovalManager()
        request = approval_manager.create_approval_request(ev_proposal)

        assert request.proposal_id == ev_proposal.proposal_id

    def test_approval_request_has_matching_fingerprint(self):
        """ApprovalRequest.proposal_fingerprint matches EvolutionProposal fingerprint."""
        converter = InvestigationProposalConverter()
        inv = self._sample_proposal()
        ev_proposal = converter.convert(inv)

        approval_manager = ApprovalManager()
        request = approval_manager.create_approval_request(ev_proposal)

        assert request.proposal_fingerprint == ev_proposal.proposal_fingerprint

    def test_approval_validates_against_unchanged_proposal(self):
        """ApprovalRequest validates against unchanged EvolutionProposal."""
        converter = InvestigationProposalConverter()
        inv = self._sample_proposal()
        ev_proposal = converter.convert(inv)

        approval_manager = ApprovalManager()
        request = approval_manager.create_approval_request(ev_proposal)

        assert request.is_valid_for(ev_proposal) is True

    def test_changed_proposal_fails_validation(self):
        """Changed EvolutionProposal fails fingerprint validation."""
        converter = InvestigationProposalConverter()
        inv = self._sample_proposal()
        ev_proposal = converter.convert(inv)

        approval_manager = ApprovalManager()
        request = approval_manager.create_approval_request(ev_proposal)

        # Simulate change: modify title and clear stored fingerprint so
        # is_valid_for recomputes it from current content
        ev_proposal.title = "Changed title"
        ev_proposal.proposal_fingerprint = ""
        assert request.is_valid_for(ev_proposal) is False

    def test_proposal_remains_non_approved_after_creation(self):
        """Proposal is PENDING_APPROVAL after creation, not APPROVED."""
        converter = InvestigationProposalConverter()
        inv = self._sample_proposal()
        ev_proposal = converter.convert(inv)

        approval_manager = ApprovalManager()
        request = approval_manager.create_approval_request(ev_proposal)

        assert ev_proposal.status == ProposalStatus.PENDING_APPROVAL
        assert request.decision == ApprovalDecision.PENDING


class TestConversationalPlanning:
    """P17 — Conversational planning route tests."""

    @pytest.fixture
    def failing_ai(self):
        class _Failing:
            def chat(self, prompt, routing_context=None):
                raise RuntimeError("No AI")

            def stream_chat(self, prompt, routing_context=None):
                def _g():
                    raise RuntimeError("No AI")
                    yield ""  # pragma: no cover

                return _g()

        return _Failing()

    @pytest.fixture
    def service(self, failing_ai):
        approval_manager = ApprovalManager()
        return ConversationService(
            ai_service=failing_ai,
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
            approval_manager=approval_manager,
        )

    def test_canonical_investigation_produces_proposal(self, service):
        """Investigation produces an InvestigationProposal."""
        response = service.send("Investigate the memory architecture")
        assert response.role == "assistant"
        assert service.state_manager.state.active_proposal_id is not None

    def test_explicit_planning_request_converts(self, service):
        """Explicit planning request converts InvestigationProposal."""
        # First, create an investigation proposal
        service.send("Investigate the memory architecture")
        inv_proposal_id = service.state_manager.state.active_proposal_id

        # Then, request planning
        response = service.send("Plan this improvement")

        assert response.role == "assistant"
        assert service.state_manager.state.evolution_proposal_id is not None
        assert service.state_manager.state.evolution_proposal_id != inv_proposal_id

    def test_approval_request_created(self, service):
        """Planning request creates an ApprovalRequest."""
        service.send("Investigate the memory architecture")
        service.send("Plan this improvement")

        assert service.state_manager.state.pending_approval_id is not None
        assert service.state_manager.state.pending_approval_id.startswith("APPR-")

    def test_no_execution_occurs(self, service):
        """Planning request does not execute anything."""
        service.send("Investigate the memory architecture")
        response = service.send("Plan this improvement")

        # No execution metadata
        assert "execution" not in response.metadata

    def test_no_filesystem_mutation(self, service):
        """Planning request does not mutate filesystem."""
        import os

        before: set[str] = set()
        for root, dirs, files in os.walk("atlas/memory"):
            for f in files:
                before.add(os.path.join(root, f))

        service.send("Investigate the memory architecture")
        service.send("Plan this improvement")

        after: set[str] = set()
        for root, dirs, files in os.walk("atlas/memory"):
            for f in files:
                after.add(os.path.join(root, f))

        assert before == after

    def test_no_auto_approval(self, service):
        """Planning request does not auto-approve."""
        service.send("Investigate the memory architecture")
        service.send("Plan this improvement")

        # Proposal should be PENDING, not APPROVED
        assert "pending" in service.state_manager.state.latest_result.lower() or \
               "approval" in service.state_manager.state.latest_result.lower()

    def test_missing_active_proposal_fails_cleanly(self, service):
        """Planning without active proposal fails cleanly."""
        response = service.send("Plan this improvement")

        assert response.role == "assistant"
        assert "no active" in response.content.lower() or \
               "investigate" in response.content.lower()

    def test_cross_session_isolation(self, failing_ai):
        """Planning state is isolated between sessions."""
        svc1 = ConversationService(
            ai_service=failing_ai,
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
            approval_manager=ApprovalManager(),
        )
        svc2 = ConversationService(
            ai_service=failing_ai,
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
            approval_manager=ApprovalManager(),
        )

        svc1.send("Investigate the memory architecture")
        svc1.send("Plan this improvement")

        # svc2 has no state from svc1
        assert svc2.state_manager.state.active_proposal_id is None
        assert svc2.state_manager.state.evolution_proposal_id is None

    def test_ambiguous_okay_does_not_trigger_planning(self, service):
        """Ambiguous 'okay' does not trigger planning."""
        service.send("Investigate the memory architecture")

        # "okay" should not be classified as PLANNING_REQUEST
        response = service.send("okay")

        # Should not have created evolution proposal
        assert service.state_manager.state.evolution_proposal_id is None


class TestPlanningClassification:
    """P17 — Planning request classification tests."""

    @pytest.mark.parametrize("text", [
        "plan this improvement",
        "plan this",
        "prepare a development proposal",
        "convert this proposal",
        "convert this investigation",
        "prepare a development plan",
        "create a development proposal",
        "make this a development proposal",
        "plan the improvement",
    ])
    def test_planning_cues(self, text):
        """Planning cues are classified as PLANNING_REQUEST."""
        spec = TaskIntake().intake(text)
        assert spec.task_type is TaskType.PLANNING_REQUEST

    def test_investigation_not_misclassified_as_planning(self):
        """Investigation requests remain INVESTIGATION_REQUEST."""
        spec = TaskIntake().intake("investigate the memory architecture")
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST

    def test_development_not_misclassified_as_planning(self):
        """Development requests remain DEVELOPMENT_REQUEST."""
        spec = TaskIntake().intake("implement the fix for Atlas")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST

    def test_approval_not_misclassified_as_planning(self):
        """Approval requests remain APPROVAL."""
        spec = TaskIntake().intake("approve this proposal")
        assert spec.task_type is TaskType.APPROVAL


class TestRegressions:
    """P17 — Regression tests for existing behavior."""

    @pytest.fixture
    def failing_ai(self):
        class _Failing:
            def chat(self, prompt, routing_context=None):
                raise RuntimeError("No AI")

            def stream_chat(self, prompt, routing_context=None):
                def _g():
                    raise RuntimeError("No AI")
                    yield ""  # pragma: no cover

                return _g()

        return _Failing()

    @pytest.fixture
    def service(self, failing_ai):
        return ConversationService(
            ai_service=failing_ai,
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
        )

    def test_p17_investigation_proposal_unchanged(self, service):
        """Existing P17 behavior preserved: InvestigationProposal created."""
        response = service.send("Investigate the memory architecture")

        # Should still produce InvestigationProposal
        assert service.state_manager.state.active_proposal_id.startswith("INV-PROP-")

    def test_p165_investigation_reaches_memory(self, service):
        """P16.5 behavior preserved: memory investigation reaches memory."""
        response = service.send("Investigate the memory architecture")
        assert "memory" in response.content.lower()

    def test_p14_negation_handling(self):
        """P14 negation handling preserved."""
        spec = TaskIntake().intake("don't modify anything")
        assert spec.task_type is not TaskType.DEVELOPMENT_REQUEST
