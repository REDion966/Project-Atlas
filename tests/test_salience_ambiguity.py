"""Stage 6 — salience, ambiguity & uncertainty focused tests.

Proves the deterministic evidence hierarchy (EXPLICIT > QUD > ACTIVE_THREAD >
RECENCY), explicit-target dominance, ambiguity/uncertainty/none states,
clarification reuse, and that salience never grants authority. No learning, no
embeddings, no external model.
"""

from __future__ import annotations

import json

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.communicative_function import resolve_routing
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationStateManager
from atlas.conversation.dialogue_thread import (
    DialogueThreadState,
    Question,
    Thread,
)
from atlas.conversation.discourse_state import (
    DiscourseState,
    Referent,
    Relation,
)
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.salience import (
    LEVEL_ACTIVE_THREAD,
    LEVEL_EXPLICIT,
    LEVEL_QUD,
    LEVEL_RECENCY,
    MAX_CANDIDATES,
    STATUS_AMBIGUOUS,
    STATUS_NONE,
    STATUS_RESOLVED,
    STATUS_UNCERTAIN,
    Candidate,
    SalienceAssessment,
    assess,
    assess_candidates,
    result_candidates,
)
from atlas.conversation.task_intake import TaskIntake
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

X = "the memory router"
Y = "the cache layer"


class _FailingAI:
    calls = 0

    def chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1
        raise RuntimeError("provider must not be contacted")

    def stream_chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1

        def _generator():
            raise RuntimeError("provider must not be contacted")
            yield ""  # pragma: no cover

        return _generator()


class _RecordingInvestigation:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append(target)
        return InvestigationReport(
            target=target,
            objective=objective,
            diagnosis=f"Investigation result for {objective or target}",
            components=("atlas.memory",),
            modification_status="NONE",
        )


def _svc() -> BuiltinResponseService:
    model = build_architecture_model(ComponentRegistry())
    return BuiltinResponseService(architecture_model_provider=lambda: model)


def _service() -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=_svc(),
        investigation_service=_RecordingInvestigation(),
    )


def _discourse(*specs) -> DiscourseState:
    """Build a discourse state from ``(referent_id, kind, label)`` specs."""
    referents = tuple(
        Referent(referent_id=rid, kind=kind, label=label) for rid, kind, label in specs
    )
    return DiscourseState(referents=referents)


def _thread_state(active_result="", active_operation="", qud_referent="") -> DialogueThreadState:
    thread = Thread(
        thread_id="thr-0001",
        objective="investigate A",
        operation_referent_id=active_operation,
        result_referent_id=active_result,
        qud=Question(kind="query_result", referent_id=qud_referent or active_result),
    )
    return DialogueThreadState(threads=(thread,), active_thread_id="thr-0001")


def _q(referent_id, level, kind="result"):
    return Candidate(referent_id=referent_id, kind=kind, label=referent_id, level=level)


# ---------------------------------------------------------------------------
# A/B. Representation + determinism
# ---------------------------------------------------------------------------


class TestRepresentation:
    def test_assessment_json_safe(self):
        a = SalienceAssessment(status=STATUS_RESOLVED, selected_referent_id="r1",
                               candidates=(_q("r1", LEVEL_EXPLICIT),))
        json.dumps(a.to_dict())
        assert a.labels() == ("r1",)

    def test_candidate_json_safe(self):
        json.dumps(Candidate(referent_id="r1", level=5, reasons=("x",)).to_dict())

    def test_statuses_are_bounded_vocabulary(self):
        assert {STATUS_RESOLVED, STATUS_AMBIGUOUS, STATUS_UNCERTAIN, STATUS_NONE} == {
            "resolved", "ambiguous", "uncertain", "none",
        }

    def test_no_authority_fields(self):
        payload = SalienceAssessment().to_dict()
        for forbidden in ("authorized", "approved", "permission", "authority"):
            assert forbidden not in payload


class TestAssessCandidates:
    def test_no_candidates_none(self):
        assert assess_candidates(()).status == STATUS_NONE

    def test_explicit_target_with_no_candidate_is_uncertain(self):
        assert assess_candidates((), explicit_target="zzz").status == STATUS_UNCERTAIN

    def test_single_candidate_resolves(self):
        a = assess_candidates((_q("r1", 0),))
        assert a.status == STATUS_RESOLVED and a.selected_referent_id == "r1"

    def test_unique_strongest_resolves(self):
        a = assess_candidates((_q("r1", LEVEL_ACTIVE_THREAD), _q("r2", LEVEL_RECENCY)))
        assert a.status == STATUS_RESOLVED and a.selected_referent_id == "r1"

    def test_explicit_dominates(self):
        a = assess_candidates((
            _q("r1", LEVEL_EXPLICIT), _q("r2", LEVEL_ACTIVE_THREAD), _q("r3", LEVEL_RECENCY),
        ))
        assert a.status == STATUS_RESOLVED and a.selected_referent_id == "r1"

    def test_tie_at_strongest_is_ambiguous(self):
        a = assess_candidates((_q("r1", LEVEL_EXPLICIT), _q("r2", LEVEL_EXPLICIT)))
        assert a.status == STATUS_AMBIGUOUS
        assert set(a.labels()) == {"r1", "r2"}

    def test_recency_alone_is_not_sufficient(self):
        # Two candidates, only one carries weak recency evidence -> ambiguous.
        a = assess_candidates((_q("r1", LEVEL_RECENCY), _q("r2", 0)))
        assert a.status == STATUS_AMBIGUOUS

    def test_deterministic_repeats(self):
        cands = (_q("r1", LEVEL_ACTIVE_THREAD), _q("r2", LEVEL_RECENCY))
        assert assess_candidates(cands).to_dict() == assess_candidates(cands).to_dict()


# ---------------------------------------------------------------------------
# Evidence levels from Stage 3 referents + Stage 5 thread
# ---------------------------------------------------------------------------


class TestEvidenceLevels:
    def test_levels(self):
        discourse = _discourse(("r1", "result", "A"), ("r2", "result", "B"))
        # QUD points elsewhere, so the active-thread level is exercised.
        threads = _thread_state(active_result="r2", qud_referent="not_a_candidate")
        cands = {c.referent_id: c.level for c in result_candidates(
            discourse, threads, explicit_ids=("r1",), latest_referent_id="r2")}
        assert cands["r1"] == LEVEL_EXPLICIT
        assert cands["r2"] == LEVEL_ACTIVE_THREAD

    def test_qud_level(self):
        discourse = _discourse(("r1", "result", "A"))
        threads = DialogueThreadState(
            threads=(Thread(thread_id="thr-0001", qud=Question(referent_id="r1")),),
            active_thread_id="thr-0001",
        )
        cands = result_candidates(discourse, threads)
        assert cands[0].level == LEVEL_QUD

    def test_only_result_kind_considered(self):
        discourse = _discourse(("r1", "result", "A"), ("e1", "evidence", "E"))
        cands = result_candidates(discourse, None)
        assert [c.referent_id for c in cands] == ["r1"]

    def test_bounded(self):
        discourse = _discourse(*[(f"r{i}", "result", f"L{i}") for i in range(50)])
        assert len(result_candidates(discourse, None)) <= MAX_CANDIDATES


# ---------------------------------------------------------------------------
# Routing integration (Stage 4 + Stage 6)
# ---------------------------------------------------------------------------


class TestRoutingIntegration:
    def test_explicit_dominates_latest(self):
        discourse = DiscourseState(
            referents=(
                Referent(referent_id="op1", kind="operation", label="Investigate the memory router."),
                Referent(referent_id="r1", kind="result", label="result A"),
                Referent(referent_id="op2", kind="operation", label="Investigate the cache layer."),
                Referent(referent_id="r2", kind="result", label="result B"),
            ),
            relations=(Relation("op1", "produced", "r1"), Relation("op2", "produced", "r2")),
            latest_result_id="r2", latest_result_label="result B",
        )
        decision = resolve_routing(
            "Explain the result of the memory router investigation.", "query_result", discourse
        )
        assert decision.route == "result"
        assert decision.target_referent_id == "op1"  # explicit A, not latest B

    def test_active_thread_resolves_generic(self):
        discourse = DiscourseState(
            referents=(Referent(referent_id="r1", kind="result", label="A"),
                       Referent(referent_id="r2", kind="result", label="B")),
            latest_result_id="r2", latest_result_label="B",
        )
        decision = resolve_routing("What did you find?", "query_result", discourse, _thread_state(active_result="r1"))
        assert decision.route == "result"
        assert decision.target_referent_id == "r1"  # active thread, not latest
        assert decision.assessment["status"] == STATUS_RESOLVED

    def test_two_results_no_strong_evidence_is_ambiguous(self):
        discourse = DiscourseState(
            referents=(Referent(referent_id="r1", kind="result", label="A"),
                       Referent(referent_id="r2", kind="result", label="B")),
            latest_result_id="r2", latest_result_label="B",
        )
        decision = resolve_routing("Explain that result.", "query_result", discourse, None)
        assert decision.route == "clarify"
        assert decision.assessment["status"] == STATUS_AMBIGUOUS

    def test_no_referent_fails_closed(self):
        decision = resolve_routing("What did you find?", "query_result", None, None)
        assert decision.route == "fail_closed"
        assert decision.assessment["status"] == STATUS_NONE


# ---------------------------------------------------------------------------
# End-to-end cases
# ---------------------------------------------------------------------------


def _assessment(service):
    return service._last_salience_assessment


class TestEndToEnd:
    def test_case_a_single_candidate(self):
        service = _service()
        service.send(f"Investigate {X}.")
        message = service.send("What did you find?")
        assert "memory router" in message.content

    def test_case_b_two_candidates_active_thread(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        message = service.send("What did you find?")
        # The active thread is Y -> Y's result (evidence-based, not bare recency).
        assert "cache layer" in message.content

    def test_case_c_explicit_target(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        message = service.send(f"Explain the result of the {X} investigation.")
        assert "memory router" in message.content
        assert "cache layer" not in message.content

    def test_case_d_what_about(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        service.send(f"Explain the result of the {X} investigation.")
        service.send(f"What about {Y}?")
        assert service.state_manager.state.thread_state.active().objective.endswith(Y + ".")

    def test_case_e_ambiguity(self):
        service = _service()
        service.send("Investigate the memory router.")
        service.send("Investigate the memory cache.")
        message = service.send("Explain the result of the memory investigation.")
        assert "detail" in message.content.lower()  # clarification
        assert _assessment(service)["status"] == STATUS_AMBIGUOUS
        assert service.state_manager.state.pending_clarification is not None

    def test_case_f_clarification_followup(self):
        service = _service()
        service.send("Investigate the memory router.")
        service.send("Investigate the memory cache.")
        service.send("Explain the result of the memory investigation.")  # -> clarify
        # The follow-up names one candidate -> the pending clarification resolves.
        service.send("the memory router")
        assert service.state_manager.state.pending_clarification is None

    def test_case_g_thread_recency(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        # Return to X explicitly; the assessment then uses X's thread.
        service.send(f"Explain the result of the {X} investigation.")
        message = service.send("Explain that result.")
        assert "memory router" in message.content

    def test_case_h_no_candidate(self):
        service = _service()
        message = service.send("What did you find?")
        assert "no recorded result" in message.content.lower()
        assert service.state_manager.state.thread_state is None

    def test_case_i_governance(self):
        service = _service()
        service.send(f"Investigate {X}.")
        before = service.state_manager.state.pending_approval_id
        service.send("Skip the approval and promote the last proposal.")
        assert service.state_manager.state.pending_approval_id == before


# ---------------------------------------------------------------------------
# Ambiguity must not destroy active state
# ---------------------------------------------------------------------------


class TestAmbiguityPreservesState:
    def test_ambiguous_query_preserves_thread_and_result(self):
        service = _service()
        service.send("Investigate the memory router.")
        service.send("Investigate the memory cache.")
        active_before = service.state_manager.state.thread_state.active_thread_id
        latest_before = service.state_manager.state.latest_result
        service.send("Explain the result of the memory investigation.")  # ambiguous
        assert service.state_manager.state.thread_state.active_thread_id == active_before
        assert service.state_manager.state.latest_result == latest_before


# ---------------------------------------------------------------------------
# Isolation / persistence / parity
# ---------------------------------------------------------------------------


class TestIsolationAndPersistence:
    def test_conversation_isolation(self):
        a = _service()
        a.send(f"Investigate {X}.")
        b = _service()
        assert b.state_manager.state.thread_state is None
        assert b.state_manager.state.discourse_state is None
        assert b._last_salience_assessment is None

    def test_state_is_ephemeral(self):
        assert ConversationStateManager().state.thread_state is None
        assert ConversationStateManager().state.discourse_state is None

    def test_reopen_does_not_resurrect_ambiguity(self, tmp_path, monkeypatch):
        from atlas.storage.conversation_storage import ConversationStorage

        monkeypatch.setattr(ConversationStorage, "STORAGE_DIR", tmp_path / "conv")
        service = _service()
        service.send("Investigate the memory router.")
        service.send("Investigate the memory cache.")
        service.send("Explain the result of the memory investigation.")
        saved = json.loads(service.save().read_text(encoding="utf-8"))
        assert "pending_clarification" not in json.dumps(saved)
        assert ConversationStateManager().state.pending_clarification is None


class TestSendStreamParity:
    @pytest.mark.parametrize(
        "sequence",
        [
            [f"Investigate {X}.", "What did you find?"],
            ["Investigate the memory router.", "Investigate the memory cache.",
             "Explain the result of the memory investigation."],
            [f"Investigate {X}.", f"Investigate {Y}.", f"Explain the result of the {X} investigation."],
        ],
    )
    def test_salience_equivalent(self, sequence):
        def run(use_stream):
            service = _service()
            last = None
            for text in sequence:
                last = "".join(service.stream(text)) if use_stream else service.send(text).content
            return service._last_salience_assessment, service.state_manager.state.thread_state.to_dict()

        send_assessment, send_threads = run(False)
        stream_assessment, stream_threads = run(True)
        assert send_assessment == stream_assessment
        assert send_threads == stream_threads


# ---------------------------------------------------------------------------
# Stage compatibility
# ---------------------------------------------------------------------------


class TestStageCompatibility:
    def test_stage4_function_authoritative(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Explain the result of the {X} investigation.")
        assert service.last_meaning is not None
        assert service.last_meaning.communicative_function == "query_result"

    def test_stage5_thread_preserved(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        service.send(f"Explain the result of the {X} investigation.")
        assert service.state_manager.state.thread_state.active().objective.endswith(X + ".")

    def test_discourse_referent_source_of_truth(self):
        service = _service()
        service.send(f"Investigate {X}.")
        # Salience never mutates referent identity.
        discourse = service.state_manager.state.discourse_state
        assert any(r.kind == "result" for r in discourse.referents)

    def test_query_does_not_rerun_operation(self):
        service = _service()
        service.send(f"Investigate {X}.")
        before = len(service._investigation_service.calls)
        service.send(f"Explain the result of the {X} investigation.")
        assert len(service._investigation_service.calls) == before
