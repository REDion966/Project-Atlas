"""C4.2 — Deterministic repository impact-analysis conversational exposure.

Covers:
  * bounded recognition (``looks_like_repository_impact_request``);
  * the pure, read-only ``RepositoryImpactAnalyzer`` reusing RepositoryMap;
  * the production conversational path (ConversationService.send) with the
    external AI unavailable;
  * fail-closed behavior for unknown/ambiguous targets;
  * empty (but valid) impact results;
  * no mutation / no model dependency.

This milestone deliberately does NOT implement general reference resolution
(GAP-C31-02); a target must be provided deterministically.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.repository_impact import (
    IMPACT_CUES,
    RepositoryImpactAnalyzer,
    RepositoryImpactStatus,
    extract_target_candidates,
    looks_like_repository_impact_request,
)
from atlas.conversation.task_intake import TaskIntake, TaskType

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = "atlas.conversation.conversation_state"


class _FailingAI:
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


def _analyzer() -> RepositoryImpactAnalyzer:
    return RepositoryImpactAnalyzer(REPO_ROOT)


def _service() -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        ai_service=_FailingAI(),
        task_intake=TaskIntake(),
    )


# ---------------------------------------------------------------------------
# Bounded recognition
# ---------------------------------------------------------------------------


class TestRecognition:
    def test_impact_request_with_target_recognized(self):
        text = (
            "If I change atlas.conversation.conversation_state, which other "
            "modules depend on it and what would be affected?"
        )
        assert looks_like_repository_impact_request(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "What depends on it?",  # reference only, no target (GAP-C31-02)
            "What would be affected?",
            "How does the conversation pipeline work?",
            "Investigate the conversation subsystem.",
            "Give me the final report",
        ],
    )
    def test_non_impact_requests_not_recognized(self, text):
        assert looks_like_repository_impact_request(text) is False

    def test_target_extraction_forms(self):
        assert extract_target_candidates(
            "what depends on atlas.conversation.conversation_state?"
        ) == ("atlas.conversation.conversation_state",)
        assert extract_target_candidates(
            "if I modify atlas/conversation/conversation_state.py"
        ) == ("atlas.conversation.conversation_state",)

    def test_cue_vocabulary_is_explicit(self):
        assert "depend on" in IMPACT_CUES
        assert "what would be affected" in IMPACT_CUES


# ---------------------------------------------------------------------------
# Pure analyzer
# ---------------------------------------------------------------------------


class TestAnalyzer:
    def test_resolved_reuses_repository_map(self):
        from atlas.research.repository_map import RepositoryMapBuilder

        repo_map = RepositoryMapBuilder(REPO_ROOT).build()
        result = _analyzer().analyze(f"What depends on {TARGET}?")
        assert result.status is RepositoryImpactStatus.RESOLVED
        assert result.resolved_module == TARGET
        assert result.dependents == repo_map.dependents_of(TARGET)
        assert result.dependencies == repo_map.dependencies_of(TARGET)
        assert result.impact == tuple(sorted(repo_map.impact_set(TARGET)))

    def test_deterministic_repeated(self):
        a = _analyzer().analyze(f"What would be affected if I change {TARGET}?")
        b = _analyzer().analyze(f"What would be affected if I change {TARGET}?")
        assert a.to_dict() == b.to_dict()

    def test_path_form_resolves(self):
        result = _analyzer().analyze(
            "If I modify atlas/conversation/conversation_state.py, "
            "what is affected?"
        )
        assert result.status is RepositoryImpactStatus.RESOLVED
        assert result.resolved_module == TARGET

    def test_unknown_target_fails_closed(self):
        result = _analyzer().analyze(
            "What depends on atlas.does.not.exist_module?"
        )
        assert result.status is RepositoryImpactStatus.UNRESOLVED
        assert result.dependents == ()
        assert result.impact == ()
        assert "no impact information" in result.message.lower()

    def test_no_target_fails_closed(self):
        result = _analyzer().analyze("What would be affected?")
        assert result.status is RepositoryImpactStatus.UNRESOLVED
        assert "no repository module identifier" in result.message.lower()

    def test_ambiguous_targets_fail_closed(self):
        result = _analyzer().analyze(
            "What is affected if I change atlas.conversation.conversation_state "
            "and atlas.evolution.models?"
        )
        assert result.status is RepositoryImpactStatus.AMBIGUOUS
        assert result.dependents == ()

    def test_empty_impact_is_not_an_error(self):
        from atlas.research.repository_map import RepositoryMapBuilder

        repo_map = RepositoryMapBuilder(REPO_ROOT).build()
        leaf = next(
            (
                info.module
                for info in repo_map.modules
                if not repo_map.dependents_of(info.module)
                and not repo_map.impact_set(info.module)
            ),
            None,
        )
        assert leaf is not None, "expected at least one leaf module"
        result = _analyzer().analyze(f"What would be affected if I change {leaf}?")
        assert result.status is RepositoryImpactStatus.RESOLVED
        assert result.dependents == ()
        assert result.impact == ()
        assert "not an error" in result.message.lower()

    def test_result_is_read_only(self):
        result = _analyzer().analyze(f"What depends on {TARGET}?")
        assert result.modification_status == "NONE"
        assert not hasattr(_analyzer(), "execute")
        assert not hasattr(result, "apply")


# ---------------------------------------------------------------------------
# Production conversational path
# ---------------------------------------------------------------------------


class TestProductionPath:
    def test_classification(self):
        spec = TaskIntake().intake(
            "If I change atlas.conversation.conversation_state, which other "
            "modules depend on it and what would be affected?"
        )
        assert spec.task_type is TaskType.REPOSITORY_IMPACT_REQUEST

    def test_send_resolves_without_ai(self):
        service = _service()
        response = service.send(
            "If I change atlas.conversation.conversation_state, which other "
            "modules depend on it and what would be affected?"
        )
        meta = response.metadata["repository_impact"]
        assert meta["status"] == "resolved"
        assert meta["resolved_module"] == TARGET
        assert meta["modification_status"] == "NONE"
        assert "Repository Impact Analysis" in response.content
        assert "**Modification performed:** NONE" in response.content
        assert _FailingAI.calls == 0

    def test_send_stable_across_repeats(self):
        service = _service()
        text = f"What depends on {TARGET}?"
        first = service.send(text).metadata["repository_impact"]
        second = service.send(text).metadata["repository_impact"]
        assert first == second

    def test_send_unknown_target_fails_closed(self):
        service = _service()
        response = service.send("What depends on atlas.nope.missing?")
        meta = response.metadata["repository_impact"]
        assert meta["status"] == "unresolved"
        assert meta["dependents"] == []
        assert "could not be resolved" in response.content.lower()

    def test_reference_only_question_not_hijacked(self):
        # GAP-C31-02 must NOT be implemented: "it" is not a resolvable target.
        service = _service()
        response = service.send("What depends on it?")
        assert "repository_impact" not in (response.metadata or {})

    def test_plain_question_reaches_existing_fallback(self):
        service = _service()
        response = service.send("How does the conversation pipeline work?")
        assert "repository_impact" not in (response.metadata or {})

    def test_investigation_still_works(self):
        service = ConversationService(
            ai_service=_FailingAI(),
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
        )
        response = service.send("Investigate the conversation subsystem.")
        assert response.metadata["investigation"]["modification_status"] == "NONE"
