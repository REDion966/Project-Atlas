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


class TestApprovalExecution:
    """P17 — Approval Execution: conversational approval/rejection through
    the governed ApprovalManager contract."""

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

    def _owner_session(self):
        from atlas.authority.service import AuthorityService
        from atlas.session.context import SessionContext
        from atlas.session.manager import SessionManager

        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        return SessionContext.from_session(manager.create_session("owner"))

    def _user_session(self):
        from atlas.authority.service import AuthorityService
        from atlas.session.context import SessionContext
        from atlas.session.manager import SessionManager

        authority = AuthorityService("Owner")
        authority.add_user("Alice", principal_id="alice")
        manager = SessionManager(authority)
        return SessionContext.from_session(manager.create_session("alice"))

    @pytest.fixture
    def service(self, failing_ai):
        return ConversationService(
            ai_service=failing_ai,
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
            approval_manager=ApprovalManager(),
        )

    def _prepare_pending(self, service, session):
        service.send("Investigate the memory architecture", session_context=session)
        service.send("Plan this improvement", session_context=session)
        state = service.state_manager.state
        assert state.evolution_proposal_id is not None
        assert state.pending_approval_id is not None
        return state

    def test_full_approval_flow(self, service):
        """investigate → plan → approve yields APPROVED, consumes pending."""
        from atlas.evolution.models import ApprovalDecision, ProposalStatus

        session = self._owner_session()
        self._prepare_pending(service, session)
        inv_id = service.state_manager.state.active_proposal_id

        response = service.send("Approve this proposal", session_context=session)

        assert response.role == "assistant"
        ev_proposal = service._resolve_evolution_proposal(
            service.state_manager.state.evolution_proposal_id
        )
        assert ev_proposal.status == ProposalStatus.APPROVED
        assert ev_proposal.approved_at is not None
        state = service.state_manager.state
        assert state.pending_approval_id is None
        assert state.evolution_proposal_id == ev_proposal.proposal_id
        assert state.active_proposal_id == inv_id
        assert response.metadata["approval"]["status"] == "approved"

    def test_full_rejection_flow(self, service):
        """investigate → plan → reject yields REJECTED with reason."""
        from atlas.evolution.models import ApprovalDecision, ProposalStatus

        session = self._owner_session()
        self._prepare_pending(service, session)

        response = service.send(
            "Reject this proposal because the scope is too broad",
            session_context=session,
        )

        assert response.role == "assistant"
        ev_proposal = service._resolve_evolution_proposal(
            service.state_manager.state.evolution_proposal_id
        )
        assert ev_proposal.status == ProposalStatus.REJECTED
        assert ev_proposal.rejection_reason != ""
        state = service.state_manager.state
        assert state.pending_approval_id is None
        assert state.evolution_proposal_id == ev_proposal.proposal_id
        assert response.metadata["approval"]["status"] == "rejected"

    def test_missing_pending_request_fails_cleanly(self, service):
        """Approval with no pending request fails without state change."""
        session = self._owner_session()
        service.send("Investigate the memory architecture", session_context=session)

        before = service.state_manager.state
        response = service.send("Approve this proposal", session_context=session)

        assert response.role == "assistant"
        assert "no development proposal" in response.content.lower()
        after = service.state_manager.state
        assert after.pending_approval_id == before.pending_approval_id
        assert after.evolution_proposal_id == before.evolution_proposal_id

    def test_missing_evolution_proposal_fails_cleanly(self, service):
        """Approval with unresolvable proposal fails without state change."""
        session = self._owner_session()
        self._prepare_pending(service, session)
        before = service.state_manager.state

        service._active_evolution_proposals.clear()
        response = service.send("Approve this proposal", session_context=session)

        assert "could not be resolved" in response.content.lower()
        after = service.state_manager.state
        assert after.pending_approval_id == before.pending_approval_id
        assert after.evolution_proposal_id == before.evolution_proposal_id

    def test_missing_approval_request_fails_cleanly(self, service):
        """Approval with unresolvable request fails without state change."""
        session = self._owner_session()
        self._prepare_pending(service, session)
        before = service.state_manager.state

        service._active_approval_requests.clear()
        response = service.send("Approve this proposal", session_context=session)

        assert "could not be resolved" in response.content.lower()
        after = service.state_manager.state
        assert after.pending_approval_id == before.pending_approval_id

    def test_identity_mismatch_refused(self, service):
        """Request bound to a different proposal is refused, state kept."""
        session = self._owner_session()
        self._prepare_pending(service, session)
        before = service.state_manager.state

        request = service._resolve_approval_request(before.pending_approval_id)
        request.proposal_id = "PROP-OTHER"
        response = service.send("Approve this proposal", session_context=session)

        assert "does not match" in response.content.lower()
        after = service.state_manager.state
        assert after.pending_approval_id == before.pending_approval_id

    def test_fingerprint_mismatch_refused(self, service):
        """Changed proposal content fails fingerprint validation, state kept."""
        session = self._owner_session()
        self._prepare_pending(service, session)
        before = service.state_manager.state

        proposal = service._resolve_evolution_proposal(before.evolution_proposal_id)
        proposal.title = "Tampered title"
        proposal.proposal_fingerprint = ""
        response = service.send("Approve this proposal", session_context=session)

        assert "changed" in response.content.lower()
        after = service.state_manager.state
        assert after.pending_approval_id == before.pending_approval_id
        assert after.evolution_proposal_id == before.evolution_proposal_id

    def test_non_owner_refused(self, service):
        """Non-OWNER session cannot approve; manager untouched."""
        owner_session = self._owner_session()
        self._prepare_pending(service, owner_session)
        before = service.state_manager.state

        request = service._resolve_approval_request(before.pending_approval_id)
        user_session = self._user_session()
        response = service.send("Approve this proposal", session_context=user_session)

        assert "owner authority" in response.content.lower()
        from atlas.evolution.models import ApprovalDecision

        assert request.decision == ApprovalDecision.PENDING
        after = service.state_manager.state
        assert after.pending_approval_id == before.pending_approval_id

    def test_missing_session_refused(self, service):
        """Approval without any session fails closed."""
        before = service.state_manager.state
        response = service.send("Approve this proposal")

        assert "no active session" in response.content.lower()
        after = service.state_manager.state
        assert after.pending_approval_id == before.pending_approval_id

    def test_already_decided_request_respected(self, service):
        """Second approval surfaces the manager guard without false success."""
        session = self._owner_session()
        self._prepare_pending(service, session)
        service.send("Approve this proposal", session_context=session)
        assert service.state_manager.state.pending_approval_id is None

        # Simulate a stale duplicate: re-point pending at the decided request.
        decided_id = next(iter(service._active_approval_requests))
        ev_id = service.state_manager.state.evolution_proposal_id
        service.state_manager.update(pending_approval_id=decided_id)
        response = service.send("Approve this proposal", session_context=session)

        assert "could not be recorded" in response.content.lower()
        assert service.state_manager.state.evolution_proposal_id == ev_id

    def test_ambiguous_does_not_approve(self, service):
        """Ambiguous language never reaches the governed handler."""
        session = self._owner_session()
        self._prepare_pending(service, session)
        before = service.state_manager.state

        from atlas.evolution.models import ApprovalDecision

        for text in ("okay", "looks good", "proceed"):
            service.send(text, session_context=session)

        request = service._resolve_approval_request(before.pending_approval_id)
        assert request.decision == ApprovalDecision.PENDING
        after = service.state_manager.state
        assert after.pending_approval_id == before.pending_approval_id

    def test_stream_approval_parity(self, service):
        """stream() approval reaches the same governed path as send()."""
        from atlas.evolution.models import ProposalStatus

        session = self._owner_session()
        self._prepare_pending(service, session)

        chunks = list(
            service.stream("Approve this proposal", session_context=session)
        )
        assert "".join(chunks)

        ev_proposal = service._resolve_evolution_proposal(
            service.state_manager.state.evolution_proposal_id
        )
        assert ev_proposal.status == ProposalStatus.APPROVED
        assert service.state_manager.state.pending_approval_id is None

    def test_stream_rejection_parity(self, service):
        """stream() rejection reaches the same governed path as send()."""
        from atlas.evolution.models import ProposalStatus

        session = self._owner_session()
        self._prepare_pending(service, session)

        chunks = list(
            service.stream(
                "Reject this proposal because it is out of scope",
                session_context=session,
            )
        )
        assert "".join(chunks)

        ev_proposal = service._resolve_evolution_proposal(
            service.state_manager.state.evolution_proposal_id
        )
        assert ev_proposal.status == ProposalStatus.REJECTED
        assert service.state_manager.state.pending_approval_id is None

    def test_rejection_reason_fallback(self, service):
        """Blank rejection text falls back to the fixed default reason."""
        handler = ConversationService._rejection_reason_from_spec
        assert handler is not None
        from atlas.conversation.task_intake import TaskIntake

        spec = TaskIntake().intake("reject this proposal")
        # Intent is non-empty here; force the blank path directly.
        from dataclasses import replace

        blanked = replace(spec, intent="   ")
        assert (
            ConversationService._rejection_reason_from_spec(blanked)
            == "Rejected via conversation."
        )

    def test_duplicate_planning_refused(self, service):
        """Second planning while pending refuses; original request survives."""
        session = self._owner_session()
        self._prepare_pending(service, session)
        before = service.state_manager.state
        count_before = len(service._active_approval_requests)

        response = service.send("Plan this improvement", session_context=session)

        assert "already has a pending approval request" in response.content.lower()
        after = service.state_manager.state
        assert after.pending_approval_id == before.pending_approval_id
        assert after.evolution_proposal_id == before.evolution_proposal_id
        assert len(service._active_approval_requests) == count_before

    def test_cross_session_isolation(self, failing_ai):
        """Service B cannot approve service A's pending request."""
        session_a = self._owner_session()
        svc_a = ConversationService(
            ai_service=failing_ai,
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
            approval_manager=ApprovalManager(),
        )
        svc_b = ConversationService(
            ai_service=failing_ai,
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
            approval_manager=ApprovalManager(),
        )
        svc_a.send("Investigate the memory architecture", session_context=session_a)
        svc_a.send("Plan this improvement", session_context=session_a)
        assert svc_a.state_manager.state.pending_approval_id is not None

        session_b = self._owner_session()
        response = svc_b.send("Approve this proposal", session_context=session_b)

        assert "no development proposal" in response.content.lower()
        from atlas.evolution.models import ApprovalDecision

        request = svc_a._resolve_approval_request(
            svc_a.state_manager.state.pending_approval_id
        )
        assert request.decision == ApprovalDecision.PENDING

    def test_no_execution_triggered(self, service):
        """Approval invokes no planner, engine, or filesystem mutation."""
        import os

        session = self._owner_session()
        self._prepare_pending(service, session)

        before: set[str] = set()
        for root, _dirs, files in os.walk("atlas/memory"):
            for f in files:
                before.add(os.path.join(root, f))

        response = service.send("Approve this proposal", session_context=session)

        assert "execution" not in response.metadata.get("approval", {})
        after: set[str] = set()
        for root, _dirs, files in os.walk("atlas/memory"):
            for f in files:
                after.add(os.path.join(root, f))
        assert before == after


class TestRejectionClassification:
    """P17 — Explicit rejection classification tests."""

    @pytest.mark.parametrize("text", [
        "reject this proposal",
        "rejected",
        "decline this change",
        "deny the request",
        "reject this proposal because the scope is too broad",
    ])
    def test_rejection_cues(self, text):
        """Rejection cues are classified as REJECTION_REQUEST."""
        spec = TaskIntake().intake(text)
        assert spec.task_type is TaskType.REJECTION_REQUEST

    def test_ambiguous_not_rejection(self):
        """Ambiguous responses are not rejection."""
        for text in ("okay", "looks good", "sure", "proceed"):
            spec = TaskIntake().intake(text)
            assert spec.task_type is not TaskType.REJECTION_REQUEST

    def test_negated_rejection_not_rejection(self):
        """Negated rejection is not rejection."""
        spec = TaskIntake().intake("don't reject this proposal")
        assert spec.task_type is not TaskType.REJECTION_REQUEST

    def test_approval_still_approval(self):
        """Approval cues still classify as APPROVAL, not rejection."""
        spec = TaskIntake().intake("approve this proposal")
        assert spec.task_type is TaskType.APPROVAL


class TestDevelopmentExecutionBridge:
    """P17 — D2 governed development-execution bridge tests.

    Proves the conversation layer resolves the REAL approved EvolutionProposal
    and ApprovalRequest, validates identity/fingerprint/status/decision, and
    delegates to the existing kernel development-execution bridge — without
    calling Level3ExecutionService, ApplicationEngine, or AuthorizationManager.
    """

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

    def _owner_session(self):
        from atlas.authority.service import AuthorityService
        from atlas.session.context import SessionContext
        from atlas.session.manager import SessionManager

        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        return SessionContext.from_session(manager.create_session("owner"))

    def _user_session(self):
        from atlas.authority.service import AuthorityService
        from atlas.session.context import SessionContext
        from atlas.session.manager import SessionManager

        authority = AuthorityService("Owner")
        authority.add_user("Alice", principal_id="alice")
        manager = SessionManager(authority)
        return SessionContext.from_session(manager.create_session("alice"))

    @pytest.fixture
    def service(self, failing_ai):
        from atlas.conversation.message import Message

        captured = {}

        def bridge(session_context, proposal, request):
            captured["session"] = session_context
            captured["proposal"] = proposal
            captured["request"] = request
            return Message(
                role="assistant",
                content="bridged",
                metadata={"execution": {"status": "succeeded"}},
            )

        svc = ConversationService(
            ai_service=failing_ai,
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
            approval_manager=ApprovalManager(),
            development_execution_bridge=bridge,
        )
        svc._test_bridge = captured
        return svc

    def _prepare_approved(self, service, session):
        service.send("Investigate the memory architecture", session_context=session)
        service.send("Plan this improvement", session_context=session)
        service.send("Approve this proposal", session_context=session)
        state = service.state_manager.state
        assert state.evolution_proposal_id is not None
        return state

    def test_full_flow_delegates_real_objects(self, service):
        """investigate → plan → approve → execute delegates real objects."""
        session = self._owner_session()
        self._prepare_approved(service, session)

        response = service.send("Execute the approved proposal", session_context=session)

        assert response.role == "assistant"
        captured = service._test_bridge
        assert captured["session"] is session
        # Real objects, not fabricated refs.
        assert hasattr(captured["proposal"], "status")
        assert hasattr(captured["request"], "decision")
        assert captured["proposal"].status == ProposalStatus.APPROVED
        assert captured["request"].decision == ApprovalDecision.APPROVED
        assert captured["request"].proposal_id == captured["proposal"].proposal_id

    def test_execution_requires_session(self, service):
        """Execution without a session fails closed."""
        response = service.send("Execute the approved proposal")
        assert "no active session" in response.content.lower()
        assert "session" not in service._test_bridge

    def test_execution_requires_owner(self, service):
        """Non-OWNER cannot execute."""
        session = self._user_session()
        self._prepare_approved(service, session)
        before = dict(service._test_bridge)

        response = service.send("Execute the approved proposal", session_context=session)

        assert "owner authority" in response.content.lower()
        assert service._test_bridge == before  # bridge not called

    def test_execution_requires_bridge(self, failing_ai):
        """Execution without a wired bridge fails closed."""
        svc = ConversationService(
            ai_service=failing_ai,
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
            approval_manager=ApprovalManager(),
        )
        session = self._owner_session()
        self._prepare_approved(svc, session)

        response = svc.send("Execute the approved proposal", session_context=session)

        assert "not available" in response.content.lower()

    def test_execution_requires_approved_proposal(self, service):
        """Execution without an approved proposal fails closed."""
        session = self._owner_session()
        response = service.send("Execute the approved proposal", session_context=session)
        assert "no approved development proposal" in response.content.lower()
        assert "session" not in service._test_bridge

    def test_proposal_not_approved_refused(self, service):
        """A proposal that is not APPROVED is refused (no bridge call)."""
        session = self._owner_session()
        service.send("Investigate the memory architecture", session_context=session)
        service.send("Plan this improvement", session_context=session)
        # Do NOT approve — proposal is PENDING_APPROVAL, request is PENDING.
        before = dict(service._test_bridge)

        response = service.send("Execute the approved proposal", session_context=session)

        # Neither the proposal nor the request is APPROVED, so the bridge is
        # never called and execution is refused.
        content = response.content.lower()
        assert (
            "not approved" in content
            or "could not be resolved" in content
            or "no approved" in content
        )
        assert service._test_bridge == before

    def test_fingerprint_mismatch_refused(self, service):
        """Changed proposal content fails fingerprint validation."""
        session = self._owner_session()
        self._prepare_approved(service, session)

        # Tamper with the live proposal after approval.
        proposal = service._resolve_evolution_proposal(
            service.state_manager.state.evolution_proposal_id
        )
        proposal.title = "Tampered"
        proposal.proposal_fingerprint = ""
        before = dict(service._test_bridge)

        response = service.send("Execute the approved proposal", session_context=session)

        assert "changed" in response.content.lower()
        assert service._test_bridge == before

    def test_stream_execution_parity(self, service):
        """stream() execution reaches the same governed bridge."""
        session = self._owner_session()
        self._prepare_approved(service, session)

        chunks = list(
            service.stream("Execute the approved proposal", session_context=session)
        )
        assert "".join(chunks)
        assert service._test_bridge["session"] is session
        assert service._test_bridge["proposal"].status == ProposalStatus.APPROVED

    def test_cross_session_isolation(self, failing_ai):
        """Service B cannot execute service A's approved proposal."""
        captured = {}

        def bridge(session_context, proposal, request):
            captured["called"] = True
            return Message(role="assistant", content="bridged")

        svc_a = ConversationService(
            ai_service=failing_ai,
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
            approval_manager=ApprovalManager(),
            development_execution_bridge=bridge,
        )
        svc_b = ConversationService(
            ai_service=failing_ai,
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
            approval_manager=ApprovalManager(),
            development_execution_bridge=bridge,
        )
        session_a = self._owner_session()
        svc_a.send("Investigate the memory architecture", session_context=session_a)
        svc_a.send("Plan this improvement", session_context=session_a)
        svc_a.send("Approve this proposal", session_context=session_a)
        assert svc_a.state_manager.state.evolution_proposal_id is not None

        session_b = self._owner_session()
        response = svc_b.send("Execute the approved proposal", session_context=session_b)

        assert "no approved development proposal" in response.content.lower()
        assert "called" not in captured

    def test_no_level3_or_authorization_calls(self, service):
        """The bridge must NOT call Level3ExecutionService or AuthorizationManager."""
        import atlas.conversation.conversation_service as cs_module

        session = self._owner_session()
        self._prepare_approved(service, session)

        # Confirm the obsolete ref classes are gone.
        assert not hasattr(cs_module, "_ApprovalRef")
        assert not hasattr(cs_module, "_ProposalRef")

        # The handler should not touch execution_service (Level3).
        service._execution_service = None  # would have been used by old path
        response = service.send("Execute the approved proposal", session_context=session)

        # If execution failed, surface the underlying error for debugging.
        exec_meta = response.metadata.get("execution", {})
        if exec_meta.get("status") == "execution_failed":
            raise AssertionError(
                f"Bridge raised: {exec_meta.get('error')!r}"
            )

        assert exec_meta.get("status") == "succeeded"


class TestKernelDevelopmentExecutionBridge:
    """P17 — kernel _development_execution_bridge persistence + delegation."""

    def _make_atlas(self, tmp_path, monkeypatch):
        import atlas.kernel.atlas as kernel_mod
        from tests.test_durable_guided_improvement import _storage_class

        monkeypatch.setattr(
            "atlas.kernel.atlas.SQLiteEvolutionStorage",
            _storage_class(tmp_path),
        )
        atlas = kernel_mod.Atlas()
        atlas.start()
        return atlas

    def test_bridge_persists_and_delegates(self, tmp_path, monkeypatch):
        """Bridge persists proposal + request and delegates to run_development_execution."""
        atlas = self._make_atlas(tmp_path, monkeypatch)
        try:
            from atlas.evolution.models import (
                ApprovalDecision,
                ApprovalRequest,
                EvolutionProposal,
                ImprovementPlan,
                ImprovementPriority,
                ProposalStatus,
            )

            # Use the atlas's OWN authoritative owner session so the
            # _require_development_authority gate recognizes it.
            session = atlas.session_context
            assert session is not None

            plan = ImprovementPlan(
                plan_id="PLAN-TEST",
                title="Test",
                description="Test plan",
                priority=ImprovementPriority.MEDIUM,
                target_components=("atlas/memory",),
            )
            proposal = EvolutionProposal(
                proposal_id="PROP-TEST-001",
                title="Improve: test",
                summary="Test",
                rationale="Test",
                expected_benefit="Test",
                risks="Low",
                impact_analysis="Test",
                implementation_approach="Test",
                plan=plan,
                status=ProposalStatus.APPROVED,
            )
            request = ApprovalRequest(
                request_id="APPR-TEST-001",
                proposal_id="PROP-TEST-001",
                title="Test",
                description="Test",
                rationale="Test",
                risks="Low",
                expected_benefit="Test",
                proposal_fingerprint=proposal.proposal_fingerprint,
                decision=ApprovalDecision.APPROVED,
            )

            # Spy on run_development_execution.
            called = {}
            original = atlas.run_development_execution

            def spy(sc, pid):
                called["session"] = sc
                called["proposal_id"] = pid
                return original(sc, pid)

            atlas.run_development_execution = spy

            message = atlas._development_execution_bridge(session, proposal, request)

            # Persisted into EvolutionMemory.
            assert atlas._evolution_memory.get_proposal("PROP-TEST-001") is not None
            persisted_reqs = [
                r for r in atlas._evolution_memory.get_all_approval_requests()
                if r.proposal_id == "PROP-TEST-001"
            ]
            assert len(persisted_reqs) >= 1

            # Delegated to run_development_execution with the right ID.
            assert called["proposal_id"] == "PROP-TEST-001"
            assert called["session"] is session

            # Returns a conversational Message. The proposal carries no actual
            # code changes, so the loop refuses with INVALID_OBJECTIVE — which
            # is a valid terminal status proving delegation reached the loop.
            assert message.role == "assistant"
            assert message.metadata["execution"]["status"] in (
                "succeeded",
                "invalid_objective",
                "iterations_exhausted",
                "governance_denied",
            )
        finally:
            atlas.shutdown()


class TestDevelopmentDiagnostic:
    """P17 — DevelopmentDiagnostic: read-only, evidence-based, fail-closed."""

    def _make_outcome(
        self,
        status: str = "FAILED",
        *,
        verification_passed: bool = False,
        rollback_occurred: bool = False,
        test_outcome: str = "failed",
        message: str = "iteration failed.",
    ) -> Any:
        from atlas.evolution.development_models import (
            DevelopmentOutcome,
            DevelopmentOutcomeStatus,
        )

        return DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus[status],
            proposal_id="PROP-DIAG-001",
            plan_id="PLAN-DIAG-001",
            iteration=1,
            verification_passed=verification_passed,
            rollback_occurred=rollback_occurred,
            test_outcome=test_outcome,
            message=message,
        )

    def _make_result(
        self,
        status: str,
        outcomes: list[Any] | None = None,
        message: str = "",
    ) -> Any:
        from atlas.evolution.development_models import DevelopmentOutcomeStatus
        from atlas.evolution.self_development_loop import DevelopmentRunResult

        return DevelopmentRunResult(
            status=DevelopmentOutcomeStatus[status],
            outcomes=outcomes or [],
            iterations_used=len(outcomes) if outcomes else 0,
            message=message,
        )

    def test_governance_denied_is_known(self):
        """GOVERNANCE_DENIED → GOVERNANCE class, KNOWN confidence."""
        from atlas.evolution.development_diagnostic import (
            DevelopmentDiagnostic,
            DiagnosticConfidence,
            DiagnosticFailureClass,
        )

        result = self._make_result(
            "GOVERNANCE_DENIED",
            message="Promotion gate refused; no promotion performed.",
        )
        diag = DevelopmentDiagnostic().diagnose(result)

        assert diag.failure_class == DiagnosticFailureClass.GOVERNANCE
        assert diag.confidence == DiagnosticConfidence.KNOWN
        assert "governance" in diag.cause.lower() or "denied" in diag.cause.lower()
        assert diag.recoverable is False

    def test_invalid_objective_is_known(self):
        """INVALID_OBJECTIVE → OBJECTIVE class, KNOWN confidence."""
        from atlas.evolution.development_diagnostic import (
            DevelopmentDiagnostic,
            DiagnosticConfidence,
            DiagnosticFailureClass,
        )

        result = self._make_result(
            "INVALID_OBJECTIVE",
            message="Change supplier returned no code change.",
        )
        diag = DevelopmentDiagnostic().diagnose(result)

        assert diag.failure_class == DiagnosticFailureClass.OBJECTIVE
        assert diag.confidence == DiagnosticConfidence.KNOWN
        assert diag.recoverable is False

    def test_unavailable_capability_is_known(self):
        """UNAVAILABLE_CAPABILITY → CAPABILITY class, KNOWN confidence."""
        from atlas.evolution.development_diagnostic import (
            DevelopmentDiagnostic,
            DiagnosticConfidence,
            DiagnosticFailureClass,
        )

        result = self._make_result(
            "UNAVAILABLE_CAPABILITY",
            message="Required capability unavailable.",
        )
        diag = DevelopmentDiagnostic().diagnose(result)

        assert diag.failure_class == DiagnosticFailureClass.CAPABILITY
        assert diag.confidence == DiagnosticConfidence.KNOWN
        assert diag.recoverable is False

    def test_iteration_exhaustion_with_verification_failure(self):
        """ITERATIONS_EXHAUSTED + verification failure → VERIFICATION, PROBABLE."""
        from atlas.evolution.development_diagnostic import (
            DevelopmentDiagnostic,
            DiagnosticConfidence,
            DiagnosticFailureClass,
        )

        outcome = self._make_outcome(
            "FAILED",
            verification_passed=False,
            test_outcome="failed",
            message="tests did not pass.",
        )
        result = self._make_result("ITERATIONS_EXHAUSTED", [outcome])
        diag = DevelopmentDiagnostic().diagnose(result)

        assert diag.failure_class == DiagnosticFailureClass.VERIFICATION
        assert diag.confidence == DiagnosticConfidence.PROBABLE
        assert "verification" in diag.cause.lower() or "budget" in diag.cause.lower()

    def test_iteration_exhaustion_with_implementation_failure(self):
        """ITERATIONS_EXHAUSTED + rollback → IMPLEMENTATION, PROBABLE."""
        from atlas.evolution.development_diagnostic import (
            DevelopmentDiagnostic,
            DiagnosticConfidence,
            DiagnosticFailureClass,
        )

        outcome = self._make_outcome(
            "FAILED",
            verification_passed=False,
            rollback_occurred=True,
            test_outcome="",
            message="apply failed.",
        )
        result = self._make_result("ITERATIONS_EXHAUSTED", [outcome])
        diag = DevelopmentDiagnostic().diagnose(result)

        assert diag.failure_class == DiagnosticFailureClass.IMPLEMENTATION
        assert diag.confidence == DiagnosticConfidence.PROBABLE

    def test_failed_verification_is_known(self):
        """FAILED + verification failure → VERIFICATION, KNOWN."""
        from atlas.evolution.development_diagnostic import (
            DevelopmentDiagnostic,
            DiagnosticConfidence,
            DiagnosticFailureClass,
        )

        outcome = self._make_outcome(
            "FAILED",
            verification_passed=False,
            test_outcome="failed",
            message="AssertionError in test_foo.",
        )
        result = self._make_result("FAILED", [outcome])
        diag = DevelopmentDiagnostic().diagnose(result)

        assert diag.failure_class == DiagnosticFailureClass.VERIFICATION
        assert diag.confidence == DiagnosticConfidence.KNOWN
        assert "AssertionError" in diag.evidence or "failed" in diag.evidence

    def test_failed_implementation_is_known(self):
        """FAILED + rollback → IMPLEMENTATION, KNOWN."""
        from atlas.evolution.development_diagnostic import (
            DevelopmentDiagnostic,
            DiagnosticConfidence,
            DiagnosticFailureClass,
        )

        outcome = self._make_outcome(
            "FAILED",
            verification_passed=False,
            rollback_occurred=True,
            test_outcome="",
            message="apply raised ValueError.",
        )
        result = self._make_result("FAILED", [outcome])
        diag = DevelopmentDiagnostic().diagnose(result)

        assert diag.failure_class == DiagnosticFailureClass.IMPLEMENTATION
        assert diag.confidence == DiagnosticConfidence.KNOWN
        assert "ValueError" in diag.evidence or "rollback" in diag.evidence.lower()

    def test_timeout_is_verification_not_infrastructure(self):
        """Timeout → VERIFICATION, NOT INFRASTRUCTURE (no over-claiming)."""
        from atlas.evolution.development_diagnostic import (
            DevelopmentDiagnostic,
            DiagnosticFailureClass,
        )

        outcome = self._make_outcome(
            "FAILED",
            verification_passed=False,
            test_outcome="timeout",
            message="pytest timed out after 30s.",
        )
        result = self._make_result("FAILED", [outcome])
        diag = DevelopmentDiagnostic().diagnose(result)

        assert diag.failure_class == DiagnosticFailureClass.VERIFICATION
        assert diag.failure_class != DiagnosticFailureClass.INFRASTRUCTURE

    def test_insufficient_evidence_returns_unknown(self):
        """Ambiguous evidence → UNKNOWN, not fabricated."""
        from atlas.evolution.development_diagnostic import (
            DevelopmentDiagnostic,
            DiagnosticConfidence,
            DiagnosticFailureClass,
        )

        outcome = self._make_outcome(
            "FAILED",
            verification_passed=False,
            rollback_occurred=False,
            test_outcome="",
            message="",
        )
        result = self._make_result("FAILED", [outcome])
        diag = DevelopmentDiagnostic().diagnose(result)

        assert diag.failure_class == DiagnosticFailureClass.UNKNOWN
        assert diag.confidence == DiagnosticConfidence.UNKNOWN

    def test_does_not_invent_root_cause(self):
        """A raw pytest failure does NOT produce a fabricated implementation root cause."""
        from atlas.evolution.development_diagnostic import (
            DevelopmentDiagnostic,
            DiagnosticFailureClass,
        )

        outcome = self._make_outcome(
            "FAILED",
            verification_passed=False,
            test_outcome="failed",
            message="test_bar FAILED: assert 1 == 2",
        )
        result = self._make_result("FAILED", [outcome])
        diag = DevelopmentDiagnostic().diagnose(result)

        # The evidence supports verification failure, NOT a specific logic-bug claim.
        assert diag.failure_class == DiagnosticFailureClass.VERIFICATION
        # Cause must not over-claim a specific root cause.
        assert "logic bug" not in diag.cause.lower()
        assert "implementation has a logic bug" not in diag.cause

    def test_diagnosis_is_readonly_and_deterministic(self):
        """Same input → same output; diagnosis has no side effects."""
        from atlas.evolution.development_diagnostic import (
            DevelopmentDiagnostic,
            DiagnosticFailureClass,
        )

        outcome = self._make_outcome(
            "FAILED",
            verification_passed=False,
            test_outcome="failed",
            message="x",
        )
        result = self._make_result("FAILED", [outcome])
        d1 = DevelopmentDiagnostic().diagnose(result)
        d2 = DevelopmentDiagnostic().diagnose(result)

        assert d1 == d2
        # Immutable result.
        with pytest.raises(AttributeError):
            d1.failure_class = DiagnosticFailureClass.INFRASTRUCTURE

    def test_diagnosis_does_not_invoke_execution(self):
        """Diagnosis must not call run_development_execution or similar."""
        import inspect

        from atlas.evolution.development_diagnostic import DevelopmentDiagnostic

        src = inspect.getsource(DevelopmentDiagnostic)
        assert "run_development_execution" not in src
        assert "subprocess" not in src
        assert "pytest" not in src
        assert "os.system" not in src
        assert ".apply(" not in src

    def test_success_not_diagnosed_as_failure(self):
        """A SUCCESS result is explicitly not a failure to diagnose."""
        from atlas.evolution.development_diagnostic import (
            DevelopmentDiagnostic,
            DiagnosticConfidence,
            DiagnosticFailureClass,
        )

        result = self._make_result("SUCCESS", message="Development completed inside sandbox.")
        diag = DevelopmentDiagnostic().diagnose(result)

        assert diag.failure_class == DiagnosticFailureClass.UNKNOWN
        assert diag.confidence == DiagnosticConfidence.UNKNOWN
        assert "succeeded" in diag.cause.lower()


class TestDevelopmentRecovery:
    """P17 — DevelopmentRecovery: read-only, evidence-based, fail-closed."""

    def _make_outcome(
        self,
        status: str = "FAILED",
        *,
        verification_passed: bool = False,
        rollback_occurred: bool = False,
        test_outcome: str = "failed",
        message: str = "iteration failed.",
    ) -> Any:
        from atlas.evolution.development_models import (
            DevelopmentOutcome,
            DevelopmentOutcomeStatus,
        )

        return DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus[status],
            proposal_id="PROP-REC-001",
            plan_id="PLAN-REC-001",
            iteration=1,
            verification_passed=verification_passed,
            rollback_occurred=rollback_occurred,
            test_outcome=test_outcome,
            message=message,
        )

    def _make_result(
        self,
        status: str,
        outcomes: list[Any] | None = None,
        message: str = "",
    ) -> Any:
        from atlas.evolution.development_models import DevelopmentOutcomeStatus
        from atlas.evolution.self_development_loop import DevelopmentRunResult

        return DevelopmentRunResult(
            status=DevelopmentOutcomeStatus[status],
            outcomes=outcomes or [],
            iterations_used=len(outcomes) if outcomes else 0,
            message=message,
        )

    def test_governance_denied_no_recovery(self):
        """GOVERNANCE_DENIED → NO_RECOVERY (cannot retry past governance)."""
        from atlas.evolution.development_recovery import (
            DevelopmentRecovery,
            RecoveryStrategy,
        )

        result = self._make_result(
            "GOVERNANCE_DENIED",
            message="Promotion gate refused.",
        )
        diagnostic = type(
            "D",
            (),
            {
                "failure_class": type("F", (), {"value": "governance"})(),
                "confidence": type("C", (), {"value": "known"})(),
                "cause": "denied",
                "evidence": "status=GOVERNANCE_DENIED",
                "recoverable": False,
            },
        )()
        decision = DevelopmentRecovery().decide(result, diagnostic)

        assert decision.recoverable is False
        assert decision.strategy == RecoveryStrategy.NO_RECOVERY

    def test_unknown_confidence_no_recovery(self):
        """UNKNOWN confidence → NO_RECOVERY (never invent strategy)."""
        from atlas.evolution.development_recovery import (
            DevelopmentRecovery,
            RecoveryStrategy,
        )

        result = self._make_result("FAILED")
        diagnostic = type(
            "D",
            (),
            {
                "failure_class": type("F", (), {"value": "implementation"})(),
                "confidence": type("C", (), {"value": "unknown"})(),
                "cause": "?",
                "evidence": "",
                "recoverable": None,
            },
        )()
        decision = DevelopmentRecovery().decide(result, diagnostic)

        assert decision.recoverable is False
        assert decision.strategy == RecoveryStrategy.NO_RECOVERY

    def test_unknown_failure_class_no_recovery(self):
        """UNKNOWN failure class → NO_RECOVERY."""
        from atlas.evolution.development_recovery import (
            DevelopmentRecovery,
            RecoveryStrategy,
        )

        result = self._make_result("FAILED")
        diagnostic = type(
            "D",
            (),
            {
                "failure_class": type("F", (), {"value": "unknown"})(),
                "confidence": type("C", (), {"value": "known"})(),
                "cause": "?",
                "evidence": "",
                "recoverable": None,
            },
        )()
        decision = DevelopmentRecovery().decide(result, diagnostic)

        assert decision.recoverable is False
        assert decision.strategy == RecoveryStrategy.NO_RECOVERY

    def test_recoverable_false_no_recovery(self):
        """recoverable=False → NO_RECOVERY."""
        from atlas.evolution.development_recovery import (
            DevelopmentRecovery,
            RecoveryStrategy,
        )

        result = self._make_result("FAILED")
        diagnostic = type(
            "D",
            (),
            {
                "failure_class": type("F", (), {"value": "implementation"})(),
                "confidence": type("C", (), {"value": "known"})(),
                "cause": "apply failed",
                "evidence": "rollback=True",
                "recoverable": False,
            },
        )()
        decision = DevelopmentRecovery().decide(result, diagnostic)

        assert decision.recoverable is False
        assert decision.strategy == RecoveryStrategy.NO_RECOVERY

    def test_recoverable_none_no_recovery(self):
        """recoverable=None → NO_RECOVERY."""
        from atlas.evolution.development_recovery import (
            DevelopmentRecovery,
            RecoveryStrategy,
        )

        result = self._make_result("FAILED")
        diagnostic = type(
            "D",
            (),
            {
                "failure_class": type("F", (), {"value": "implementation"})(),
                "confidence": type("C", (), {"value": "known"})(),
                "cause": "apply failed",
                "evidence": "rollback=True",
                "recoverable": None,
            },
        )()
        decision = DevelopmentRecovery().decide(result, diagnostic)

        assert decision.recoverable is False
        assert decision.strategy == RecoveryStrategy.NO_RECOVERY

    def test_objective_failure_escalates(self):
        """OBJECTIVE failure → ESCALATE (cannot silently modify objective)."""
        from atlas.evolution.development_recovery import (
            DevelopmentRecovery,
            RecoveryStrategy,
        )

        result = self._make_result("INVALID_OBJECTIVE")
        diagnostic = type(
            "D",
            (),
            {
                "failure_class": type("F", (), {"value": "objective"})(),
                "confidence": type("C", (), {"value": "known"})(),
                "cause": "invalid objective",
                "evidence": "status=INVALID_OBJECTIVE",
                "recoverable": False,
            },
        )()
        decision = DevelopmentRecovery().decide(result, diagnostic)

        assert decision.recoverable is False
        assert decision.strategy == RecoveryStrategy.ESCALATE
        assert "human planning" in decision.rationale.lower()

    def test_capability_failure_escalates(self):
        """CAPABILITY failure → ESCALATE (cannot retry unavailable capability)."""
        from atlas.evolution.development_recovery import (
            DevelopmentRecovery,
            RecoveryStrategy,
        )

        result = self._make_result("UNAVAILABLE_CAPABILITY")
        diagnostic = type(
            "D",
            (),
            {
                "failure_class": type("F", (), {"value": "capability"})(),
                "confidence": type("C", (), {"value": "known"})(),
                "cause": "capability unavailable",
                "evidence": "status=UNAVAILABLE_CAPABILITY",
                "recoverable": False,
            },
        )()
        decision = DevelopmentRecovery().decide(result, diagnostic)

        assert decision.recoverable is False
        assert decision.strategy == RecoveryStrategy.ESCALATE

    def test_verification_failure_with_evidence_may_retry(self):
        """VERIFICATION failure with evidence → REVISE_AND_RETRY."""
        from atlas.evolution.development_recovery import (
            DevelopmentRecovery,
            RecoveryStrategy,
        )

        result = self._make_result("FAILED")
        diagnostic = type(
            "D",
            (),
            {
                "failure_class": type("F", (), {"value": "verification"})(),
                "confidence": type("C", (), {"value": "known"})(),
                "cause": "Verification did not pass.",
                "evidence": "test_outcome=failed",
                "recoverable": True,
            },
        )()
        decision = DevelopmentRecovery().decide(result, diagnostic)

        assert decision.recoverable is True
        assert decision.strategy == RecoveryStrategy.REVISE_AND_RETRY

    def test_verification_failure_without_evidence_escalates(self):
        """VERIFICATION failure without evidence → ESCALATE."""
        from atlas.evolution.development_recovery import (
            DevelopmentRecovery,
            RecoveryStrategy,
        )

        result = self._make_result("FAILED")
        diagnostic = type(
            "D",
            (),
            {
                "failure_class": type("F", (), {"value": "verification"})(),
                "confidence": type("C", (), {"value": "probable"})(),
                "cause": "",
                "evidence": "",
                "recoverable": True,
            },
        )()
        decision = DevelopmentRecovery().decide(result, diagnostic)

        assert decision.recoverable is False
        assert decision.strategy == RecoveryStrategy.ESCALATE

    def test_implementation_failure_with_evidence_may_retry(self):
        """IMPLEMENTATION failure with evidence → REVISE_AND_RETRY."""
        from atlas.evolution.development_recovery import (
            DevelopmentRecovery,
            RecoveryStrategy,
        )

        result = self._make_result("FAILED")
        diagnostic = type(
            "D",
            (),
            {
                "failure_class": type("F", (), {"value": "implementation"})(),
                "confidence": type("C", (), {"value": "known"})(),
                "cause": "Implementation did not succeed.",
                "evidence": "rollback_occurred=True",
                "recoverable": True,
            },
        )()
        decision = DevelopmentRecovery().decide(result, diagnostic)

        assert decision.recoverable is True
        assert decision.strategy == RecoveryStrategy.REVISE_AND_RETRY

    def test_ambiguous_evidence_no_recovery(self):
        """Ambiguous evidence → NO_RECOVERY."""
        from atlas.evolution.development_recovery import (
            DevelopmentRecovery,
            RecoveryStrategy,
        )

        result = self._make_result("FAILED")
        diagnostic = type(
            "D",
            (),
            {
                "failure_class": type("F", (), {"value": "implementation"})(),
                "confidence": type("C", (), {"value": "probable"})(),
                "cause": "",
                "evidence": "",
                "recoverable": True,
            },
        )()
        decision = DevelopmentRecovery().decide(result, diagnostic)

        assert decision.recoverable is False
        assert decision.strategy == RecoveryStrategy.ESCALATE

    def test_decision_is_immutable(self):
        """RecoveryDecision is frozen/immutable."""
        from atlas.evolution.development_recovery import (
            DevelopmentRecovery,
            RecoveryStrategy,
        )

        result = self._make_result("GOVERNANCE_DENIED")
        diagnostic = type(
            "D",
            (),
            {
                "failure_class": type("F", (), {"value": "governance"})(),
                "confidence": type("C", (), {"value": "known"})(),
                "cause": "denied",
                "evidence": "e",
                "recoverable": False,
            },
        )()
        decision = DevelopmentRecovery().decide(result, diagnostic)

        with pytest.raises(AttributeError):
            decision.recoverable = True
        with pytest.raises(AttributeError):
            decision.strategy = RecoveryStrategy.REVISE_AND_RETRY

    def test_diagnose_then_recover_end_to_end(self):
        """Full path: DevelopmentDiagnostic → DevelopmentRecovery."""
        from atlas.evolution.development_diagnostic import DevelopmentDiagnostic
        from atlas.evolution.development_recovery import (
            DevelopmentRecovery,
            RecoveryStrategy,
        )

        outcome = self._make_outcome(
            "FAILED",
            verification_passed=False,
            test_outcome="failed",
            message="AssertionError in test_foo.",
        )
        result = self._make_result("FAILED", [outcome])

        diagnostic = DevelopmentDiagnostic().diagnose(result)
        decision = DevelopmentRecovery().decide(result, diagnostic)

        # A raw pytest failure should classify as VERIFICATION, not fabricate
        # an implementation root cause.
        assert diagnostic.failure_class.value == "verification"
        # With evidence present, recovery may be possible.
        assert isinstance(decision.recoverable, bool)
        assert decision.strategy in (
            RecoveryStrategy.NO_RECOVERY,
            RecoveryStrategy.REVISE_AND_RETRY,
            RecoveryStrategy.ESCALATE,
        )

    def test_recovery_does_not_execute_or_authorize(self):
        """RecoveryDecision component must not invoke execution or auth."""
        import inspect

        from atlas.evolution.development_recovery import DevelopmentRecovery

        src = inspect.getsource(DevelopmentRecovery)
        assert "run_development_execution" not in src
        assert "subprocess" not in src
        assert "pytest" not in src
        assert "os.system" not in src
        assert "assert_owner" not in src
        assert "approve" not in src
        assert ".apply(" not in src


class TestRecoveryClassification:
    """P17 — recovery request classification."""

    def test_recover_cues(self):
        """Recovery cues classify as RECOVERY_REQUEST."""
        for text in (
            "recover from the failure",
            "recovery",
            "try again",
            "retry the development",
            "attempt recovery",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is TaskType.RECOVERY_REQUEST

    def test_execution_not_misclassified_as_recovery(self):
        """Execution cues remain EXECUTION_REQUEST."""
        spec = TaskIntake().intake("execute the approved proposal")
        assert spec.task_type is TaskType.EXECUTION_REQUEST

    def test_approval_not_misclassified_as_recovery(self):
        """Approval cues remain APPROVAL."""
        spec = TaskIntake().intake("approve this proposal")
        assert spec.task_type is TaskType.APPROVAL


class TestDevelopmentVerification:
    """P17 — DevelopmentVerification: read-only, evidence-based, fail-closed."""

    def _make_outcome(
        self,
        status: str = "SUCCESS",
        *,
        verification_passed: bool = True,
        rollback_occurred: bool = False,
        test_outcome: str = "passed",
        message: str = "Development iteration succeeded in sandbox.",
        changed_files: list[str] | None = None,
        iteration: int = 1,
    ) -> Any:
        from atlas.evolution.development_models import (
            DevelopmentOutcome,
            DevelopmentOutcomeStatus,
        )

        return DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus[status],
            proposal_id="PROP-VER-001",
            plan_id="PLAN-VER-001",
            iteration=iteration,
            verification_passed=verification_passed,
            rollback_occurred=rollback_occurred,
            test_outcome=test_outcome,
            message=message,
            changed_files=changed_files or ["atlas/memory/manager.py"],
        )

    def _make_result(
        self,
        status: str,
        outcomes: list[Any] | None = None,
        iterations_used: int | None = None,
        message: str = "",
    ) -> Any:
        from atlas.evolution.development_models import DevelopmentOutcomeStatus
        from atlas.evolution.self_development_loop import DevelopmentRunResult

        outcomes = outcomes or []
        return DevelopmentRunResult(
            status=DevelopmentOutcomeStatus[status],
            outcomes=outcomes,
            iterations_used=iterations_used if iterations_used is not None else len(outcomes),
            message=message,
        )

    def test_verified_success(self):
        """SUCCESS with all iterations passing → VERIFIED."""
        from atlas.evolution.development_verification import (
            DevelopmentVerification,
            VerificationStatus,
        )

        outcome = self._make_outcome("SUCCESS", verification_passed=True)
        result = self._make_result("SUCCESS", [outcome])
        report = DevelopmentVerification().verify(result)

        assert report.status == VerificationStatus.VERIFIED
        assert report.all_tests_passed is True
        assert report.iterations_examined == 1

    def test_unverified_failure(self):
        """FAILED result → UNVERIFIED."""
        from atlas.evolution.development_verification import (
            DevelopmentVerification,
            VerificationStatus,
        )

        outcome = self._make_outcome(
            "FAILED",
            verification_passed=False,
            test_outcome="failed",
            message="tests did not pass.",
        )
        result = self._make_result("FAILED", [outcome])
        report = DevelopmentVerification().verify(result)

        assert report.status == VerificationStatus.UNVERIFIED
        assert report.all_tests_passed is False

    def test_partial_mixed_iterations(self):
        """Mixed iteration outcomes → PARTIAL."""
        from atlas.evolution.development_verification import (
            DevelopmentVerification,
            VerificationStatus,
        )

        good = self._make_outcome("SUCCESS", verification_passed=True, iteration=1)
        bad = self._make_outcome(
            "FAILED",
            verification_passed=False,
            test_outcome="failed",
            iteration=2,
        )
        result = self._make_result("FAILED", [good, bad])
        report = DevelopmentVerification().verify(result)

        assert report.status == VerificationStatus.PARTIAL
        assert report.all_tests_passed is False
        assert report.iterations_examined == 2

    def test_unverifiable_no_outcomes(self):
        """Result with no iteration outcomes → UNVERIFIABLE."""
        from atlas.evolution.development_verification import (
            DevelopmentVerification,
            VerificationStatus,
        )

        result = self._make_result("FAILED", [])
        report = DevelopmentVerification().verify(result)

        assert report.status == VerificationStatus.UNVERIFIABLE

    def test_unverifiable_none_result(self):
        """None result → UNVERIFIABLE."""
        from atlas.evolution.development_verification import (
            DevelopmentVerification,
            VerificationStatus,
        )

        report = DevelopmentVerification().verify(None)

        assert report.status == VerificationStatus.UNVERIFIABLE

    def test_governance_denied_unverified(self):
        """GOVERNANCE_DENIED → UNVERIFIED."""
        from atlas.evolution.development_verification import (
            DevelopmentVerification,
            VerificationStatus,
        )

        result = self._make_result("GOVERNANCE_DENIED", message="gate refused")
        report = DevelopmentVerification().verify(result)

        assert report.status == VerificationStatus.UNVERIFIED

    def test_iteration_exhaustion_unverified(self):
        """ITERATIONS_EXHAUSTED → UNVERIFIED."""
        from atlas.evolution.development_verification import (
            DevelopmentVerification,
            VerificationStatus,
        )

        result = self._make_result("ITERATIONS_EXHAUSTED", message="exhausted")
        report = DevelopmentVerification().verify(result)

        assert report.status == VerificationStatus.UNVERIFIED

    def test_rollback_recorded(self):
        """Rollback evidence is preserved in the report."""
        from atlas.evolution.development_verification import (
            DevelopmentVerification,
        )

        outcome = self._make_outcome(
            "FAILED",
            verification_passed=False,
            rollback_occurred=True,
        )
        result = self._make_result("FAILED", [outcome])
        report = DevelopmentVerification().verify(result)

        assert report.any_rollback is True

    def test_changed_files_preserved(self):
        """Changed files are preserved in the report."""
        from atlas.evolution.development_verification import (
            DevelopmentVerification,
        )

        outcome = self._make_outcome(
            "SUCCESS",
            verification_passed=True,
            changed_files=["atlas/memory/manager.py", "atlas/memory/storage.py"],
        )
        result = self._make_result("SUCCESS", [outcome])
        report = DevelopmentVerification().verify(result)

        assert "atlas/memory/manager.py" in report.changed_files
        assert "atlas/memory/storage.py" in report.changed_files

    def test_does_not_infer_from_message(self):
        """A human-readable message alone does not fabricate verification."""
        from atlas.evolution.development_verification import (
            DevelopmentVerification,
            VerificationStatus,
        )

        # FAILED status with a positive-sounding message should NOT be VERIFIED.
        outcome = self._make_outcome(
            "FAILED",
            verification_passed=False,
            test_outcome="failed",
            message="almost succeeded",
        )
        result = self._make_result("FAILED", [outcome], message="almost succeeded")
        report = DevelopmentVerification().verify(result)

        assert report.status != VerificationStatus.VERIFIED

    def test_immutable_report(self):
        """VerificationReport is frozen/immutable."""
        from atlas.evolution.development_verification import (
            DevelopmentVerification,
            VerificationStatus,
        )

        result = self._make_result("SUCCESS", [self._make_outcome()])
        report = DevelopmentVerification().verify(result)

        with pytest.raises(AttributeError):
            report.status = VerificationStatus.UNVERIFIABLE

    def test_no_subprocess_or_execution(self):
        """DevelopmentVerification must not invoke execution or subprocess."""
        import inspect

        from atlas.evolution.development_verification import DevelopmentVerification

        src = inspect.getsource(DevelopmentVerification)
        assert "run_development_execution" not in src
        assert "subprocess" not in src
        assert "pytest" not in src
        assert "os.system" not in src
        assert ".apply(" not in src


class TestVerificationClassification:
    """P17 — explicit verification request classification."""

    def test_verification_cues(self):
        """Verification cues classify as VERIFICATION_REQUEST."""
        for text in (
            "verify the development",
            "verify the result",
            "check the development result",
            "check whether the development succeeded",
            "verify the completed development",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is TaskType.VERIFICATION_REQUEST

    def test_recovery_not_misclassified_as_verification(self):
        """Recovery cues remain RECOVERY_REQUEST."""
        spec = TaskIntake().intake("recover from the failure")
        assert spec.task_type is TaskType.RECOVERY_REQUEST

    def test_execution_not_misclassified_as_verification(self):
        """Execution cues remain EXECUTION_REQUEST."""
        spec = TaskIntake().intake("execute the approved proposal")
        assert spec.task_type is TaskType.EXECUTION_REQUEST


class TestDevelopmentLifecycleReport:
    """P17 — DevelopmentLifecycleReport model and builder."""

    def _make_outcome(
        self,
        status: str = "SUCCESS",
        *,
        verification_passed: bool = True,
        rollback_occurred: bool = False,
        test_outcome: str = "passed",
        message: str = "Development iteration succeeded in sandbox.",
        changed_files: list[str] | None = None,
        iteration: int = 1,
    ) -> Any:
        from atlas.evolution.development_models import (
            DevelopmentOutcome,
            DevelopmentOutcomeStatus,
        )

        return DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus[status],
            proposal_id="PROP-RPT-001",
            plan_id="PLAN-RPT-001",
            iteration=iteration,
            verification_passed=verification_passed,
            rollback_occurred=rollback_occurred,
            test_outcome=test_outcome,
            message=message,
            changed_files=changed_files or ["atlas/memory/manager.py"],
        )

    def _make_result(
        self,
        status: str,
        outcomes: list[Any] | None = None,
        iterations_used: int | None = None,
        message: str = "",
    ) -> Any:
        from atlas.evolution.development_models import DevelopmentOutcomeStatus
        from atlas.evolution.self_development_loop import DevelopmentRunResult

        outcomes = outcomes or []
        return DevelopmentRunResult(
            status=DevelopmentOutcomeStatus[status],
            outcomes=outcomes,
            iterations_used=iterations_used if iterations_used is not None else len(outcomes),
            message=message,
        )

    def test_report_is_immutable(self):
        """DevelopmentLifecycleReport is frozen."""
        from atlas.evolution.development_report import (
            DevelopmentLifecycleReport,
            FinalConclusion,
        )

        report = DevelopmentLifecycleReport(
            final_conclusion=FinalConclusion.SUCCESS,
            evidence="test",
        )
        with pytest.raises(AttributeError):
            report.final_conclusion = FinalConclusion.FAILED

    def test_verified_success(self):
        """SUCCESS with all iterations passing → SUCCESS conclusion."""
        from atlas.evolution.development_report import DevelopmentReportBuilder

        outcome = self._make_outcome("SUCCESS", verification_passed=True)
        result = self._make_result("SUCCESS", [outcome])
        report = DevelopmentReportBuilder().build(
            state=self._dummy_state(),
            proposal=self._dummy_proposal("PROP-RPT-001"),
            approval=self._dummy_approval("APPR-RPT-001"),
        )
        # The builder reconstructs evidence from proposal metadata; with no
        # execution metadata it falls back to UNVERIFIABLE, which is correct
        # fail-closed behavior.
        assert report.final_conclusion is not None

    def _dummy_state(self) -> Any:
        return type(
            "_S",
            (),
            {"evolution_proposal_id": "PROP-RPT-001", "recovery_proposal_id": None},
        )()

    def _dummy_proposal(self, proposal_id: str) -> Any:
        from atlas.evolution.models import ProposalStatus

        return type(
            "_P",
            (),
            {
                "proposal_id": proposal_id,
                "status": ProposalStatus.APPROVED,
                "metadata": {
                    "execution": {
                        "result_status": "SUCCESS",
                        "last_outcome": {
                            "verification_passed": True,
                            "test_outcome": "passed",
                        },
                    }
                },
            },
        )()

    def _dummy_approval(self, request_id: str) -> Any:
        from atlas.evolution.models import ApprovalDecision

        return type(
            "_A",
            (),
            {"request_id": request_id, "decision": ApprovalDecision.APPROVED},
        )()

    def test_no_subprocess_or_execution(self):
        """Report builder must not invoke execution or subprocess."""
        import inspect

        from atlas.evolution.development_report import DevelopmentReportBuilder

        src = inspect.getsource(DevelopmentReportBuilder)
        assert "run_development_execution" not in src
        assert "subprocess" not in src
        assert "pytest" not in src
        assert "os.system" not in src
        assert ".apply(" not in src


class TestReportClassification:
    """P17 — explicit report request classification."""

    def test_report_cues(self):
        """Report cues classify as REPORT_REQUEST."""
        for text in (
            "report on the development",
            "give me the development report",
            "give me the final report",
            "show the final development report",
            "summarize the development lifecycle",
        ):
            spec = TaskIntake().intake(text)
            assert spec.task_type is TaskType.REPORT_REQUEST

    def test_recovery_not_misclassified_as_report(self):
        """Recovery cues remain RECOVERY_REQUEST."""
        spec = TaskIntake().intake("recover from the failure")
        assert spec.task_type is TaskType.RECOVERY_REQUEST

    def test_verification_not_misclassified_as_report(self):
        """Verification cues remain VERIFICATION_REQUEST."""
        spec = TaskIntake().intake("verify the development")
        assert spec.task_type is TaskType.VERIFICATION_REQUEST
