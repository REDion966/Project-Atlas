"""Stage 3 — Discourse Referents + Operation/Result Lifecycle focused tests.

Covers the Stage 3 responsibilities: the bounded ``Referent``/``Relation``/
``DiscourseState`` representation and its value/serialization contract, the
operation → result → evidence lifecycle, the centralized ``apply_discourse_turn``
seam reached through the existing single operation-recording helper, boundedness,
governance safety, send/stream parity, and the explicit Stage 4+ boundaries.

The layer is representation-only: it must change no routing. ``TestStage0Regression``
and ``TestBehaviourPreservation`` pin that the known Stage 0 investigation
follow-up failure is unchanged. No network or external model is involved.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import (
    ConversationState,
    ConversationStateManager,
)
from atlas.conversation.discourse_state import (
    KIND_EVIDENCE,
    KIND_FINDING,
    KIND_OPERATION,
    KIND_PROPOSAL,
    KIND_RESULT,
    KIND_VERIFICATION,
    MAX_REFERENTS,
    REL_CONCERNS,
    REL_PRODUCED,
    REL_SUPPORTED_BY,
    REL_SUPERSEDES,
    REL_VERIFIED_BY,
    STATUS_BLOCKED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROPOSED,
    STATUS_SUPERSEDED,
    STATUS_VERIFIED,
    DiscourseState,
    DiscourseTurnOutcome,
    Referent,
    Relation,
    apply_turn,
)
from atlas.conversation.investigation import (
    InvestigationFinding,
    InvestigationReport,
)
from atlas.conversation.task_intake import TaskIntake
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

STAGE0_SEQUENCE = (
    "Investigate the current conversation architecture and tell me what you find.",
    "What did you find?",
    "Can you explain the result of the investigation you just completed?",
)


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
    """A read-only investigation that produces a diagnosis (no findings)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append({"target": target, "objective": objective})
        return InvestigationReport(
            target=target,
            objective=objective,
            diagnosis="Identified 3 relevant component(s) in atlas",
            components=("atlas.memory",),
            modification_status="NONE",
        )


class _DetailedInvestigation(_RecordingInvestigation):
    """A read-only investigation that also produces findings with evidence."""

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append({"target": target, "objective": objective})
        return InvestigationReport(
            target=target,
            objective=objective,
            diagnosis="Identified 3 relevant component(s) in atlas",
            findings=(
                InvestigationFinding(
                    category="test_gap",
                    description="no test covers the memory ranking path",
                    evidence="tests/test_memory.py",
                    location="atlas/memory/ranking.py:10",
                ),
            ),
            components=("atlas.memory",),
            modification_status="NONE",
        )


def _svc() -> BuiltinResponseService:
    model = build_architecture_model(ComponentRegistry())
    return BuiltinResponseService(architecture_model_provider=lambda: model)


def _service(investigation=None) -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=_svc(),
        investigation_service=investigation,
    )


def _outcome(**over) -> DiscourseTurnOutcome:
    base = dict(
        turn_index=1,
        operation_origin="investigation_request",
        operation_label="memory service",
        operation_status=STATUS_COMPLETED,
        result_label="found 3 components",
    )
    base.update(over)
    return DiscourseTurnOutcome(**base)


# ---------------------------------------------------------------------------
# A. Referent construction
# ---------------------------------------------------------------------------


class TestReferentConstruction:
    def test_empty_discourse_state_is_valid(self):
        state = DiscourseState()
        assert state.referents == ()
        assert state.relations == ()
        assert state.sequence == 0

    def test_conversation_state_default_has_no_discourse_state(self):
        assert ConversationState().discourse_state is None

    def test_referent_fields(self):
        referent = Referent(referent_id="ref-000001", kind=KIND_RESULT, label="r")
        assert referent.kind == KIND_RESULT
        assert referent.status == STATUS_PENDING

    def test_no_authority_fields(self):
        payload = Referent(referent_id="ref-000001").to_dict()
        for forbidden in ("authorized", "approved", "permission", "authority"):
            assert forbidden not in payload
        for forbidden in ("authorize", "approve", "execute", "promote"):
            assert not hasattr(DiscourseState(), forbidden)


# ---------------------------------------------------------------------------
# B. JSON serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_json_safe(self):
        state = apply_turn(None, _outcome())
        json.dumps(state.to_dict())

    def test_round_trip(self):
        state = apply_turn(None, _outcome(findings=("f",), evidence=("e",), proposal_ref="p1"))
        rebuilt = DiscourseState.from_dict(state.to_dict())
        assert rebuilt == state
        assert isinstance(rebuilt.referents[0], Referent)
        assert isinstance(rebuilt.relations[0], Relation)

    def test_conversation_state_round_trip_preserves_discourse_type(self):
        manager = ConversationStateManager()
        manager.apply_discourse_turn(_outcome())
        rebuilt = ConversationStateManager().update(**manager.state.to_dict())
        assert isinstance(rebuilt.discourse_state, DiscourseState)


# ---------------------------------------------------------------------------
# C. Immutability / value semantics
# ---------------------------------------------------------------------------


class TestValueSemantics:
    def test_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            Referent(referent_id="ref-000001").kind = "x"  # type: ignore[misc]

    def test_updates_do_not_mutate_the_original(self):
        first = apply_turn(None, _outcome())
        apply_turn(first, _outcome(result_label="a different result"))
        assert len(first.referents) == 2  # unchanged (operation + result)

    def test_deterministic(self):
        a = apply_turn(None, _outcome()).to_dict()
        b = apply_turn(None, _outcome()).to_dict()
        assert a == b


# ---------------------------------------------------------------------------
# D. Stable identity
# ---------------------------------------------------------------------------


class TestIdentity:
    def test_ids_are_deterministic_and_sequential(self):
        state = apply_turn(None, _outcome())
        assert state.referents[0].referent_id == "ref-000001"
        assert state.referents[1].referent_id == "ref-000002"
        assert state.sequence == 2

    def test_ids_do_not_collide_across_turns(self):
        state = apply_turn(None, _outcome())
        state = apply_turn(state, _outcome(result_label="second result"))
        ids = [r.referent_id for r in state.referents]
        assert len(ids) == len(set(ids))

    def test_referent_wraps_existing_ref(self):
        state = apply_turn(None, _outcome(operation_label="", proposal_ref="inv-42"))
        proposal = state.find(state.latest_proposal_id)
        assert proposal.ref == "inv-42"  # wraps the existing id, not a new one


# ---------------------------------------------------------------------------
# E. Supported referent kinds
# ---------------------------------------------------------------------------


class TestKinds:
    def test_operation_and_result(self):
        state = apply_turn(None, _outcome())
        kinds = {r.kind for r in state.referents}
        assert kinds == {KIND_OPERATION, KIND_RESULT}

    def test_finding_and_evidence(self):
        state = apply_turn(None, _outcome(findings=("a gap",), evidence=("tests/x.py",)))
        kinds = {r.kind for r in state.referents}
        assert {KIND_FINDING, KIND_EVIDENCE} <= kinds

    def test_proposal(self):
        state = apply_turn(None, _outcome(proposal_ref="p1"))
        assert any(r.kind == KIND_PROPOSAL for r in state.referents)

    def test_verification(self):
        state = apply_turn(None, _outcome(operation_origin="verification_request"))
        kinds = {r.kind for r in state.referents}
        assert KIND_VERIFICATION in kinds


# ---------------------------------------------------------------------------
# F. Lifecycle / status
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_operation_status_is_recorded(self):
        state = apply_turn(None, _outcome(operation_status=STATUS_FAILED, result_label=""))
        operation = state.find(state.latest_operation_id)
        assert operation.status == STATUS_FAILED

    def test_result_status_completed(self):
        state = apply_turn(None, _outcome())
        result = state.find(state.latest_result_id)
        assert result.status == STATUS_COMPLETED

    def test_proposal_status_proposed(self):
        state = apply_turn(None, _outcome(proposal_ref="p1"))
        assert state.find(state.latest_proposal_id).status == STATUS_PROPOSED

    def test_verification_status_verified(self):
        state = apply_turn(None, _outcome(operation_origin="verification_request"))
        verification = next(r for r in state.referents if r.kind == KIND_VERIFICATION)
        assert verification.status == STATUS_VERIFIED


# ---------------------------------------------------------------------------
# G/H. Relationship creation: operation -> result
# ---------------------------------------------------------------------------


class TestOperationResult:
    def test_operation_produced_result(self):
        state = apply_turn(None, _outcome())
        operation_id = state.latest_operation_id
        result_id = state.latest_result_id
        assert result_id and result_id != operation_id
        assert any(
            rel.source_id == operation_id
            and rel.relation == REL_PRODUCED
            and rel.target_id == result_id
            for rel in state.relations
        )

    def test_operation_exists_without_result(self):
        state = apply_turn(None, _outcome(result_label="", operation_status=STATUS_PENDING))
        assert state.latest_operation_id  # the operation is representable
        assert state.latest_result_id == ""  # with no result
        assert not any(r.kind == KIND_RESULT for r in state.referents)


# ---------------------------------------------------------------------------
# I. Result -> evidence / J. investigation -> finding / K. proposal / L. verification
# ---------------------------------------------------------------------------


class TestOtherRelationships:
    def test_result_supported_by_evidence(self):
        state = apply_turn(None, _outcome(evidence=("tests/x.py:10",)))
        result_id = state.latest_result_id
        assert any(rel.relation == REL_SUPPORTED_BY and rel.source_id == result_id for rel in state.relations)

    def test_investigation_produced_finding(self):
        state = apply_turn(None, _outcome(findings=("a concrete gap",)))
        operation_id = state.latest_operation_id
        finding = next(r for r in state.referents if r.kind == KIND_FINDING)
        assert any(
            rel.relation == REL_PRODUCED
            and rel.source_id == operation_id
            and rel.target_id == finding.referent_id
            for rel in state.relations
        )

    def test_proposal_concerns_operation(self):
        state = apply_turn(None, _outcome(proposal_ref="p1"))
        assert any(
            rel.relation == REL_CONCERNS and rel.source_id == state.latest_proposal_id
            for rel in state.relations
        )

    def test_operation_verified_by_verification(self):
        first = apply_turn(None, _outcome())
        prior_operation = first.latest_operation_id
        second = apply_turn(first, _outcome(operation_origin="verification_request", result_label=""))
        verification = next(r for r in second.referents if r.kind == KIND_VERIFICATION)
        assert any(
            rel.relation == REL_VERIFIED_BY
            and rel.source_id == prior_operation
            and rel.target_id == verification.referent_id
            for rel in second.relations
        )


# ---------------------------------------------------------------------------
# M. Repeated operations / supersession
# ---------------------------------------------------------------------------


class TestRepeatedOperations:
    def test_repeated_operations_produce_distinct_referents(self):
        state = apply_turn(None, _outcome())
        first_op = state.latest_operation_id
        state = apply_turn(state, _outcome(result_label="second result"))
        assert state.latest_operation_id != first_op
        assert len([r for r in state.referents if r.kind == KIND_OPERATION]) == 2
        assert len([r for r in state.referents if r.kind == KIND_RESULT]) == 2

    def test_new_result_supersedes_previous(self):
        state = apply_turn(None, _outcome())
        old_result = state.latest_result_id
        state = apply_turn(state, _outcome(result_label="second result"))
        new_result = state.latest_result_id
        assert state.find(old_result).status == STATUS_SUPERSEDED
        assert any(
            rel.relation == REL_SUPERSEDES
            and rel.source_id == new_result
            and rel.target_id == old_result
            for rel in state.relations
        )


# ---------------------------------------------------------------------------
# N/O. Failed / blocked / pending operations
# ---------------------------------------------------------------------------


class TestFailedBlocked:
    @pytest.mark.parametrize("status", [STATUS_FAILED, STATUS_BLOCKED, STATUS_PENDING])
    def test_non_success_statuses_representable(self, status):
        state = apply_turn(
            None, _outcome(operation_status=status, result_label="")
        )
        operation = state.find(state.latest_operation_id)
        assert operation.status == status
        assert state.latest_result_id == ""


# ---------------------------------------------------------------------------
# P. Bounded state
# ---------------------------------------------------------------------------


class TestBounds:
    def test_referents_are_bounded(self):
        state: DiscourseState | None = None
        for index in range(MAX_REFERENTS + 6):
            state = apply_turn(state, _outcome(result_label=f"result {index}"))
        assert len(state.referents) <= MAX_REFERENTS

    def test_evicted_referents_drop_their_relations(self):
        state: DiscourseState | None = None
        for index in range(MAX_REFERENTS + 6):
            state = apply_turn(state, _outcome(result_label=f"result {index}"))
        live = {r.referent_id for r in state.referents}
        for rel in state.relations:
            assert rel.source_id in live and rel.target_id in live

    def test_labels_are_bounded(self):
        state = apply_turn(None, _outcome(result_label="x" * 5000))
        assert len(state.find(state.latest_result_id).label) <= 200


# ---------------------------------------------------------------------------
# Q/R. Centralized update + single store
# ---------------------------------------------------------------------------


class TestOwnership:
    def test_manager_is_the_single_owner(self):
        manager = ConversationStateManager()
        manager.apply_discourse_turn(_outcome())
        assert isinstance(manager.state.discourse_state, DiscourseState)

    def test_malformed_outcome_is_ignored(self):
        manager = ConversationStateManager()
        before = manager.state
        assert manager.apply_discourse_turn("not-an-outcome") is before
        assert manager.state.discourse_state is None

    def test_conversation_state_owns_discourse_state(self):
        assert "discourse_state" in ConversationState.__dataclass_fields__

    def test_no_module_level_registry(self):
        import atlas.conversation.discourse_state as module

        source = open(module.__file__, encoding="utf-8").read()
        assert "global " not in source

    def test_discourse_module_does_not_import_conversation_state(self):
        import atlas.conversation.discourse_state as module

        source = open(module.__file__, encoding="utf-8").read()
        # No runtime back-import of the state module (which would be a cycle):
        # the module stays stdlib-only.
        assert "from atlas.conversation.conversation_state import" not in source
        assert "import atlas.conversation.conversation_state" not in source


# ---------------------------------------------------------------------------
# S. Malformed input / fail-soft
# ---------------------------------------------------------------------------


class TestMalformed:
    def test_referent_from_dict_rejects_malformed(self):
        assert Referent.from_dict(None) is None
        assert Referent.from_dict({"kind": KIND_RESULT}) is None  # no id

    def test_relation_from_dict_rejects_unknown_relation(self):
        assert Relation.from_dict({"source_id": "a", "relation": "nope", "target_id": "b"}) is None
        assert Relation.from_dict({"source_id": "a"}) is None

    def test_unknown_kind_degrades(self):
        referent = Referent.from_dict({"referent_id": "ref-000001", "kind": "wat"})
        assert referent.kind == KIND_OPERATION

    def test_empty_outcome_records_nothing(self):
        state = apply_turn(None, DiscourseTurnOutcome())
        assert state.referents == ()


# ---------------------------------------------------------------------------
# Service integration — the real recording path
# ---------------------------------------------------------------------------


class TestServiceIntegration:
    def test_investigation_records_operation_and_result(self):
        service = _service(_RecordingInvestigation())
        service.send("Investigate the memory architecture.")
        discourse = service.state_manager.state.discourse_state
        assert isinstance(discourse, DiscourseState)
        kinds = {r.kind for r in discourse.referents}
        assert KIND_OPERATION in kinds and KIND_RESULT in kinds
        operation = discourse.find(discourse.latest_operation_id)
        assert operation.origin == "investigation_request"

    def test_investigation_records_findings_and_evidence(self):
        service = _service(_DetailedInvestigation())
        service.send("Investigate the memory architecture.")
        discourse = service.state_manager.state.discourse_state
        kinds = {r.kind for r in discourse.referents}
        assert KIND_FINDING in kinds and KIND_EVIDENCE in kinds

    def test_greeting_records_no_operation(self):
        service = _service()
        service.send("Hello Atlas.")
        assert service.state_manager.state.discourse_state is None

    def test_existing_fields_remain_authoritative(self):
        service = _service(_RecordingInvestigation())
        service.send("Investigate the memory architecture.")
        state = service.state_manager.state
        assert state.current_investigation
        assert state.latest_result
        assert state.last_operation is not None
        assert isinstance(state.discourse_state, DiscourseState)


# ---------------------------------------------------------------------------
# T. Send / stream parity
# ---------------------------------------------------------------------------


class TestSendStreamParity:
    def test_investigation_parity(self):
        send_service = _service(_RecordingInvestigation())
        send_service.send("Investigate the memory architecture.")
        stream_service = _service(_RecordingInvestigation())
        list(stream_service.stream("Investigate the memory architecture."))
        assert (
            send_service.state_manager.state.discourse_state.to_dict()
            == stream_service.state_manager.state.discourse_state.to_dict()
        )

    def test_non_operation_parity(self):
        send_service = _service()
        send_service.send("Hello Atlas.")
        stream_service = _service()
        list(stream_service.stream("Hello Atlas."))
        assert send_service.state_manager.state.discourse_state is None
        assert stream_service.state_manager.state.discourse_state is None


# ---------------------------------------------------------------------------
# U. Governance invariants
# ---------------------------------------------------------------------------


class TestGovernance:
    def test_recording_a_proposal_does_not_approve_it(self):
        manager = ConversationStateManager()
        manager.apply_discourse_turn(
            _outcome(proposal_ref="prop-1")
        )
        # The registry only DESCRIBES the proposal.
        assert manager.state.discourse_state.find(
            manager.state.discourse_state.latest_proposal_id
        ).status == STATUS_PROPOSED

    def test_service_recording_creates_no_governance_objects(self):
        service = _service(_RecordingInvestigation())
        before = (
            dict(service._active_proposals),
            dict(service._active_evolution_proposals),
            dict(service._active_approval_requests),
        )
        service.send("Investigate the memory architecture.")
        after = (
            dict(service._active_proposals),
            dict(service._active_evolution_proposals),
            dict(service._active_approval_requests),
        )
        # A proposal referent may be recorded, but no approval/authority is created.
        assert service.state_manager.state.pending_approval_id is None
        assert set(after[1]) == set(before[1])
        assert set(after[2]) == set(before[2])


# ---------------------------------------------------------------------------
# V. Stage 1/2 compatibility
# ---------------------------------------------------------------------------


class TestCompatibility:
    def test_dialogue_state_still_recorded(self):
        service = _service(_RecordingInvestigation())
        service.send("Investigate the memory architecture.")
        assert service.state_manager.state.dialogue_state is not None
        assert service.last_meaning is not None

    def test_discourse_and_dialogue_coexist(self):
        service = _service(_RecordingInvestigation())
        service.send("Investigate the memory architecture.")
        payload = service.state_manager.state.to_dict()
        assert payload["dialogue_state"] is not None
        assert payload["discourse_state"] is not None
        json.dumps(payload)


# ---------------------------------------------------------------------------
# Stage 0 regression — Stage 3 must not change routing
# ---------------------------------------------------------------------------


class TestStage0Regression:
    def test_stage0_query_turns_no_longer_start_new_operations(self):
        """Stage 4 fix: "explain the result of the investigation ..." no longer
        starts a NEW investigation.

        (The compound lead turn now retains its result through the delegated
        investigation, so the follow-up resolves from it instead of failing
        closed.)
        """
        recording = _RecordingInvestigation()
        service = _service(recording)
        service.send(STAGE0_SEQUENCE[0])
        service.send(STAGE0_SEQUENCE[1])
        before = len(recording.calls)
        message = service.send(STAGE0_SEQUENCE[2])
        assert len(recording.calls) == before  # no NEW investigation
        assert not isinstance((message.metadata or {}).get("investigation"), dict)
