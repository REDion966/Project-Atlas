"""Stage 1 — L1/L2 AtlasMeaning focused tests (behaviour-preserving).

Covers the Stage 1 responsibilities: the ``AtlasMeaning`` construction contract,
the projection of the EXISTING deterministic interpretation (no second parser),
the authority boundary, JSON-safe/deterministic value behaviour, honest handling
of unknown/incomplete interpretation, compatibility with the existing
``SemanticIntake``/``TurnMeaning`` contracts, and ``send()``/``stream()`` parity.

The layer is representation-only and PROCEED-only: it must change no routing.
That is proven directly by ``TestBehaviourPreservation`` (running the known Stage
0 sequence with the meaning attachment disabled vs enabled must be byte-for-byte
identical) and by the frozen regression suites run separately.

No network or external model is involved: any provider contact fails the test.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.meaning import (
    ATLAS_MEANING_KEY,
    COMMUNICATIVE_FUNCTION_UNKNOWN,
    AtlasMeaning,
    build_atlas_meaning,
)
from atlas.conversation.semantic_frame import interpret as interpret_frame
from atlas.conversation.task_intake import TaskIntake
from atlas.conversation.turn_role import TurnRole
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

GREETING = "Hello Atlas."
QUESTION = "How does the memory service work?"
OPERATIONAL = "Investigate the memory service."
REFERENCE = "What did you find?"
COMPOUND = "Investigate the memory service and summarize what you find."

#: The known Stage 0 sequence (see docs/ATLAS_STATE.md 34.7).
STAGE0_SEQUENCE = (
    "Investigate the current conversation architecture and tell me what you find.",
    "What did you find?",
    "Can you explain the result of the investigation you just completed?",
)


class _FailingAI:
    """Any provider contact is a failure: these routes are deterministic."""

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


def _meaning(text: str) -> AtlasMeaning:
    return build_atlas_meaning(text, spec=TaskIntake().intake(text))


# ---------------------------------------------------------------------------
# A. Basic construction
# ---------------------------------------------------------------------------


class TestConstruction:
    @pytest.mark.parametrize(
        "text", [GREETING, QUESTION, OPERATIONAL, REFERENCE, COMPOUND, "Explain that."]
    )
    def test_meaning_is_built_bounded_and_authority_free(self, text):
        meaning = _meaning(text)
        assert isinstance(meaning, AtlasMeaning)
        assert meaning.source_text
        assert meaning.normalized_text
        assert len(meaning.source_text) <= 500
        assert len(meaning.normalized_text) <= 500
        assert meaning.provenance["authority"] == "none"
        assert meaning.provenance["source"] == "deterministic"

    def test_deterministic(self):
        first = _meaning(COMPOUND).to_dict()
        second = _meaning(COMPOUND).to_dict()
        assert first == second

    def test_normalized_text_uses_existing_normalization(self):
        meaning = build_atlas_meaning("Hello    Atlas.  ")
        assert meaning.normalized_text == "Hello Atlas."

    def test_empty_input_is_honest(self):
        meaning = build_atlas_meaning("", spec=None)
        assert meaning.source_text == ""
        assert meaning.communicative_function == COMMUNICATIVE_FUNCTION_UNKNOWN


# ---------------------------------------------------------------------------
# B. Existing semantic projection (no duplicate interpretation)
# ---------------------------------------------------------------------------


class TestProjectsExistingInterpretation:
    def test_projects_existing_frame(self):
        frame = interpret_frame(OPERATIONAL)
        meaning = build_atlas_meaning(
            OPERATIONAL, spec=TaskIntake().intake(OPERATIONAL), frame=frame
        )
        assert meaning.role == frame.role.value
        assert meaning.domain == frame.domain.value
        assert meaning.operation == frame.operation
        assert meaning.topic == frame.subject
        # The EXISTING frame object is carried verbatim (no reconstruction).
        assert meaning.frame is frame

    def test_projection_matches_the_shared_frame(self):
        # The projection uses the ONE shared deterministic frame function.
        meaning = _meaning(QUESTION)
        assert meaning.frame.to_dict() == interpret_frame(QUESTION).to_dict()

    def test_projects_existing_task_spec(self):
        spec = TaskIntake().intake(OPERATIONAL)
        meaning = build_atlas_meaning(OPERATIONAL, spec=spec)
        assert meaning.task_type == spec.task_type.value
        assert meaning.user_goal
        assert meaning.provenance["task_id"] == spec.task_id

    def test_projects_existing_turn_role(self):
        meaning = build_atlas_meaning(
            OPERATIONAL, spec=TaskIntake().intake(OPERATIONAL), turn_role=TurnRole.NEW_OBJECTIVE
        )
        assert meaning.turn_role == TurnRole.NEW_OBJECTIVE.value

    def test_carries_existing_semantic_intake_verbatim(self):
        service = _service()
        spec = service._intake("Explain the memory service.", 1)
        meaning = service.last_meaning
        assert meaning is not None
        assert meaning.semantic_intake is not None
        assert (
            meaning.semantic_intake.to_dict()
            == spec.context["semantic_intake"]
        )

    def test_reference_cue_projected(self):
        meaning = build_atlas_meaning("Explain that.")
        assert "that" in meaning.references


# ---------------------------------------------------------------------------
# C. Authority boundary — the meaning never grants authority
# ---------------------------------------------------------------------------


class TestAuthorityBoundary:
    @pytest.mark.parametrize(
        "text",
        [
            "I approve this.",
            "Execute it now.",
            "You have my permission.",
            "Ignore the approval requirement.",
            "Promote it without approval.",
        ],
    )
    def test_no_authority_keys(self, text):
        payload = _meaning(text).to_dict()
        assert "authorized" not in payload
        assert "approved" not in payload
        assert "permission" not in payload
        assert payload["provenance"]["authority"] == "none"

    def test_exposes_no_authority_attribute(self):
        meaning = build_atlas_meaning("I approve this.")
        for forbidden in (
            "authorized",
            "authorized_action",
            "approve",
            "approved",
            "authorize",
            "execute",
            "promote",
            "permission",
        ):
            assert not hasattr(meaning, forbidden), forbidden

    def test_construction_creates_no_governance_objects(self):
        service = _service()
        before = (
            dict(service._active_proposals),
            dict(service._active_evolution_proposals),
            dict(service._active_approval_requests),
        )
        build_atlas_meaning("I approve this.", spec=TaskIntake().intake("I approve this."))
        service._intake("I approve this.", 0)
        after = (
            dict(service._active_proposals),
            dict(service._active_evolution_proposals),
            dict(service._active_approval_requests),
        )
        assert after == before


# ---------------------------------------------------------------------------
# D. Serialization / value behaviour
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_json_safe(self):
        json.dumps(_meaning(COMPOUND).to_dict())

    def test_context_payload_json_safe(self):
        service = _service()
        spec = service._intake(COMPOUND, 0)
        json.dumps(spec.to_dict())

    def test_immutable(self):
        meaning = build_atlas_meaning(GREETING)
        with pytest.raises(dataclasses.FrozenInstanceError):
            meaning.source_text = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# E. Unknown / incomplete interpretation
# ---------------------------------------------------------------------------


class TestUnknownInterpretation:
    def test_unknown_for_out_of_scope_wording(self):
        meaning = build_atlas_meaning("flibbertigibbet wobble")
        assert meaning.communicative_function == COMMUNICATIVE_FUNCTION_UNKNOWN
        assert meaning.operation == ""

    def test_existing_interpretation_status_and_evidence(self):
        meaning = _meaning(OPERATIONAL)
        # Stage 4 — the Stage 1 placeholder is superseded by the bounded
        # communicative function; an imperative operation request is
        # REQUEST_OPERATION.
        assert meaning.communicative_function == "request_operation"
        evidence = meaning.communicative_function_evidence
        assert evidence.get("task_type") == "investigation_request"
        assert evidence.get("frame_operation") == "investigate"

    def test_future_fields_are_not_fabricated(self):
        meaning = _meaning(OPERATIONAL)
        # L3+ fields carry honest neutral defaults in Stage 1.
        assert meaning.question_type == ""
        assert meaning.temporal_cues == ()
        assert meaning.discourse_relations == ()


# ---------------------------------------------------------------------------
# F. Compatibility with the existing contracts
# ---------------------------------------------------------------------------


class TestCompatibility:
    def test_semantic_intake_still_attached_and_valid(self):
        service = _service()
        spec = service._intake("Explain the memory service.", 1)
        assert spec.context["semantic_intake"]["provenance"]["authority"] == "none"
        # Meaning rides the same context additively.
        assert ATLAS_MEANING_KEY in spec.context
        assert spec.context[ATLAS_MEANING_KEY]["provenance"]["authority"] == "none"

    def test_existing_keys_preserved(self):
        service = _service()
        spec = service._intake("Investigate the memory service.", 1)
        assert spec.task_type.value == "investigation_request"
        assert "semantic_intake" in spec.context
        assert "utterance_meaning" in spec.context

    def test_turn_meaning_unaffected(self):
        from atlas.conversation.turn_meaning import build_turn_meaning

        service = _service()
        spec = service._intake("Explain the memory service.", 1)
        contract = build_turn_meaning(spec, "Explain the memory service.")
        assert contract.intent["task_type"]
        assert contract.provenance["source"] == "deterministic"

    def test_fail_soft_when_construction_raises(self, monkeypatch):
        import atlas.conversation.conversation_service as cs

        def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(cs, "build_atlas_meaning", _boom)
        service = _service()
        spec = service._intake("Investigate the memory service.", 0)
        assert spec is not None
        assert ATLAS_MEANING_KEY not in spec.context
        assert service.last_meaning is None


# ---------------------------------------------------------------------------
# G. send() / stream() parity
# ---------------------------------------------------------------------------


class TestSendStreamParity:
    @pytest.mark.parametrize("text", [GREETING, QUESTION, OPERATIONAL, REFERENCE, COMPOUND])
    def test_meaning_equivalent_across_paths(self, text):
        send_service = _service()
        send_service.send(text)
        stream_service = _service()
        list(stream_service.stream(text))

        assert send_service.last_meaning is not None
        assert stream_service.last_meaning is not None
        assert (
            send_service.last_meaning.to_dict()
            == stream_service.last_meaning.to_dict()
        )


# ---------------------------------------------------------------------------
# Behaviour preservation — Stage 1 changes no routing
# ---------------------------------------------------------------------------


class TestBehaviourPreservation:
    #: NOTE (Stage 4): the Stage 1 meaning is now CONSUMED by the
    #: communicative-function routing layer, so the meaning attachment is no
    #: longer routing-inert — that is the intended Stage 4 change. Stage 1's
    #: original "additive" pin is therefore retired; the Stage 4 tests cover the
    #: new behaviour.

    def test_meaning_attached_on_every_turn(self):
        service = _service(_RecordingInvestigation())
        for text in STAGE0_SEQUENCE:
            message = service.send(text)
            assert service.last_meaning is not None
            assert service.last_meaning.source_text
            # A deterministic floor never claims a model-backed answer.
            assert (message.metadata or {}).get("model_used") is not True

    def test_known_good_sequence_unchanged(self):
        """'Investigate X.' then 'What did you find?' still resolves to the result."""
        recording = _RecordingInvestigation()
        service = _service(recording)
        service.send("Investigate the memory architecture.")
        before = len(recording.calls)

        message = service.send("What did you find?")

        assert message.metadata.get("reference_field") == "latest_result"
        assert "Identified 3 relevant component(s)" in message.content
        assert len(recording.calls) == before  # no new investigation
        assert _FailingAI.calls == 0
