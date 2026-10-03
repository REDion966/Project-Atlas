"""Real-kernel self-development routing — the goal-orchestration precedence defect.

Investigation record (deterministic, model-OFF, real kernel).

**Symptom.** The real Atlas REPL answered this request with a read-only
investigation/explanation PLAN whose step label was a malformed subject:

    "Done. Steps completed: 2/2.
     - Investigate (want add small deterministic regression test capability
       explanation behavior just): completed ...
     - Analysis (want add small deterministic regression test capability
       explanation behavior just): completed ..."

**Previous diagnosis was wrong.** The implementation report blamed
``ConversationService._maybe_handle_multi_intent``. Tracing the real cascade
shows that handler is NEVER REACHED for this turn — it sits at line 3651,
*after* the route that actually claims it.

**Actual root cause.** ``ConversationService._maybe_handle_goal_request`` (line
2742) sits at line 3623 of the ``send`` cascade, while the governed development
route ``_development_request_route`` sits at line 3812 — later. The goal route
called ``build_goal_plan`` on raw text and never consulted the ``TaskSpec`` the
cascade had ALREADY computed at line 3463. For a governed development request
that also carries an investigation/explanation clause, the decomposition yields
an investigation/explanation pair, so the goal route claimed the turn and the
governed development route became unreachable. This contradicted the cascade's
own stated contract at line 3810: *"Development semantics win — run it first and
never reroute development through orchestration."*

The correction is a local precedence condition, not new architecture: the goal
route now declines when the already-computed ``TaskSpec`` classifies the turn as
``DEVELOPMENT_REQUEST``. No new parser, router, authority, or approval rule.
"""

from __future__ import annotations

from pathlib import Path

from atlas.conversation import semantic_frame as sf
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.task_intake import TaskIntake, TaskType

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: The exact request that produced the defect on the real kernel.
TARGET = (
    "I want you to add a small deterministic regression test for the "
    "capability-explanation behavior we just fixed. First investigate the relevant "
    "implementation and existing tests, then tell me exactly what you would change "
    "and why. Do not modify anything yet."
)

#: A clean two-stage goal that legitimately owns the orchestration route.
GOAL = (
    "Investigate the conversation state handling and then explain what we should "
    "do next."
)


class _FailingAI:
    """Model-OFF: any provider contact is a test failure."""

    calls = 0

    def chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1
        raise RuntimeError("no model may be contacted")

    def stream_chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1

        def _gen():
            raise RuntimeError("no model may be contacted")
            yield ""  # pragma: no cover

        return _gen()


class _RecordingGoalBridge:
    """Records every plan the goal route hands to the kernel-owned executor."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def __call__(self, text, steps, session_context=None):
        from atlas.orchestration.execution_models import ExecutionRequest
        from atlas.orchestration.reporting import orchestration_result_to_message
        from atlas.session.context import SessionContext
        from atlas.session.manager import SessionManager
        from atlas.authority.service import AuthorityService

        descriptions = tuple(str(getattr(s, "description", "")) for s in steps)
        self.calls.append((text, descriptions))
        manager = SessionManager(AuthorityService("Owner"))
        session = session_context or SessionContext.from_session(
            manager.create_session("owner")
        )
        result = _executor().execute(
            ExecutionRequest(steps=tuple(steps), session_context=session, max_steps=4)
        )
        return orchestration_result_to_message(result, intent=text)


def _executor():
    from atlas.authority.service import AuthorityService
    from atlas.orchestration.executor import OrchestrationExecutor

    return OrchestrationExecutor(
        authority_service=AuthorityService("Owner"),
        investigation_service=InvestigationService(),
    )


def _service(bridge=None) -> ConversationService:
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        investigation_service=InvestigationService(),
        goal_orchestration_resolver=bridge or _RecordingGoalBridge(),
    )


def _started_atlas(monkeypatch, tmp_path):
    """A fully wired real kernel with every external opt-in at its code default."""
    from tests.safe_kernel_config import bound_configuration, write_safe_config
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    config_path = write_safe_config(tmp_path)

    class TmpSQLiteEvolutionStorage(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", TmpSQLiteEvolutionStorage
    )
    monkeypatch.setattr(
        "atlas.kernel.atlas.Configuration", bound_configuration(config_path)
    )
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


# ---------------------------------------------------------------------------
# 1. Root cause: the decomposition that stole the turn
# ---------------------------------------------------------------------------


class TestRootCause:
    def test_intake_already_classified_the_turn_as_development(self):
        assert TaskIntake().intake(TARGET).task_type is TaskType.DEVELOPMENT_REQUEST

    def test_the_decomposition_yields_the_stolen_investigation_pair(self):
        # This is what let the goal route claim a DEVELOPMENT_REQUEST: the raw text
        # decomposes into an investigation/explanation pair, and the previous goal
        # route never consulted the already-computed TaskSpec.
        assert sf.decompose(TARGET) != ()

    def test_goal_plan_is_still_composable_from_the_same_text(self):
        # The plan composition itself is NOT the defect and stays unchanged: it is
        # the goal route's failure to DEFINE against the intake that was wrong.
        from atlas.orchestration.goal_plan import build_goal_plan

        assert build_goal_plan(TARGET) is not None


# ---------------------------------------------------------------------------
# 2. The correction: governed development keeps its own route
# ---------------------------------------------------------------------------


class TestGovernedDevelopmentKeepsItsRoute:
    def test_goal_route_declines_a_development_request(self):
        bridge = _RecordingGoalBridge()
        message = _service(bridge).send(TARGET)

        assert bridge.calls == [], "governed development was rerouted to orchestration"
        assert "step(s) completed" not in message.content
        assert "Investigate (want add small deterministic" not in message.content

    def test_the_same_request_without_the_clause_takes_the_same_route(self):
        # Before the fix these two requests diverged only because of the extra
        # clause. They must now be routed identically.
        without = TARGET.replace(
            "First investigate the relevant implementation and existing tests, then ", ""
        )
        bridge = _RecordingGoalBridge()
        _service(bridge).send(without)
        assert bridge.calls == []

    def test_no_approval_is_created_merely_by_planning(self):
        service = _service()
        service.send(TARGET)
        assert service.state_manager.state.pending_approval_id is None

    def test_no_authority_metadata_is_emitted(self):
        message = _service().send(TARGET)
        for key in ("approval", "execution", "promotion", "authorization"):
            assert key not in (message.metadata or {}), key

    def test_model_off_operation(self):
        # The GOAL ROUTE is model-free by construction and is now never even
        # entered for a development request: no plan is composed and the
        # orchestration bridge is never called.
        #
        # (A bare service with no kernel-owned development bridge falls through to
        # the model path at the very END of the cascade — that is the EXISTING
        # legacy contract of _maybe_handle_development_request, unchanged here.)
        _FailingAI.calls = 0
        bridge = _RecordingGoalBridge()
        service = _service(bridge)
        spec = TaskIntake().intake(TARGET)
        assert (
            service._maybe_handle_goal_request(TARGET, spec) is None
        ), "the goal route must decline a governed development request"
        assert _FailingAI.calls == 0
        assert bridge.calls == []

    def test_stream_mirrors_send(self):
        # Both cascades route through the same handler; the stream path must not
        # reintroduce the defect.
        bridge = _RecordingGoalBridge()
        service = _service(bridge)
        chunks = list(service.stream(TARGET))
        assert bridge.calls == []
        assert "step(s) completed" not in "".join(chunks)


# ---------------------------------------------------------------------------
# 3. Preserved behaviour
# ---------------------------------------------------------------------------


class TestPreservedBehaviour:
    def test_clean_two_stage_goal_still_uses_orchestration(self):
        bridge = _RecordingGoalBridge()
        message = _service(bridge).send(GOAL)
        assert bridge.calls, "a legitimate two-stage goal must keep its route"
        # The orchestration reporting surface owns this shape (N/M summary), which
        # is exactly what a development request must no longer be able to reach.
        assert "step(s) completed" in message.content

    def test_clean_goal_does_not_leak_an_approval(self):
        service = _service()
        service.send(GOAL)
        assert service.state_manager.state.pending_approval_id is None

    def test_plain_development_request_is_unchanged(self):
        bridge = _RecordingGoalBridge()
        message = _service(bridge).send(
            "Add a small deterministic regression test for this behavior."
        )
        assert bridge.calls == []
        assert "I need a bit more detail" in message.content

    def test_normal_investigation_is_unchanged(self):
        bridge = _RecordingGoalBridge()
        message = _service(bridge).send(
            "Investigate how Atlas handles development requests."
        )
        assert bridge.calls == []
        assert "## Investigation:" in message.content

    def test_multi_intent_non_development_goal_is_unchanged(self):
        bridge = _RecordingGoalBridge()
        _service(bridge).send(
            "Investigate the parser module and then explain the problem."
        )
        assert bridge.calls, "a non-development goal keeps the orchestration route"

    def test_explicit_negation_still_wins(self):
        # An explicitly negated development request must NOT be treated as one.
        assert (
            TaskIntake()
            .intake("Don't add a test to the module; do not modify anything yet.")
            .task_type
            is TaskType.CONVERSATION
        )
        bridge = _RecordingGoalBridge()
        _service(bridge).send(
            "Don't add a test to the module; do not modify anything yet."
        )
        assert bridge.calls == []

    def test_no_modification_stance_is_honoured(self):
        # The development bridge is kernel-owned, so the governed route only runs on
        # the real kernel. What matters here is that the read-only constraint the
        # request carries never became a reason to answer it as a plan/execution.
        assert TaskIntake().intake(TARGET).task_type is TaskType.DEVELOPMENT_REQUEST
        bridge = _RecordingGoalBridge()
        message = _service(bridge).send(TARGET)
        assert bridge.calls == []
        assert "step(s) completed" not in message.content


# ---------------------------------------------------------------------------
# 4. Real kernel
# ---------------------------------------------------------------------------


class TestRealKernel:
    def test_target_request_stays_on_the_development_route(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat(TARGET)
            assert "step(s) completed" not in message.content
            assert "Investigate (want add small deterministic" not in message.content
            assert atlas._conversation.state_manager.state.pending_approval_id is None
        finally:
            atlas.shutdown()

    def test_real_kernel_does_not_plan_a_development_request(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            planned: list[str] = []
            service = atlas._conversation
            original = service._goal_orchestration_resolver

            def spy(text, steps, session_context=None):
                planned.append(text)
                return original(text, steps, session_context)

            service._goal_orchestration_resolver = spy
            atlas.chat(TARGET)
            assert planned == [], "real kernel must not orchestrate a development request"
        finally:
            atlas.shutdown()

    def test_real_kernel_external_providers_are_off(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            assert (
                atlas._config.get("ai", "external_providers", default=False) is False
            )
            message = atlas.chat(TARGET)
            # The governed development route answers deterministically and says so;
            # no provider is contacted and no model is required.
            assert "no external AI model used" in message.content
        finally:
            atlas.shutdown()

    def test_no_repository_modification_occurs(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            before = sorted(p.name for p in _REPO_ROOT.glob("atlas/**/*.py"))
            stamps = {
                p: p.stat().st_mtime
                for p in _REPO_ROOT.glob("atlas/**/*.py")
                if p.is_file()
            }
            atlas.chat(TARGET)
            assert sorted(p.name for p in _REPO_ROOT.glob("atlas/**/*.py")) == before
            changed = [p for p, m in stamps.items() if p.stat().st_mtime != m]
            assert changed == [], f"repository modified: {changed}"
        finally:
            atlas.shutdown()