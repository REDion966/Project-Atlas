"""C3.3 — Deterministic investigation synthesis / reporting tests.

Covers:
  * the pure, evidence-grounded ``InvestigationSynthesizer`` (deterministic
    prioritisation over an already-produced InvestigationReport);
  * the conversational investigation-report path through
    ``ConversationService.send`` (REPORT_REQUEST), without disturbing the
    existing development-lifecycle report;
  * model-independence (a failing AI service is never required);
  * read-only behavior (modification_status stays NONE; no repository mutation).

This milestone deliberately does NOT exercise GAP-C31-02 (reference
resolution); those tests belong to the deferred Priority 2 capability.
"""

from __future__ import annotations

from atlas.authority.service import AuthorityService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import (
    InvestigationFinding,
    InvestigationReport,
    InvestigationService,
)
from atlas.conversation.investigation_synthesis import (
    ComponentEvidence,
    InvestigationSynthesis,
    InvestigationSynthesizer,
)
from atlas.conversation.task_intake import TaskIntake
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager


# ---------------------------------------------------------------------------
# Doubles / helpers
# ---------------------------------------------------------------------------


class _FailingAI:
    """External AI unavailable; records any accidental invocation."""

    calls = 0

    def chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1
        raise RuntimeError("No AI available")

    def stream_chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1

        def _g():
            raise RuntimeError("No AI available")
            yield ""  # pragma: no cover

        return _g()


def _owner_session() -> SessionContext:
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    return SessionContext.from_session(manager.create_session("owner"))


def _report() -> InvestigationReport:
    """Fixed investigation report with directly-attributable evidence."""
    return InvestigationReport(
        target="memory architecture",
        components=(
            "atlas.memory.manager",
            "atlas.memory.repository",
            "atlas.conversation.service",
        ),
        findings=(
            InvestigationFinding(
                category="dependency",
                description=(
                    "'atlas.memory.manager' depends on: "
                    "atlas.memory.repository, atlas.storage.base"
                ),
                location="atlas.memory.manager",
            ),
            InvestigationFinding(
                category="dependency",
                description=(
                    "'atlas.memory.repository' depends on: atlas.storage.base"
                ),
                location="atlas.memory.repository",
            ),
            InvestigationFinding(
                category="test",
                description="Found 2 test file(s) referencing 'manager'",
                evidence="tests/test_memory_manager.py",
                location="tests/",
            ),
            InvestigationFinding(
                category="reference",
                description=(
                    "Found 3 reference(s) to 'memory' in atlas/memory/"
                ),
                evidence="atlas/memory/manager.py",
                location="atlas/memory/",
            ),
        ),
        diagnosis="Identified 3 relevant component(s) in atlas/memory.",
        affected_files=(
            "atlas/memory/manager.py",
            "tests/test_memory_manager.py",
        ),
        recommended_next_step="Review the identified components.",
        modification_status="NONE",
        tests_inspected=("tests/test_memory_manager.py",),
    )


def _service() -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        ai_service=_FailingAI(),
        task_intake=TaskIntake(),
        investigation_service=InvestigationService(),
        session_context=_owner_session(),
    )


# ---------------------------------------------------------------------------
# Pure synthesizer — unit tests
# ---------------------------------------------------------------------------


class TestSynthesizerDeterminism:
    def test_same_report_same_synthesis(self):
        report = _report()
        a = InvestigationSynthesizer().synthesize(report)
        b = InvestigationSynthesizer().synthesize(report)
        assert isinstance(a, InvestigationSynthesis)
        assert a.to_dict() == b.to_dict()

    def test_repeated_calls_are_stable(self):
        synth = InvestigationSynthesizer()
        report = _report()
        first = synth.synthesize(report).to_dict()
        for _ in range(3):
            assert synth.synthesize(report).to_dict() == first


class TestSynthesizerPrioritisation:
    def test_identifies_evidence_supported_component(self):
        result = InvestigationSynthesizer().synthesize(_report())
        assert result.insufficient_evidence is False
        # manager has dependency(3) + test(2) + reference(1) = 6
        assert result.recommended_focus == "atlas.memory.manager"
        top = result.ranked_components[0]
        assert top.component == "atlas.memory.manager"
        assert top.score == 6

    def test_ranking_is_ordered_by_score_then_name(self):
        result = InvestigationSynthesizer().synthesize(_report())
        scores = [c.score for c in result.ranked_components]
        assert scores == sorted(scores, reverse=True)
        # conversation.service has no attributable evidence
        assert result.ranked_components[-1].component == (
            "atlas.conversation.service"
        )
        assert result.ranked_components[-1].score == 0

    def test_conclusion_is_not_merely_a_count(self):
        result = InvestigationSynthesizer().synthesize(_report())
        # The synthesis states a conclusion about what to review first.
        assert result.recommended_focus is not None
        assert "strongest combined evidence" in result.recommended_reason.lower()
        assert "reviewing" in result.summary.lower()
        assert "first" in result.summary.lower()

    def test_evidence_tie_is_reported_honestly(self):
        report = InvestigationReport(
            target="tie",
            components=("atlas.b.beta", "atlas.a.alpha"),
            findings=(
                InvestigationFinding(
                    category="test",
                    description="Found 1 test file(s) referencing 'alpha'",
                    evidence="tests/test_alpha.py",
                    location="tests/",
                ),
                InvestigationFinding(
                    category="test",
                    description="Found 1 test file(s) referencing 'beta'",
                    evidence="tests/test_beta.py",
                    location="tests/",
                ),
            ),
            modification_status="NONE",
        )
        result = InvestigationSynthesizer().synthesize(report)
        assert result.insufficient_evidence is False
        assert result.tied_components == ("atlas.a.alpha", "atlas.b.beta")
        assert result.recommended_focus == "atlas.a.alpha"  # deterministic
        assert "share the strongest evidence" in result.recommended_reason.lower()
        assert "tie-break" in result.recommended_reason.lower()
        assert "Tied evidence" in result.to_markdown()


class TestSynthesizerEvidenceGrounding:
    def test_signals_cite_real_report_evidence(self):
        result = InvestigationSynthesizer().synthesize(_report())
        top = result.ranked_components[0]
        joined = " ".join(top.signals)
        assert (
            "'atlas.memory.manager' depends on: atlas.memory.repository, "
            "atlas.storage.base" in joined
        )
        assert "referencing 'manager'" in joined
        assert "tests/test_memory_manager.py" in joined

    def test_no_fabricated_components(self):
        report = _report()
        result = InvestigationSynthesizer().synthesize(report)
        assert set(c.component for c in result.ranked_components) == set(
            report.components
        )

    def test_insufficient_evidence_says_so(self):
        report = InvestigationReport(
            target="opaque target",
            components=("atlas.a.alpha", "atlas.b.beta"),
            findings=(),
            modification_status="NONE",
        )
        result = InvestigationSynthesizer().synthesize(report)
        assert result.insufficient_evidence is True
        assert result.recommended_focus is None
        assert "does not" in result.recommended_reason.lower()
        assert "insufficient" in result.to_markdown().lower()

    def test_empty_report_fails_safe(self):
        result = InvestigationSynthesizer().synthesize(
            InvestigationReport(target="nothing", modification_status="NONE")
        )
        assert result.insufficient_evidence is True
        assert result.recommended_focus is None
        assert "no specific evidence" in result.summary.lower()
        assert result.modification_status == "NONE"

    def test_signals_are_bounded(self):
        findings = tuple(
            InvestigationFinding(
                category="dependency",
                description=f"'atlas.x.mod' depends on: dep{i}",
                location="atlas.x.mod",
            )
            for i in range(6)
        )
        report = InvestigationReport(
            target="x",
            components=("atlas.x.mod",),
            findings=findings,
            modification_status="NONE",
        )
        result = InvestigationSynthesizer().synthesize(report)
        top = result.ranked_components[0]
        assert top.score == 18  # all evidence counted
        assert len(top.signals) <= 4  # rendering bounded

    def test_synthesis_is_read_only(self):
        result = InvestigationSynthesizer().synthesize(_report())
        assert result.modification_status == "NONE"
        assert not hasattr(InvestigationSynthesizer(), "execute")
        assert not hasattr(result, "execute")


class TestComponentEvidenceSerialization:
    def test_evidence_to_dict_json_safe(self):
        item = ComponentEvidence(
            component="atlas.x.mod", score=3, signals=("s",)
        )
        d = item.to_dict()
        assert d == {
            "component": "atlas.x.mod",
            "score": 3,
            "signals": ["s"],
        }


# ---------------------------------------------------------------------------
# Conversational integration — investigation report path
# ---------------------------------------------------------------------------


class TestInvestigationReportPath:
    def test_investigation_then_report_is_synthesised(self):
        service = _service()

        turn1 = service.send("Investigate the memory subsystem")
        assert turn1.metadata["investigation"]["modification_status"] == "NONE"

        turn2 = service.send("Give me the final report")
        assert turn2.role == "assistant"
        report_meta = turn2.metadata["report"]
        assert report_meta["status"] == "investigation"
        assert report_meta["kind"] == "investigation"
        assert report_meta["modification_status"] == "NONE"
        assert "Investigation Synthesis" in turn2.content
        assert "**Modification performed:** NONE" in turn2.content

    def test_report_without_investigation_still_no_lifecycle(self):
        service = _service()
        response = service.send("Give me the final report")
        assert response.metadata["report"]["status"] == "no_lifecycle"

    def test_investigation_branch_not_taken_with_development_lifecycle(self):
        """A development lifecycle keeps priority; the new branch is additive."""
        service = _service()
        service._last_investigation_report = _report()
        service.state_manager.update(evolution_proposal_id="PROP-DOES-NOT-EXIST")
        response = service.send("Give me the final report")
        # Falls through to the existing development-lifecycle path.
        assert response.metadata["report"]["status"] == "proposal_not_found"

    def test_report_isolated_between_services(self):
        a = _service()
        b = _service()
        a.send("Investigate the memory subsystem")
        response = b.send("Give me the final report")
        assert response.metadata["report"]["status"] == "no_lifecycle"

    def test_report_path_requires_no_external_model(self):
        service = _service()
        service.send("Investigate the memory subsystem")
        response = service.send("Give me the final report")
        assert response.metadata["report"]["status"] == "investigation"
        assert _FailingAI.calls == 0

    def test_report_requires_owner(self):
        authority = AuthorityService("Owner")
        authority.add_user("Alice", principal_id="alice")
        manager = SessionManager(authority)
        user_session = SessionContext.from_session(
            manager.create_session("alice")
        )
        service = ConversationService(
            ai_service=_FailingAI(),
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
            session_context=user_session,
        )
        service._last_investigation_report = _report()
        response = service.send("Give me the final report")
        assert response.metadata["report"]["status"] == "unauthorized"
