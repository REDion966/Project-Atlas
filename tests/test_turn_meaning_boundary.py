"""L1 — typed turn-meaning boundary contract tests (no provider dependency)."""

from __future__ import annotations

import dataclasses
import json
import pathlib
import unittest
from datetime import datetime
from unittest.mock import MagicMock

from atlas.ai.ai_manager import AIManager
from atlas.cognition.api import CognitionAPI
from atlas.cognition.decision import CognitionDecision
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.task_intake import TaskIntake
from atlas.conversation.turn_meaning import (
    MAX_SOURCE_TEXT_CHARS,
    TurnMeaning,
    accept_turn_meaning,
    build_turn_meaning,
)
from atlas.services.cognition_service import CognitionService

TURN = "Create a report using local data"


def _cognition_mock() -> MagicMock:
    cognition = MagicMock(spec=CognitionService)
    cognition.process.return_value = CognitionDecision(
        action="respond", reasoning="test", data={}
    )
    return cognition


def _service(cognition=None, task_intake=TaskIntake()):
    manager = AIManager()
    manager.initialize(provider="Mock Provider", model="atlas-mock-v1", timeout=300)
    cognition = cognition if cognition is not None else _cognition_mock()
    service = ConversationService(
        manager.service,
        cognition_api=CognitionAPI(cognition_service=cognition),
        task_intake=task_intake,
    )
    return service, cognition


class TestContractConstruction(unittest.TestCase):
    def test_construction_is_deterministic(self):
        spec = TaskIntake(now=datetime(2026, 1, 1)).intake(TURN)
        first = build_turn_meaning(spec, TURN)
        second = build_turn_meaning(spec, TURN)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_contract_is_immutable(self):
        contract = build_turn_meaning(TaskIntake().intake(TURN), TURN)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            contract.source_text = "changed"  # type: ignore[misc]

    def test_nested_source_isolation(self):
        spec = TaskIntake().intake(TURN)
        contract = build_turn_meaning(spec, TURN)
        before = contract.to_dict()
        # Mutating the source spec's mutable mapping after construction must not
        # change the contract.
        spec.context["resolved_reference"] = {"field": "x", "value": "mutated"}
        self.assertEqual(contract.to_dict(), before)
        # Mutating a returned payload must not change the contract either.
        payload = contract.to_dict()
        payload["intent"]["task_type"] = "mutated"
        self.assertEqual(contract.to_dict(), before)

    def test_role_separation(self):
        contract = build_turn_meaning(TaskIntake().intake(TURN), TURN)
        self.assertEqual(
            set(contract.to_dict()),
            {"intent", "uncertainty", "reference", "source_text", "provenance"},
        )
        self.assertEqual(contract.intent["task_type"], "action_request")
        self.assertNotIn("ambiguity", contract.intent)
        self.assertNotIn("context", contract.intent)
        self.assertIn("ambiguity_score", contract.uncertainty)
        self.assertEqual(contract.reference, {})
        self.assertEqual(contract.provenance["source"], "deterministic")

    def test_reference_block_carries_existing_evidence(self):
        spec = TaskIntake().intake(TURN)
        spec.context["resolved_reference"] = {
            "field": "current_investigation",
            "value": "memory architecture",
        }
        contract = build_turn_meaning(spec, TURN)
        self.assertEqual(
            contract.reference,
            {"field": "current_investigation", "value": "memory architecture"},
        )

    def test_json_safe_serialization(self):
        contract = build_turn_meaning(TaskIntake().intake(TURN), TURN)
        json.dumps(contract.to_dict())

    def test_source_text_is_bounded(self):
        contract = build_turn_meaning(
            TaskIntake().intake(TURN), "y" * (MAX_SOURCE_TEXT_CHARS + 50)
        )
        self.assertEqual(len(contract.source_text), MAX_SOURCE_TEXT_CHARS)


class TestBoundaryAcceptance(unittest.TestCase):
    def test_valid_contract_accepted_unchanged(self):
        contract = build_turn_meaning(TaskIntake().intake(TURN), TURN)
        self.assertIs(accept_turn_meaning(contract), contract)

    def test_absent_contract_is_none(self):
        self.assertIsNone(accept_turn_meaning(None))

    def test_malformed_contract_fails_closed(self):
        spec = TaskIntake().intake(TURN)
        malformed = (
            {},
            "not-a-contract",
            42,
            object(),
            ["intent"],
            spec,  # a TaskSpec is not the contract
        )
        for value in malformed:
            with self.subTest(value=type(value).__name__):
                self.assertIsNone(accept_turn_meaning(value))

    def test_boundary_drops_malformed_without_changing_call_shape(self):
        cognition = _cognition_mock()
        api = CognitionAPI(cognition_service=cognition)
        api.process(user_input="u", metadata=None, goal="g", turn_meaning={"bad": True})
        cognition.process.assert_called_once_with(
            user_input="u", memory=None, metadata=None, goal="g"
        )

    def test_boundary_forwards_valid_contract_unchanged(self):
        cognition = _cognition_mock()
        api = CognitionAPI(cognition_service=cognition)
        contract = build_turn_meaning(TaskIntake().intake(TURN), TURN)
        api.process(user_input="u", metadata=None, goal="g", turn_meaning=contract)
        forwarded = cognition.process.call_args.kwargs["turn_meaning"]
        self.assertIs(forwarded, contract)

    def test_validation_does_not_consume_content(self):
        # Shape-valid but content-nonsensical contracts are still accepted
        # unchanged: the boundary inspects shape/type only.
        cognition = _cognition_mock()
        api = CognitionAPI(cognition_service=cognition)
        odd = TurnMeaning(intent={}, uncertainty={}, reference={}, source_text="", provenance={})
        api.process(user_input="u", metadata=None, goal="g", turn_meaning=odd)
        self.assertIs(cognition.process.call_args.kwargs["turn_meaning"], odd)
        decision = api.process(user_input="u", metadata=None, goal="g", turn_meaning=odd)
        self.assertEqual(decision.action, "respond")

    def test_contract_module_is_model_free(self):
        import atlas.conversation.turn_meaning as module

        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ("atlas.ai", "requests", "openai", "ollama", "anthropic"):
            self.assertNotIn(forbidden, source)


class TestConversationHandoff(unittest.TestCase):
    def test_send_constructs_and_crosses_boundary(self):
        service, cognition = _service()
        service.send(TURN)
        kwargs = cognition.process.call_args.kwargs
        passed = kwargs.get("turn_meaning")
        self.assertIsInstance(passed, TurnMeaning)
        self.assertEqual(passed.intent["task_type"], "action_request")
        self.assertEqual(passed.provenance["source"], "deterministic")
        self.assertTrue(passed.source_text)
        # Legacy metadata payload is untouched.
        self.assertEqual(kwargs["metadata"]["task"]["task_type"], "action_request")

    def test_stream_constructs_and_crosses_boundary(self):
        service, cognition = _service()
        list(service.stream(TURN))
        passed = cognition.process.call_args.kwargs.get("turn_meaning")
        self.assertIsInstance(passed, TurnMeaning)
        self.assertEqual(passed.intent["task_type"], "action_request")

    def test_send_and_stream_meanings_are_equivalent(self):
        send_service, send_cognition = _service()
        send_service.send(TURN)
        stream_service, stream_cognition = _service()
        list(stream_service.stream(TURN))
        self.assertEqual(
            send_cognition.process.call_args.kwargs["turn_meaning"].to_dict(),
            stream_cognition.process.call_args.kwargs["turn_meaning"].to_dict(),
        )

    def test_pinned_cognition_metadata_unchanged(self):
        service, _cognition = _service()
        captured = []
        original = service._prompt_builder.build
        service._prompt_builder.build = lambda ctx: (captured.extend(ctx), original(ctx))[1]
        service.send(TURN)
        cognition_messages = [
            m
            for m in captured
            if getattr(m, "metadata", None) and "cognition" in m.metadata
        ]
        self.assertTrue(cognition_messages)
        task = cognition_messages[0].metadata["cognition"]["task"]
        self.assertEqual(task["task_type"], "action_request")
        self.assertEqual(task["source"], "deterministic")

    def test_legacy_call_shape_unchanged(self):
        service, cognition = _service(task_intake=None)
        service.send("Hello legacy")
        cognition.process.assert_called_once_with(
            user_input="Hello legacy",
            memory=None,
            metadata=None,
            goal="Hello legacy",
        )


if __name__ == "__main__":
    unittest.main()
