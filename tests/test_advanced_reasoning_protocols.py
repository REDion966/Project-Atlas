"""Track D — Advanced Reasoning provider protocol tests (Batch 1).

Verifies the :class:`EvidenceProvider`, :class:`CausalGraphProvider`,
:class:`ReasoningModel`, :class:`VerificationModel`, and
:class:`HypothesisModel` protocols are importable, runtime checkable, and
structurally compatible with the model types they reference.
"""

from typing import Protocol

from atlas.advanced_reasoning.models import (
    CausalPath,
    Hypothesis,
    ReasoningTraceStep,
    VerificationFinding,
)
from atlas.advanced_reasoning.protocols import (
    CausalGraphProvider,
    EvidenceProvider,
    HypothesisModel,
    ReasoningModel,
    VerificationModel,
)


class _FakeEvidenceProvider:
    """Structural stand-in for the EvidenceProvider protocol."""

    def query(self, query_text: str, limit: int = 10) -> list[str]:
        return [f"ev:{query_text}"][:limit]


class _FakeCausalGraphProvider:
    """Structural stand-in for the CausalGraphProvider protocol."""

    def causal_paths(
        self,
        source: str,
        target: str,
        max_depth: int = 5,
    ) -> tuple[CausalPath, ...]:
        return ()

    def related_entities(
        self,
        entity_id: str,
        max_depth: int = 5,
    ) -> tuple[str, ...]:
        return ()


class _FakeReasoningModel:
    """Structural stand-in for the ReasoningModel protocol."""

    def propose_steps(
        self,
        question: str,
        max_steps: int = 20,
    ) -> tuple[ReasoningTraceStep, ...]:
        return ()


class _FakeVerificationModel:
    """Structural stand-in for the VerificationModel protocol."""

    def assess(
        self,
        claim: str,
        context: dict,
    ) -> VerificationFinding | None:
        return None


class _FakeHypothesisModel:
    """Structural stand-in for the HypothesisModel protocol."""

    def generate(
        self,
        claim: str,
        limit: int = 5,
    ) -> tuple[Hypothesis, ...]:
        return ()


class TestProtocolShape:
    def test_evidence_provider_is_protocol(self):
        assert issubclass(EvidenceProvider, Protocol)

    def test_causal_graph_provider_is_protocol(self):
        assert issubclass(CausalGraphProvider, Protocol)

    def test_reasoning_model_is_protocol(self):
        assert issubclass(ReasoningModel, Protocol)

    def test_verification_model_is_protocol(self):
        assert issubclass(VerificationModel, Protocol)

    def test_hypothesis_model_is_protocol(self):
        assert issubclass(HypothesisModel, Protocol)

    def test_all_protocols_are_runtime_checkable(self):
        for protocol in (
            EvidenceProvider,
            CausalGraphProvider,
            ReasoningModel,
            VerificationModel,
            HypothesisModel,
        ):
            assert hasattr(protocol, "__instancecheck__"), f"{protocol.__name__}"

    def test_evidence_provider_method(self):
        assert hasattr(EvidenceProvider, "query")

    def test_causal_graph_provider_methods(self):
        for method in ("causal_paths", "related_entities"):
            assert hasattr(CausalGraphProvider, method)

    def test_reasoning_model_method(self):
        assert hasattr(ReasoningModel, "propose_steps")

    def test_verification_model_method(self):
        assert hasattr(VerificationModel, "assess")

    def test_hypothesis_model_method(self):
        assert hasattr(HypothesisModel, "generate")


class TestRuntimeCompatibility:
    def test_evidence_provider_structural_match(self):
        assert isinstance(_FakeEvidenceProvider(), EvidenceProvider)

    def test_causal_graph_provider_structural_match(self):
        assert isinstance(_FakeCausalGraphProvider(), CausalGraphProvider)

    def test_reasoning_model_structural_match(self):
        assert isinstance(_FakeReasoningModel(), ReasoningModel)

    def test_verification_model_structural_match(self):
        assert isinstance(_FakeVerificationModel(), VerificationModel)

    def test_hypothesis_model_structural_match(self):
        assert isinstance(_FakeHypothesisModel(), HypothesisModel)

    def test_model_types_are_importable(self):
        assert CausalPath is not None
        assert Hypothesis is not None
        assert ReasoningTraceStep is not None
        assert VerificationFinding is not None
