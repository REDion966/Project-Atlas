"""Track D — MultiStepReasoner tests (Batch 2).

Covers deterministic decomposition, evidence binding, confidence
propagation, budget enforcement, cycle detection, model enhancement
(fail-soft), and edge cases.
"""

import pytest

from atlas.advanced_reasoning.models import (
    ReasoningTraceStep,
    TraceStatus,
)
from atlas.advanced_reasoning.multi_step import MultiStepReasoner
from tests._advanced_reasoning_fakes import (
    FakeEvidenceProvider,
    FakeReasoningModel,
    RaisingReasoningModel,
)


class TestBasicReasoning:
    def test_single_goal_completed(self):
        reasoner = MultiStepReasoner()
        trace = reasoner.reason("Is the sky blue?")
        assert trace.status == TraceStatus.COMPLETED
        assert trace.step_count == 1
        assert trace.conclusion == "the sky blue"
        assert trace.confidence == 0.4
        assert trace.evidence_refs == ()

    def test_multi_goal_chains_steps(self):
        reasoner = MultiStepReasoner()
        trace = reasoner.reason("Is the sky blue and is the sea green?")
        assert trace.status == TraceStatus.COMPLETED
        assert trace.step_count == 2
        assert trace.steps[0].premise_step_ids == ()
        assert trace.steps[1].premise_step_ids == (trace.steps[0].step_id,)
        assert trace.conclusion == "the sea green"
        assert trace.confidence == 0.152

    def test_evidence_binding_raises_step_confidence(self):
        provider = FakeEvidenceProvider(
            rows={"the sky blue": ("ev:sky", "ev:blue")}
        )
        reasoner = MultiStepReasoner(evidence_provider=provider)
        trace = reasoner.reason("Is the sky blue and is the sea green?")
        assert trace.steps[0].evidence_refs == ("ev:blue", "ev:sky")
        assert trace.steps[0].confidence == 0.8
        assert trace.steps[1].evidence_refs == ()
        assert trace.steps[1].confidence == 0.4
        assert trace.confidence == 0.304
        assert trace.evidence_refs == ("ev:blue", "ev:sky")

    def test_strategy_is_decompose(self):
        reasoner = MultiStepReasoner()
        trace = reasoner.reason("Is the sky blue?")
        assert trace.strategy.name == "DECOMPOSE"

    def test_metadata_records_sub_goals(self):
        reasoner = MultiStepReasoner()
        trace = reasoner.reason("Is the sky blue and is the sea green?")
        assert trace.metadata["sub_goals"] == [
            "Is the sky blue",
            "is the sea green?",
        ]


class TestEdgeCases:
    def test_empty_question_returns_failed_trace(self):
        reasoner = MultiStepReasoner()
        trace = reasoner.reason("   ")
        assert trace.status == TraceStatus.FAILED
        assert trace.steps == ()
        assert trace.confidence == 0.0
        assert "empty" in trace.metadata["error"]

    def test_budget_exceeded_marks_ran_out_of_budget(self):
        reasoner = MultiStepReasoner()
        trace = reasoner.reason(
            "alpha and beta and gamma and delta and epsilon",
            max_steps=2,
        )
        assert trace.status == TraceStatus.RAN_OUT_OF_BUDGET
        assert trace.step_count == 2

    def test_budget_one_with_multi_goal(self):
        reasoner = MultiStepReasoner()
        trace = reasoner.reason("alpha and beta", max_steps=1)
        assert trace.status == TraceStatus.RAN_OUT_OF_BUDGET
        assert trace.step_count == 1

    def test_sub_goals_dedupes_fragments(self):
        reasoner = MultiStepReasoner()
        assert reasoner.sub_goals("alpha and alpha") == ("alpha",)

    def test_sub_goals_empty_on_empty_input(self):
        reasoner = MultiStepReasoner()
        assert reasoner.sub_goals("   ") == ()

    def test_trace_id_override(self):
        reasoner = MultiStepReasoner()
        trace = reasoner.reason("Is the sky blue?", trace_id="custom-id")
        assert trace.trace_id == "custom-id"


class TestDeterminism:
    def test_same_input_same_steps(self):
        reasoner = MultiStepReasoner()
        first = reasoner.reason("Is the sky blue and is the sea green?")
        second = reasoner.reason("Is the sky blue and is the sea green?")
        assert first.steps == second.steps
        assert first.conclusion == second.conclusion
        assert first.confidence == second.confidence
        assert first.status == second.status


class TestAssertionForm:
    def test_strips_question_prefix(self):
        assert MultiStepReasoner.assertion_form("Is the sky blue?") == "the sky blue"

    def test_what_prefix(self):
        assert MultiStepReasoner.assertion_form("what is x?") == "x"

    def test_non_question_unchanged(self):
        assert MultiStepReasoner.assertion_form("the sky blue") == "the sky blue"


class TestDependencyGraphValidation:
    def test_sequential_chain_is_acyclic(self):
        steps = (
            ReasoningTraceStep(step_id="s1"),
            ReasoningTraceStep(step_id="s2", premise_step_ids=("s1",)),
            ReasoningTraceStep(step_id="s3", premise_step_ids=("s2",)),
        )
        assert MultiStepReasoner().validate_dependency_graph(steps) == ()

    def test_detects_two_node_cycle(self):
        steps = (
            ReasoningTraceStep(step_id="s1", premise_step_ids=("s2",)),
            ReasoningTraceStep(step_id="s2", premise_step_ids=("s1",)),
        )
        assert MultiStepReasoner().validate_dependency_graph(steps) != ()

    def test_detects_self_reference_cycle(self):
        steps = (
            ReasoningTraceStep(step_id="s1", premise_step_ids=("s1",)),
        )
        assert MultiStepReasoner().validate_dependency_graph(steps) != ()

    def test_ignores_missing_premise_refs(self):
        steps = (
            ReasoningTraceStep(step_id="s1", premise_step_ids=("ghost",)),
        )
        assert MultiStepReasoner().validate_dependency_graph(steps) == ()


class TestModelEnhancement:
    def test_model_steps_merged(self):
        model = FakeReasoningModel(
            steps=(
                ReasoningTraceStep(
                    step_id="m1",
                    description="model step",
                    conclusion="model conclusion",
                ),
            )
        )
        reasoner = MultiStepReasoner(reasoning_model=model)
        trace = reasoner.reason("Is the sky blue?")
        assert trace.step_count == 2
        assert trace.steps[0].step_id == "m1"
        assert trace.steps[1].premise_step_ids == ("m1",)

    def test_raising_model_falls_back(self):
        reasoner = MultiStepReasoner(reasoning_model=RaisingReasoningModel())
        trace = reasoner.reason("Is the sky blue?")
        assert trace.status == TraceStatus.COMPLETED
        assert trace.step_count == 1
        assert trace.steps[0].step_id == "step:0000"

    def test_self_referencing_model_step_dropped(self):
        model = FakeReasoningModel(
            steps=(
                ReasoningTraceStep(
                    step_id="m1",
                    premise_step_ids=("m1",),
                    conclusion="bad",
                ),
            )
        )
        reasoner = MultiStepReasoner(reasoning_model=model)
        trace = reasoner.reason("Is the sky blue?")
        assert trace.step_count == 1
        assert trace.steps[0].step_id == "step:0000"

    def test_forward_referencing_model_step_dropped(self):
        model = FakeReasoningModel(
            steps=(
                ReasoningTraceStep(
                    step_id="m1",
                    premise_step_ids=("m9",),
                    conclusion="bad",
                ),
            )
        )
        reasoner = MultiStepReasoner(reasoning_model=model)
        trace = reasoner.reason("Is the sky blue?")
        assert trace.step_count == 1
        assert trace.steps[0].step_id == "step:0000"


class TestEvidenceFailSoft:
    def test_raising_evidence_provider_is_ignored(self):
        class BoomProvider:
            def query(self, query_text, limit=10):
                raise RuntimeError("down")

        reasoner = MultiStepReasoner(evidence_provider=BoomProvider())
        trace = reasoner.reason("Is the sky blue?")
        assert trace.status == TraceStatus.COMPLETED
        assert trace.steps[0].evidence_refs == ()
