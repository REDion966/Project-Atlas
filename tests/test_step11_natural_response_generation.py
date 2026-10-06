"""Step 11 — natural response generation.

The baseline (real Atlas/kernel) showed the step/outcome report was mechanically
assembled: it echoed the whole request back ("Done: <whole sentence>"), exposed
internal step ids ("step-0000") and internal executor targets
("retrieve" / "synthesize") as if they were results, duplicated the target as the
"output", and always printed internal attribution ("Executed as: owner
(owner)"). It did not make clear what each step *was* and what it actually
*produced*.

Step 11 adds one bounded, deterministic response-realization layer
(``atlas/conversation/response_layer.py``) and routes the EXISTING reporting
surface through it, so every orchestration outcome is presented in one truthful,
natural shape. It is presentation only: no new intelligence, no model call, no
invented fact/action/authority, and the deterministic ``orchestration`` metadata
is unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.conversation.response_layer import describe_step, render_outcome
from atlas.orchestration.execution_models import (
    ExecutionState,
    ExecutionStatus,
    OrchestrationResult,
    StepExecutionResult,
    StepFailureKind,
)
from atlas.orchestration.models import NodeKind
from atlas.orchestration.reporting import orchestration_result_to_message

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _step(step_id, kind, target, state, *, output=None, error="", failure_kind=None, metadata=None):
    return StepExecutionResult(
        step_id=step_id,
        kind=kind,
        target=target,
        state=state,
        failure_kind=failure_kind,
        output=dict(output or {}),
        error=error,
        metadata=dict(metadata or {}),
    )


def _result(status, steps, error=""):
    return OrchestrationResult(run_id="run-1", status=status, steps=tuple(steps), error=error)


def _investigation_step(step_id="step-0000", subject="storage layer"):
    return _step(
        step_id,
        NodeKind.INVESTIGATION,
        f"investigate {subject}",
        ExecutionState.COMPLETED,
        output={
            "target": f"investigate {subject}",
            "objective": f"investigate {subject}",
            "diagnosis": "Identified 8 relevant component(s).",
        },
    )


def _knowledge_step(step_id="step-0001"):
    return _step(
        step_id,
        NodeKind.KNOWLEDGE,
        "retrieve",
        ExecutionState.COMPLETED,
        output={
            "question": "knowledge decision service",
            "validated_status": "ok",
            "claim_count": 3,
            "claims": [{"statement": "a"}, {"statement": "b"}, {"statement": "c"}],
        },
    )


def _started_atlas(monkeypatch, tmp_path):
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class TmpSQLiteEvolutionStorage(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", TmpSQLiteEvolutionStorage
    )
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


# ---------------------------------------------------------------------------
# 1. Response realization (presentation only)
# ---------------------------------------------------------------------------


class TestDescribeStep:
    def test_uses_a_human_label_not_the_step_id(self):
        line = describe_step(_investigation_step())
        assert line.startswith("- Investigate")
        assert "step-0000" not in line

    def test_shows_the_recorded_result_not_an_input_echo(self):
        line = describe_step(_investigation_step(subject="storage layer"))
        assert "storage layer" in line
        assert "Identified 8 relevant component(s)." in line
        # The internal target is NOT echoed as a "result".
        assert "investigate storage layer — investigate storage layer" not in line

    def test_knowledge_step_shows_a_count_result(self):
        line = describe_step(_knowledge_step())
        assert line.startswith("- Research")
        assert "knowledge decision service" in line
        assert "3 claim(s)" in line
        assert "retrieve" not in line

    def test_failed_step_shows_its_recorded_reason(self):
        step = _step(
            "step-0001",
            NodeKind.ANALYSIS,
            "synthesize",
            ExecutionState.FAILED,
            failure_kind=StepFailureKind.EXECUTION_FAILED,
            error="carried result is not an investigation report (fail-closed)",
        )
        line = describe_step(step)
        assert line.startswith("- Analysis")
        assert ": failed" in line
        assert "carried result is not an investigation report" in line
        assert "synthesize" not in line

    def test_blocked_step_shows_its_reason(self):
        step = _step(
            "step-0001",
            NodeKind.ANALYSIS,
            "synthesize",
            ExecutionState.BLOCKED,
            error="dependency step-0000 did not complete",
        )
        line = describe_step(step)
        assert ": blocked" in line
        assert "dependency" in line


class TestRenderOutcome:
    def test_completed_reports_counts_and_natural_steps(self):
        text = render_outcome(_result(ExecutionStatus.COMPLETED, [_investigation_step(), _knowledge_step()]))
        assert "Done. Steps completed: 2/2." in text
        assert "- Investigate" in text
        assert "- Research (knowledge decision service): completed — 3 claim(s)" in text
        assert "step-0000" not in text
        assert "Executed as" not in text

    def test_failed_never_claims_done_or_a_completed_count(self):
        step = _step(
            "step-0000",
            NodeKind.RESEARCH,
            "acquire",
            ExecutionState.FAILED,
            failure_kind=StepFailureKind.NO_EVIDENCE,
            error="research produced no authorized evidence for the requested objective",
        )
        text = render_outcome(_result(ExecutionStatus.FAILED, [step]))
        assert "Could not complete the request." in text
        assert "Done" not in text
        assert "Steps completed" not in text
        assert "no authorized evidence" in text

    def test_partial_reports_issues_without_done(self):
        analysis = _step(
            "step-0001",
            NodeKind.ANALYSIS,
            "synthesize",
            ExecutionState.FAILED,
            failure_kind=StepFailureKind.EXECUTION_FAILED,
            error="insufficient evidence for synthesis",
        )
        text = render_outcome(_result(ExecutionStatus.PARTIAL, [_investigation_step(), analysis]))
        assert "Completed with issues" in text
        assert "Done" not in text
        assert "Steps completed" not in text
        assert "insufficient evidence for synthesis" in text

    def test_research_partial_lists_dimensions(self):
        step = _step(
            "step-0000",
            NodeKind.RESEARCH,
            "acquire",
            ExecutionState.COMPLETED,
            metadata={
                "research_completeness": {
                    "status": "partial",
                    "requested": ["camera", "battery"],
                    "supported": ["camera"],
                    "unsupported": ["battery"],
                }
            },
        )
        text = render_outcome(_result(ExecutionStatus.PARTIAL, [step]))
        assert "Research partially completed." in text
        assert "Relevant evidence obtained for:" in text and "- camera" in text
        assert "No sufficient evidence obtained for:" in text and "- battery" in text

    def test_rejected_reports_the_reason(self):
        step = _step(
            "step-0000",
            NodeKind.CAPABILITY,
            "some_capability",
            ExecutionState.FAILED,
            failure_kind=StepFailureKind.AUTHORIZATION_FAILED,
        )
        text = render_outcome(_result(ExecutionStatus.REJECTED, [step], error="authorization denied"))
        assert "Could not execute this request." in text
        assert "authorization denied" in text

    def test_deterministic(self):
        result = _result(ExecutionStatus.COMPLETED, [_investigation_step(), _knowledge_step()])
        assert render_outcome(result) == render_outcome(result)


class TestOrchestrationMessage:
    def test_metadata_is_preserved_exactly(self):
        result = _result(ExecutionStatus.COMPLETED, [_investigation_step(), _knowledge_step()])
        message = orchestration_result_to_message(result)
        assert message.metadata["orchestration"]["status"] == "completed"
        assert len(message.metadata["orchestration"]["steps"]) == 2

    def test_request_is_not_echoed_back(self):
        result = _result(ExecutionStatus.COMPLETED, [_investigation_step()])
        message = orchestration_result_to_message(result, intent="Investigate X and also research Y.")
        assert "Investigate X and also research Y." not in message.content

    def test_malformed_result_is_handled(self):
        message = orchestration_result_to_message({"not": "a result"})  # type: ignore[arg-type]
        assert message.content == "I could not prepare the execution report."


# ---------------------------------------------------------------------------
# 2. Real Atlas/kernel validation
# ---------------------------------------------------------------------------


class TestRealKernel:
    def test_multi_step_report_is_natural_and_truthful(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat(
                "Investigate the memory service and also research the knowledge decision service."
            )
            content = message.content
            # Compound clause delegation is authoritative for this turn (see
            # test_step10_multi_intent_multi_step.TestRealKernel): each clause is
            # answered by the EXISTING authoritative handler a standalone turn
            # uses, so there is no orchestration step report to realize. The Step
            # 11 contract that still applies is the presentation one — a natural,
            # truthful report that leaks no internal identifiers and answers every
            # clause. The superseded "Done. Steps completed: 2/2." /
            # orchestration.status assertions contradicted that decision.
            metadata = message.metadata or {}
            assert metadata.get("orchestration") is None
            multi = metadata["multi_intent"]
            assert multi["unhandled"] == []
            assert len(multi["handled"]) == 2

            # Both clauses are genuinely answered.
            assert "I answered 2 of 2" in content
            assert "Investigate the memory service" in content
            assert "knowledge decision service" in content
            # No internal implementation detail leaks.
            assert "step-0000" not in content
            assert "Executed as" not in content
            # The result is presented, not summarized away.
            assert "## Investigation" in content
            # Audit metadata is intact.
            state = atlas._conversation.state_manager.state
            assert state.last_operation.kind == "investigation_request"
            assert bool(state.latest_result) is True
            assert bool(state.last_knowledge) is True
        finally:
            atlas.shutdown()

    def test_ordered_report_preserves_user_order(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat(
                "First investigate the storage layer, then research the knowledge decision service."
            )
            content = message.content
            # The user's explicit "first ... then ..." order is preserved in the
            # report, and the investigation clause is presented before research.
            assert content.index("First investigate the storage layer") < content.index(
                "knowledge decision service"
            )
            multi = (message.metadata or {})["multi_intent"]
            assert multi["unhandled"] == []
            assert multi["handled"][0].lower().startswith("first investigate")
        finally:
            atlas.shutdown()

    def test_dependent_report_identifies_the_analysis(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat(
                "Investigate the storage layer and then analyze the findings."
            )
            content = message.content
            assert "Done. Steps completed: 2/2." in content
            assert "- Analysis (" in content
            # Each step result belongs to its own step; the analysis is not silent.
            assert "completed" in content
        finally:
            atlas.shutdown()

    def test_unsupported_step_is_separated_from_completed_work(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat(
                "Investigate the memory service and also order me a new laptop."
            )
            content = message.content
            assert "- Investigate (memory service): completed" in content
            assert "Recognized but not attempted:" in content
            assert "order me a new laptop. — not supported" in content
        finally:
            atlas.shutdown()

    def test_follow_up_reference_stays_context_aware(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.chat("Investigate the storage layer.")
            follow = atlas.chat("What does it do?")
            assert follow.content.startswith("The active investigation:")
            assert "storage layer" in follow.content
        finally:
            atlas.shutdown()

    def test_clarification_lists_the_real_ambiguity(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            state = atlas._conversation.state_manager  # noqa: SLF001
            state.update(current_subject="auth module")
            state.update(development_intent="add oauth support")
            asked = atlas.chat("Tell me more about it.")
            assert "auth module" in asked.content
            assert "add oauth support" in asked.content
        finally:
            atlas.shutdown()

    def test_send_stream_parity(self, monkeypatch, tmp_path):
        text = "Investigate the memory service and also research the knowledge decision service."
        sent_atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            sent = sent_atlas.chat(text).content
        finally:
            sent_atlas.shutdown()
        streamed_atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            streamed = "".join(streamed_atlas.stream(text))
        finally:
            streamed_atlas.shutdown()
        assert sent == streamed

    def test_no_authority_or_repository_mutation(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat(
                "Investigate the memory service and also research the knowledge decision service."
            )
            for key in ("approval", "execution", "promotion", "authorization"):
                assert key not in message.metadata, key
            assert atlas.pending_promotion_reviews() == []
            assert not (
                _REPO_ROOT / "tests" / "test_goal_commands_evidence_gap.py"
            ).exists()
        finally:
            atlas.shutdown()
