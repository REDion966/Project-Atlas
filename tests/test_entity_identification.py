"""L4.3 — bounded deterministic entity identification tests.

Covers:
- the pure identification mechanism (separator tolerance, word boundaries,
  bounds, determinism, JSON-safety, model independence);
- the conversation-layer integration: bounded evidence on
  ``TaskSpec.context``, the fail-closed default with no catalog, and the
  single-entity ``current_subject`` population that makes the already-shipped
  subject references reachable;
- preservation: routing, governance fields, and the L1 ``TurnMeaning``
  contract are untouched by identification.

All tests are pure/deterministic. No provider network calls are made.
"""

from __future__ import annotations

import ast
import hashlib
import json
import unittest
from pathlib import Path

from atlas.ai.ai_manager import AIManager
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.entity_identification import (
    IDENTIFIED_ENTITIES_KEY,
    MAX_IDENTIFIED_ENTITIES,
    EntityCatalog,
    IdentifiedEntity,
    identify_entities,
)
from atlas.conversation.reference_resolution import ReferenceResolutionStatus
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.conversation.turn_meaning import TurnMeaning, build_turn_meaning

CATALOG = EntityCatalog.from_names(
    {
        "capability": ["code_inspector", "knowledge_search"],
        "tool": ["workspace_search"],
    }
)

TOOL_TURN = "What does code_inspector do?"

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "atlas"
    / "conversation"
    / "entity_identification.py"
)


def _input_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _service(catalog: EntityCatalog | None = CATALOG) -> ConversationService:
    manager = AIManager()
    manager.initialize(provider="Mock Provider", model="atlas-mock-v1", timeout=300)
    return ConversationService(
        manager.service,
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        entity_catalog=catalog,
    )


class TestEntityCatalog(unittest.TestCase):
    def test_from_names_dedupes_case_insensitively(self):
        catalog = EntityCatalog.from_names(
            {"capability": ["Code_Inspector"], "tool": ["code_inspector"]}
        )
        self.assertEqual(catalog.entries, (("Code_Inspector", "capability"),))

    def test_first_kind_wins_and_order_is_callers(self):
        catalog = EntityCatalog.from_names(
            {"capability": ["b_cap", "a_cap"], "tool": ["a_cap", "t_tool"]}
        )
        self.assertEqual(
            catalog.entries,
            (("b_cap", "capability"), ("a_cap", "capability"), ("t_tool", "tool")),
        )

    def test_ignores_blank_and_non_string_names(self):
        catalog = EntityCatalog.from_names({"tool": ["", "   ", None, 5, "ok_tool"]})
        self.assertEqual(catalog.entries, (("ok_tool", "tool"),))

    def test_empty_catalog_matches_nothing(self):
        self.assertEqual(identify_entities("code_inspector", EntityCatalog()), ())


class TestIdentifyEntities(unittest.TestCase):
    def test_explicit_name_is_identified_with_kind(self):
        found = identify_entities(TOOL_TURN, CATALOG)
        self.assertEqual(
            [entity.to_dict() for entity in found],
            [{"name": "code_inspector", "kind": "capability"}],
        )

    def test_separator_variants_are_identified(self):
        for text in (
            "code_inspector",
            "code inspector",
            "code-inspector",
            "code.inspector",
            "Code_Inspector",
            "show me CODE  INSPECTOR",
        ):
            with self.subTest(text=text):
                found = identify_entities(text, CATALOG)
                self.assertEqual([entity.name for entity in found], ["code_inspector"])

    def test_word_boundaries_reject_partial_and_embedded_names(self):
        for text in (
            "xcode_inspector",
            "code_inspect",
            "code_inspectors",
            "code inspectorx",
        ):
            with self.subTest(text=text):
                self.assertEqual(identify_entities(text, CATALOG), ())

    def test_unknown_text_yields_nothing(self):
        for text in ("hello there", "what can you do?", "", "   ", "banana"):
            with self.subTest(text=text):
                self.assertEqual(identify_entities(text, CATALOG), ())

    def test_multiple_entities_reported_most_specific_first(self):
        found = identify_entities(
            "compare code_inspector and workspace_search", CATALOG
        )
        self.assertEqual(
            [entity.name for entity in found],
            ["workspace_search", "code_inspector"],
        )

    def test_result_is_bounded(self):
        names = [f"entity_number_{index:02d}" for index in range(12)]
        catalog = EntityCatalog.from_names({"tool": names})
        found = identify_entities(" ".join(names), catalog)
        self.assertEqual(len(found), MAX_IDENTIFIED_ENTITIES)
        self.assertEqual(
            [entity.name for entity in found],
            sorted(names, key=lambda name: (-len(name), name))[
                :MAX_IDENTIFIED_ENTITIES
            ],
        )

    def test_non_string_and_no_catalog_are_fail_closed(self):
        self.assertEqual(identify_entities(None, CATALOG), ())
        self.assertEqual(identify_entities("code_inspector", None), ())

    def test_deterministic_and_position_independent(self):
        first = identify_entities("code_inspector and workspace_search", CATALOG)
        for _ in range(20):
            self.assertEqual(
                identify_entities("code_inspector and workspace_search", CATALOG),
                first,
            )
        self.assertEqual(
            identify_entities("workspace_search and code_inspector", CATALOG), first
        )

    def test_entity_evidence_is_json_safe_and_immutable(self):
        entity = IdentifiedEntity(name="code_inspector", kind="capability")
        self.assertEqual(
            json.loads(json.dumps(entity.to_dict())),
            {"name": "code_inspector", "kind": "capability"},
        )
        with self.assertRaises(AttributeError):
            entity.name = "other"

    def test_module_is_model_free(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertEqual(
            sorted(imported),
            [
                "__future__",
                "atlas.conversation.normalization",
                "dataclasses",
                "re",
                "typing",
            ],
        )


class TestConversationServiceIdentification(unittest.TestCase):
    def setUp(self):
        self.svc = _service()

    def _identify(self, text):
        spec = self.svc._intake(text, len(self.svc.conversation.messages))
        return spec, self.svc._apply_entity_identification(spec, text)

    def test_entities_are_attached_as_bounded_evidence(self):
        _, identified = self._identify(TOOL_TURN)
        self.assertEqual(
            identified.context[IDENTIFIED_ENTITIES_KEY],
            [{"name": "code_inspector", "kind": "capability"}],
        )
        serialized = json.loads(json.dumps(identified.to_dict()))
        self.assertEqual(
            serialized["context"][IDENTIFIED_ENTITIES_KEY],
            [{"name": "code_inspector", "kind": "capability"}],
        )

    def test_identification_preserves_the_intake_contract(self):
        spec, identified = self._identify(TOOL_TURN)
        self.assertIs(identified.task_type, spec.task_type)
        self.assertIs(identified.intent, spec.intent)
        self.assertEqual(identified.ambiguity, spec.ambiguity)
        self.assertEqual(identified.confidence, spec.confidence)
        self.assertEqual(identified.needs_clarification, spec.needs_clarification)
        self.assertEqual(identified.source, spec.source)
        self.assertEqual(identified.verified, spec.verified)
        self.assertEqual(identified.input_hash, spec.input_hash)
        self.assertEqual(identified.input_hash, _input_hash(TOOL_TURN))

    def test_identification_does_not_change_routing_or_response(self):
        with_catalog = _service(CATALOG).send(TOOL_TURN)
        without_catalog = _service(None).send(TOOL_TURN)
        self.assertEqual(with_catalog.content, without_catalog.content)
        self.assertEqual(
            with_catalog.metadata.get("builtin_intent"),
            without_catalog.metadata.get("builtin_intent"),
        )

    def test_single_entity_populates_the_bounded_subject_slot(self):
        self.assertIsNone(self.svc.state_manager.state.current_subject)
        self.svc.send(TOOL_TURN)
        self.assertEqual(self.svc.state_manager.state.current_subject, "code_inspector")

    def test_multiple_entities_do_not_guess_a_subject(self):
        self.svc.send("compare code_inspector and workspace_search")
        state = self.svc.state_manager.state
        self.assertIsNone(state.current_subject)

    def test_dead_subject_reference_becomes_reachable(self):
        reference = "tell me more about this topic"
        self.assertIs(
            _service(None).resolve_reference(reference).status,
            ReferenceResolutionStatus.UNRESOLVED,
        )
        self.svc.send(TOOL_TURN)
        result = self.svc.resolve_reference(reference)
        self.assertIs(result.status, ReferenceResolutionStatus.RESOLVED)
        self.assertEqual(result.resolved_field, "current_subject")
        self.assertEqual(result.resolved_value, "code_inspector")

    def test_identification_is_a_noop_without_a_catalog(self):
        service = _service(None)
        self.assertIsNone(service.entity_catalog)
        spec = service._intake(TOOL_TURN, 1)
        self.assertIs(service._apply_entity_identification(spec, TOOL_TURN), spec)
        self.assertNotIn(IDENTIFIED_ENTITIES_KEY, spec.context)
        service.send(TOOL_TURN)
        self.assertIsNone(service.state_manager.state.current_subject)

    def test_whitespace_variants_identify_identically(self):
        _, baseline = self._identify(TOOL_TURN)
        for text in (
            "What does  code_inspector  do?",
            "What does\tcode_inspector\tdo?",
            "What does\ncode_inspector\ndo?",
            "  " + TOOL_TURN + "  ",
        ):
            with self.subTest(text=text):
                spec, identified = self._identify(text)
                self.assertEqual(
                    identified.context[IDENTIFIED_ENTITIES_KEY],
                    baseline.context[IDENTIFIED_ENTITIES_KEY],
                )
                self.assertEqual(spec.input_hash, _input_hash(text))

    def test_governed_turn_is_identified_without_gaining_authority(self):
        text = "Add a new capability for code_inspector"
        spec, identified = self._identify(text)
        self.assertIs(spec.task_type, TaskType.DEVELOPMENT_REQUEST)
        self.assertIs(identified.task_type, TaskType.DEVELOPMENT_REQUEST)
        self.assertEqual(identified.needs_clarification, spec.needs_clarification)
        self.assertEqual(
            identified.context[IDENTIFIED_ENTITIES_KEY],
            [{"name": "code_inspector", "kind": "capability"}],
        )
        self.assertEqual(self.svc._active_approval_requests, {})
        self.assertEqual(self.svc._active_proposals, {})

    def test_turn_meaning_contract_is_unchanged(self):
        spec, identified = self._identify(TOOL_TURN)
        meaning = build_turn_meaning(identified, TOOL_TURN)
        self.assertEqual(
            set(TurnMeaning.__dataclass_fields__),
            {"intent", "uncertainty", "reference", "source_text", "provenance"},
        )
        self.assertEqual(meaning.reference, {})
        self.assertNotIn(IDENTIFIED_ENTITIES_KEY, meaning.intent)
        self.assertEqual(meaning.source_text, TOOL_TURN)
        self.assertEqual(meaning.provenance["source"], "deterministic")
        self.assertEqual(meaning.provenance["input_hash"], spec.input_hash)

    def test_send_and_stream_agree(self):
        sent_service = _service()
        sent = sent_service.send(TOOL_TURN)
        streamed_service = _service()
        chunks = list(streamed_service.stream(TOOL_TURN))
        self.assertEqual("".join(chunks), sent.content)
        self.assertEqual(
            sent_service.state_manager.state.current_subject,
            streamed_service.state_manager.state.current_subject,
        )

    def test_repeated_identification_is_stable(self):
        spec = self.svc._intake(TOOL_TURN, 1)
        payloads = {
            json.dumps(
                self.svc._apply_entity_identification(spec, TOOL_TURN).to_dict()[
                    "context"
                ][IDENTIFIED_ENTITIES_KEY],
                sort_keys=True,
            )
            for _ in range(20)
        }
        self.assertEqual(len(payloads), 1)


if __name__ == "__main__":
    unittest.main()
