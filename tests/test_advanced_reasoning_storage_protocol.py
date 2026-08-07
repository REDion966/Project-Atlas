"""Track D — Advanced Reasoning storage protocol tests (Batch 1).

Verifies the :class:`AdvancedReasoningStorage` protocol is importable,
runtime checkable, and structurally compatible with the model types it
references.
"""

from typing import Protocol

from atlas.advanced_reasoning.models import (
    CausalPath,
    CounterfactualResult,
    Hypothesis,
    HypothesisSet,
    MetaAssessment,
    ReasoningTrace,
    ReasoningTraceStep,
    StrategyScore,
    VerificationFinding,
    VerificationReport,
)
from atlas.advanced_reasoning.storage_protocol import AdvancedReasoningStorage


class TestAdvancedReasoningStorageProtocol:
    def test_is_protocol(self):
        assert issubclass(AdvancedReasoningStorage, Protocol)

    def test_is_runtime_checkable(self):
        # @runtime_checkable decorator adds __instancecheck__ to the protocol class.
        assert hasattr(AdvancedReasoningStorage, "__instancecheck__")

    def test_has_lifecycle_methods(self):
        for method in ("initialize", "close", "is_available"):
            assert hasattr(AdvancedReasoningStorage, method)

    def test_has_trace_methods(self):
        for method in ("store_trace", "load_traces", "load_trace"):
            assert hasattr(AdvancedReasoningStorage, method)

    def test_has_trace_step_methods(self):
        for method in ("store_trace_step", "load_trace_steps"):
            assert hasattr(AdvancedReasoningStorage, method)

    def test_has_causal_methods(self):
        for method in (
            "store_causal_path",
            "load_causal_paths",
            "store_counterfactual_result",
            "load_counterfactual_results",
        ):
            assert hasattr(AdvancedReasoningStorage, method)

    def test_has_hypothesis_methods(self):
        for method in (
            "store_hypothesis",
            "store_hypothesis_set",
            "load_hypothesis_sets",
            "load_hypothesis_set",
            "load_hypotheses",
        ):
            assert hasattr(AdvancedReasoningStorage, method)

    def test_has_verification_methods(self):
        for method in (
            "store_verification_report",
            "load_verification_reports",
            "load_verification_report",
            "load_verification_findings",
        ):
            assert hasattr(AdvancedReasoningStorage, method)

    def test_has_meta_assessment_methods(self):
        for method in (
            "store_meta_assessment",
            "load_meta_assessments",
            "load_strategy_scores",
        ):
            assert hasattr(AdvancedReasoningStorage, method)

    def test_model_types_are_importable(self):
        assert ReasoningTrace is not None
        assert ReasoningTraceStep is not None
        assert CausalPath is not None
        assert CounterfactualResult is not None
        assert Hypothesis is not None
        assert HypothesisSet is not None
        assert VerificationReport is not None
        assert VerificationFinding is not None
        assert MetaAssessment is not None
        assert StrategyScore is not None
