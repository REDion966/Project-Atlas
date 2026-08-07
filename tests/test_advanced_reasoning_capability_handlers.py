"""Track D — AdvancedReasoningCapabilityFactory tests (Batch 3)."""

from atlas.advanced_reasoning.capability_handlers import (
    AdvancedReasoningCapabilityFactory,
)
from atlas.advanced_reasoning.evolution_integration import IngestHandoffResult
from atlas.advanced_reasoning.models import ReasoningStrategy, ReasoningTrace, TraceStatus
from atlas.advanced_reasoning.service import AdvancedReasoningService
from atlas.advanced_reasoning.trace_repository import ReasoningTraceRepository
from atlas.reasoning.execution.registry import CapabilityRegistry


def _make_trace(trace_id: str = "trace-1") -> ReasoningTrace:
    return ReasoningTrace(
        trace_id=trace_id,
        question="Is X supported?",
        strategy=ReasoningStrategy.DECOMPOSE,
        status=TraceStatus.COMPLETED,
        conclusion="inclined yes",
        confidence=0.8,
    )


class _FakeSink:
    """Accepting/refusing governed-ingest sink fake."""

    def __init__(self, accept: bool = True) -> None:
        self.accept = accept
        self.requests = []

    def enqueue_request(self, request) -> IngestHandoffResult:
        self.requests.append(request)
        if not self.accept:
            return IngestHandoffResult(False, error="refused by policy")
        return IngestHandoffResult(True, request_id=request.request_id)


class TestRegistration:
    def test_all_seven_registered(self):
        registry = CapabilityRegistry()
        AdvancedReasoningCapabilityFactory().register(registry)
        for name in (
            "reasoning.trace",
            "reasoning.causal",
            "reasoning.counterfactual",
            "reasoning.hypotheses",
            "reasoning.verify",
            "reasoning.meta",
            "reasoning.ingest",
        ):
            assert registry.has(name)
        assert registry.count == 7


class TestTrace:
    def test_empty_question_fails_closed(self):
        result = AdvancedReasoningCapabilityFactory().handlers()["reasoning.trace"]({})
        assert not result.success
        assert "question" in result.error

    def test_produces_trace(self):
        factory = AdvancedReasoningCapabilityFactory()
        result = factory.handlers()["reasoning.trace"](
            {"question": "How does a generator produce electricity?"}
        )
        assert result.success
        assert result.output["trace"]["status"] == "COMPLETED"

    def test_trace_stored_in_repository(self):
        factory = AdvancedReasoningCapabilityFactory()
        result = factory.handlers()["reasoning.trace"]({"question": "What is torque?"})
        assert factory.service.repository.get_trace(result.output["trace_id"]) is not None


class TestCausal:
    def test_requires_source_and_target(self):
        handler = AdvancedReasoningCapabilityFactory().handlers()["reasoning.causal"]
        assert not handler({"source": "a"}).success
        assert not handler({"target": "b"}).success

    def test_fail_soft_empty_provider(self):
        result = AdvancedReasoningCapabilityFactory().handlers()["reasoning.causal"](
            {"source": "ignition", "target": "fire"}
        )
        assert result.success
        assert result.output["count"] == 0


class TestCounterfactual:
    def test_requires_event_and_assumption(self):
        handler = AdvancedReasoningCapabilityFactory().handlers()["reasoning.counterfactual"]
        assert not handler({"event": "x"}).success
        assert not handler({"assumption": "y"}).success

    def test_runs(self):
        result = AdvancedReasoningCapabilityFactory().handlers()["reasoning.counterfactual"](
            {"event": "ignition", "assumption": "without oxygen"}
        )
        assert result.success
        assert result.output["changed"] is False


class TestHypotheses:
    def test_requires_claim(self):
        result = AdvancedReasoningCapabilityFactory().handlers()["reasoning.hypotheses"]({})
        assert not result.success

    def test_generates(self):
        result = AdvancedReasoningCapabilityFactory().handlers()["reasoning.hypotheses"](
            {"claim": "The production yield dropped sharply."}
        )
        assert result.success
        assert result.output["count"] >= 1


class TestVerify:
    def test_requires_trace_id_or_claim(self):
        result = AdvancedReasoningCapabilityFactory().handlers()["reasoning.verify"]({})
        assert not result.success

    def test_verify_claim(self):
        result = AdvancedReasoningCapabilityFactory().handlers()["reasoning.verify"](
            {"claim": "The sky is blue on a clear day."}
        )
        assert result.success
        assert "verdict" in result.output

    def test_verify_by_trace_id(self):
        repository = ReasoningTraceRepository()
        repository.store_trace(_make_trace("trace:known"))
        factory = AdvancedReasoningCapabilityFactory(
            service=AdvancedReasoningService(repository=repository)
        )
        result = factory.handlers()["reasoning.verify"]({"trace_id": "trace:known"})
        assert result.success
        assert result.output["target_id"] == "trace:known"

    def test_verify_missing_trace_fails_closed(self):
        result = AdvancedReasoningCapabilityFactory().handlers()["reasoning.verify"](
            {"trace_id": "trace:does-not-exist"}
        )
        assert not result.success
        assert "no trace" in result.error


class TestMeta:
    def test_produces_assessment(self):
        result = AdvancedReasoningCapabilityFactory().handlers()["reasoning.meta"]({})
        assert result.success
        assert "recommended_strategy" in result.output


class TestIngest:
    def test_requires_trace_id_or_content(self):
        result = AdvancedReasoningCapabilityFactory().handlers()["reasoning.ingest"]({})
        assert not result.success

    def test_fails_closed_without_sink(self):
        repository = ReasoningTraceRepository()
        repository.store_trace(_make_trace("trace:known"))
        factory = AdvancedReasoningCapabilityFactory(
            service=AdvancedReasoningService(repository=repository, ingest_sink=None)
        )
        result = factory.handlers()["reasoning.ingest"]({"trace_id": "trace:known"})
        assert not result.success
        assert "sink" in result.error

    def test_accepting_sink_succeeds(self):
        repository = ReasoningTraceRepository()
        repository.store_trace(_make_trace("trace:known"))
        sink = _FakeSink(accept=True)
        factory = AdvancedReasoningCapabilityFactory(
            service=AdvancedReasoningService(repository=repository, ingest_sink=sink)
        )
        result = factory.handlers()["reasoning.ingest"]({"trace_id": "trace:known"})
        assert result.success
        assert result.output["accepted"] is True
        assert result.metadata["governed"] is True
        assert len(sink.requests) == 1

    def test_refusing_sink_fails(self):
        repository = ReasoningTraceRepository()
        repository.store_trace(_make_trace("trace:known"))
        sink = _FakeSink(accept=False)
        factory = AdvancedReasoningCapabilityFactory(
            service=AdvancedReasoningService(repository=repository, ingest_sink=sink)
        )
        result = factory.handlers()["reasoning.ingest"]({"trace_id": "trace:known"})
        assert not result.success
        assert "refused" in result.error

    def test_ingest_by_content(self):
        sink = _FakeSink(accept=True)
        factory = AdvancedReasoningCapabilityFactory(
            service=AdvancedReasoningService(ingest_sink=sink)
        )
        result = factory.handlers()["reasoning.ingest"](
            {"content": "use decomposition for multi-fact queries"}
        )
        assert result.success

    def test_ingest_missing_trace_fails_closed(self):
        result = AdvancedReasoningCapabilityFactory().handlers()["reasoning.ingest"](
            {"trace_id": "trace:missing"}
        )
        assert not result.success

    def test_ingest_does_not_mutate_repository(self):
        repository = ReasoningTraceRepository()
        repository.store_trace(_make_trace("trace:known"))
        before = repository.trace_count
        factory = AdvancedReasoningCapabilityFactory(
            service=AdvancedReasoningService(
                repository=repository, ingest_sink=_FakeSink()
            )
        )
        factory.handlers()["reasoning.ingest"]({"trace_id": "trace:known"})
        assert repository.trace_count == before
        assert repository.get_trace("trace:known") is not None