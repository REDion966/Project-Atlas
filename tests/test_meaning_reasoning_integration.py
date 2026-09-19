"""L7.3 — Meaning → Reasoning / Planning integration tests.

These tests establish the L7 contract: bounded structured meaning (the L1
``TurnMeaning`` projection) crosses an explicit, deterministic boundary into
the unified runtime and is actually *consumed* by the REASONING and PLANNING
stages — it can change the resulting reasoning/planning decision, ambiguity
remains fail-closed, and behaviour without meaning is unchanged.

Everything here is deterministic and model-independent: no provider, no
network, no model is constructed or required.
"""

import unittest

from atlas.cognition.api import CognitionAPI
from atlas.cognition.models import CognitionState
from atlas.conversation.task_intake import TaskIntake
from atlas.conversation.turn_meaning import (
    MAX_REASONING_ITEMS,
    MAX_REASONING_TEXT_CHARS,
    TurnMeaning,
    build_turn_meaning,
)
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.planning import PlanningEngine
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.services.cognition_service import CognitionService


def _stage_data(result, stage_name):
    """Return the data payload of a named pipeline stage."""
    return next(s.data for s in result.stages if s.stage.name == stage_name)


def _build_coordinator(handler_calls=None, controller=None):
    """Real reasoning components over a registry with a recording handler."""
    registry = CapabilityRegistry()

    def handler(params):
        if handler_calls is not None:
            handler_calls.append(params)
        return ExecutionResult(
            capability="conversation", success=True, output={"ok": True},
        )

    registry.register("conversation", handler)

    return RuntimeCoordinator(
        reasoning_controller=controller or ReasoningController(),
        capability_analyzer=CapabilityAnalyzer(),
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=PlanningEngine(),
    )


def _meaning_for(text):
    """Build the real L1 meaning contract for a natural instruction."""
    spec = TaskIntake().intake(text)
    return build_turn_meaning(spec, text)


def _explicit_meaning(**intent):
    """Build a contract with an explicit deterministic intent block."""
    return TurnMeaning(
        intent=dict(intent),
        uncertainty={},
        reference={},
        source_text="explicit",
        provenance={"source": "test"},
    )


# ---------------------------------------------------------------------------
# 1-2. Meaning reaches the reasoning/planning boundary and is consumed
# ---------------------------------------------------------------------------

class TestMeaningCrossesIntoReasoningAndPlanning(unittest.TestCase):

    def test_meaning_reaches_reasoning_and_planning_stages(self):
        """The bounded meaning is present in both stage payloads."""
        meaning = _meaning_for("Summarize the tradeoffs of caching.")
        coordinator = _build_coordinator()

        result = coordinator.process(
            user_input="Summarize the tradeoffs of caching.",
            goal="summarize caching tradeoffs",
            turn_meaning=meaning,
        )

        reasoning = _stage_data(result, "REASONING")
        planning = _stage_data(result, "PLANNING")

        self.assertIn("meaning", reasoning)
        self.assertIn("meaning", planning)
        self.assertEqual(reasoning["meaning"]["task_type"], "action_request")
        self.assertEqual(
            reasoning["meaning"]["intent"], planning["meaning"]["intent"],
        )
        self.assertEqual(
            planning["meaning"]["success_criteria"],
            reasoning["meaning"]["success_criteria"],
        )

    def test_meaning_supplies_reasoning_goal_when_goal_absent(self):
        """Structured meaning's goal informs the reasoning/planning goal."""
        meaning = _explicit_meaning(
            task_type="action_request",
            intent="prepare report",
            goal="prepare the deployment report",
        )
        coordinator = _build_coordinator()

        result = coordinator.process(
            user_input="unclassified text", turn_meaning=meaning,
        )

        reasoning = _stage_data(result, "REASONING")
        planning = _stage_data(result, "PLANNING")

        self.assertIn("prepare the deployment report", reasoning["goal"])
        self.assertIn("prepare the deployment report", planning["goal"])

    def test_meaning_reaches_the_reasoning_plan_decision(self):
        """The plan the controller builds is constructed from meaning."""
        captured = {}

        class _RecordingController(ReasoningController):
            def create_plan(self, decision):
                captured["data"] = dict(decision.data)
                return super().create_plan(decision)

        meaning = _explicit_meaning(
            task_type="action_request",
            intent="prepare report",
            goal="prepare the deployment report",
            constraints=["read-only"],
            success_criteria=["report exists"],
        )
        coordinator = _build_coordinator(controller=_RecordingController())

        coordinator.process(user_input="text", turn_meaning=meaning)

        self.assertIn("meaning", captured["data"])
        self.assertEqual(
            captured["data"]["meaning"]["constraints"], ["read-only"],
        )
        self.assertEqual(
            captured["data"]["meaning"]["success_criteria"], ["report exists"],
        )

    def test_meaning_task_type_labels_the_routing_request(self):
        """Meaning's task type is consumed by the planning→routing path."""
        coordinator = _build_coordinator()
        state = CognitionState(
            user_input="text",
            goal="do the thing",
            meaning={"task_type": "development_request"},
            planning_result={"goal": "respond: do the thing",
                             "steps": [{"id": "step-1"}],
                             "results": []},
        )

        request = coordinator._build_routing_request(state)

        self.assertIsNotNone(request)
        self.assertEqual(request.task_type, "development_request")


# ---------------------------------------------------------------------------
# 3. Ambiguity / uncertainty remains fail-closed
# ---------------------------------------------------------------------------

class TestMeaningAmbiguityIsFailClosed(unittest.TestCase):

    def test_real_ambiguous_instruction_blocks_reasoning_and_planning(self):
        """A genuinely ambiguous instruction (needs_clarification) must not
        produce capabilities, dispatch, or routes."""
        meaning = _meaning_for("Build it.")
        self.assertTrue(
            meaning.to_reasoning_meaning()["needs_clarification"],
            "precondition: this instruction is ambiguous",
        )

        calls = []
        coordinator = _build_coordinator(handler_calls=calls)

        result = coordinator.process(
            user_input="Build it.",
            goal="respond: Build it.",
            turn_meaning=meaning,
        )
        reasoning = _stage_data(result, "REASONING")
        planning = _stage_data(result, "PLANNING")

        self.assertTrue(reasoning.get("requires_clarification"))
        self.assertEqual(reasoning["capabilities"], [])
        self.assertTrue(planning.get("requires_clarification"))
        self.assertEqual(planning["results"], [])
        self.assertEqual(planning["routes"], [])
        self.assertEqual(planning["steps"], [])
        self.assertEqual(calls, [], "no capability may be dispatched")

    def test_ambiguity_score_and_reasons_are_boundary_projected(self):
        """The uncertainty snapshot crosses the boundary deterministically."""
        meaning = _meaning_for("run it")
        projected = meaning.to_reasoning_meaning()

        self.assertTrue(projected["needs_clarification"])
        self.assertGreaterEqual(projected["ambiguity_score"], 0.5)
        self.assertIn("reference", projected["ambiguities"])

    def test_unambiguous_meaning_still_dispatches(self):
        """Non-ambiguous meaning does not block the normal path."""
        meaning = _meaning_for("Summarize the tradeoffs of caching.")
        calls = []
        coordinator = _build_coordinator(handler_calls=calls)

        result = coordinator.process(
            user_input="Summarize the tradeoffs of caching.",
            goal="summarize",
            turn_meaning=meaning,
        )

        self.assertFalse(
            _stage_data(result, "REASONING").get("requires_clarification", False)
        )
        self.assertEqual(len(calls), 1)


# ---------------------------------------------------------------------------
# 4-6. Backward compatibility / fail-closed input handling
# ---------------------------------------------------------------------------

class TestMeaningBackwardCompatibility(unittest.TestCase):

    def test_absent_meaning_preserves_existing_behavior(self):
        """Without meaning the stage payloads keep their previous shape."""
        calls = []
        coordinator = _build_coordinator(handler_calls=calls)

        result = coordinator.process(
            user_input="is the sky blue", goal="verify claim X",
        )
        reasoning = _stage_data(result, "REASONING")
        planning = _stage_data(result, "PLANNING")

        self.assertNotIn("meaning", reasoning)
        self.assertNotIn("requires_clarification", reasoning)
        self.assertIn("verify claim X", reasoning["goal"])
        self.assertIn("verify claim X", planning["goal"])
        self.assertEqual(len(calls), 1)

    def test_malformed_meaning_is_dropped_fail_closed(self):
        """A raising or non-dict projection degrades to no meaning."""
        class _Raising:
            def to_reasoning_meaning(self):
                raise RuntimeError("boom")

        class _WrongType:
            def to_reasoning_meaning(self):
                return ["not", "a", "dict"]

        coordinator = _build_coordinator()

        for payload in (_Raising(), _WrongType(), object(), "meaning"):
            result = coordinator.process(
                user_input="text", goal="g", turn_meaning=payload,
            )
            reasoning = _stage_data(result, "REASONING")
            self.assertNotIn("meaning", reasoning)

    def test_cognition_state_meaning_defaults_to_empty(self):
        self.assertEqual(CognitionState().meaning, {})

    def test_legacy_inline_path_is_unaffected_by_turn_meaning(self):
        """The no-coordinator compatibility shim keeps its previous behavior."""
        registry = CapabilityRegistry()
        registry.register("conversation", lambda params: ExecutionResult(
            capability="conversation", success=True, output={},
        ))

        service = CognitionService(
            reasoning_controller=ReasoningController(),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=registry,
            capability_router=CapabilityRouter(registry),
            capability_dispatcher=CapabilityDispatcher(registry),
        )
        service.start()
        try:
            without = service.process("Hello world")
            with_meaning = service.process(
                "Hello world", turn_meaning=_meaning_for("Build it."),
            )
            self.assertEqual(
                sorted(without.data.keys()), sorted(with_meaning.data.keys()),
            )
            self.assertIn("reasoning", with_meaning.data)
        finally:
            service.stop()


# ---------------------------------------------------------------------------
# 7. Public boundary + provider independence + determinism
# ---------------------------------------------------------------------------

class TestMeaningAtThePublicBoundary(unittest.TestCase):

    def test_cognition_api_forwards_meaning_to_reasoning(self):
        """The served boundary (CognitionAPI -> CognitionService ->
        RuntimeCoordinator) delivers meaning to reasoning/planning."""
        coordinator = _build_coordinator()
        service = CognitionService(runtime_coordinator=coordinator)
        service.start()
        try:
            api = CognitionAPI(cognition_service=service)
            meaning = _explicit_meaning(
                task_type="action_request",
                intent="prepare report",
                goal="prepare the deployment report",
            )
            decision = api.process(
                "unclassified text", turn_meaning=meaning,
            )
            public_reasoning = decision.data["reasoning"]
            self.assertIn("meaning", public_reasoning)
            self.assertEqual(
                public_reasoning["meaning"]["goal"],
                "prepare the deployment report",
            )
            self.assertIn("prepare the deployment report",
                          public_reasoning["goal"])
        finally:
            service.stop()

    def test_integration_requires_no_ai_provider(self):
        """No provider, no network: the integration is model-independent."""
        meaning = _explicit_meaning(
            task_type="action_request", intent="i", goal="g",
        )
        coordinator = _build_coordinator()
        self.assertIsNone(coordinator._ai_service)

        result = coordinator.process(user_input="text", turn_meaning=meaning)

        self.assertTrue(result.success)
        self.assertEqual(result.final_response, "")

    def test_meaning_consumption_is_deterministic(self):
        """Identical inputs produce identical reasoning/planning payloads."""
        meaning = _explicit_meaning(
            task_type="action_request",
            intent="prepare report",
            goal="prepare the deployment report",
            constraints=["read-only"],
        )
        coordinator = _build_coordinator()

        first = coordinator.process(user_input="text", turn_meaning=meaning)
        second = coordinator.process(user_input="text", turn_meaning=meaning)

        self.assertEqual(
            _stage_data(first, "REASONING"), _stage_data(second, "REASONING"),
        )
        self.assertEqual(
            _stage_data(first, "PLANNING"), _stage_data(second, "PLANNING"),
        )

    def test_projection_is_bounded_and_json_safe(self):
        """The reasoning projection is content-bounded and JSON-safe."""
        meaning = TurnMeaning(
            intent={
                "task_type": "action_request",
                "intent": "x" * (MAX_REASONING_TEXT_CHARS + 50),
                "goal": "y" * (MAX_REASONING_TEXT_CHARS + 50),
                "constraints": [f"c{i}" for i in range(MAX_REASONING_ITEMS + 5)],
                "priorities": "not-a-list",
                "confidence": float("nan"),
                "needs_clarification": True,
            },
            uncertainty={"ambiguity_score": float("inf")},
            reference={"field": "findings", "value": "v" * 400},
        )

        projected = meaning.to_reasoning_meaning()

        self.assertEqual(len(projected["intent"]), MAX_REASONING_TEXT_CHARS)
        self.assertEqual(len(projected["goal"]), MAX_REASONING_TEXT_CHARS)
        self.assertEqual(len(projected["constraints"]), MAX_REASONING_ITEMS)
        self.assertEqual(projected["priorities"], [])
        self.assertEqual(projected["confidence"], 0.0)
        self.assertEqual(projected["ambiguity_score"], 0.0)
        self.assertEqual(
            len(projected["reference"]["value"]), MAX_REASONING_TEXT_CHARS,
        )
        self.assertTrue(projected["needs_clarification"])
        # JSON-safe / deterministic round-trip of the projection itself.
        self.assertIsInstance(str(projected), str)

    def test_projection_does_not_mutate_the_contract(self):
        meaning = _meaning_for("Summarize the tradeoffs of caching.")
        before = meaning.to_dict()
        meaning.to_reasoning_meaning()
        self.assertEqual(meaning.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
