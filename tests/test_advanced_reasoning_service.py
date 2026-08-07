"""Track D — AdvancedReasoningService tests (Batch 3)."""

from atlas.advanced_reasoning.evolution_integration import ReasoningIngestBridge
from atlas.advanced_reasoning.models import (
    ReasoningConfig,
    ReasoningStrategy,
    ReasoningTrace,
    TraceStatus,
)
from atlas.advanced_reasoning.service import AdvancedReasoningService
from atlas.advanced_reasoning.trace_repository import ReasoningTraceRepository


class TestComposition:
    def test_default_composition(self):
        service = AdvancedReasoningService()
        assert service.config is not None
        assert service.multi_step is not None
        assert service.causal is not None
        assert service.hypotheses is not None
        assert service.verifier is not None
        assert service.meta is not None
        assert service.repository is not None
        assert service.ingest_bridge is not None

    def test_injected_components_are_used(self):
        repo = object.__new__(ReasoningTraceRepository)
        service = AdvancedReasoningService(repository=repo)
        assert service.repository is repo

    def test_config_propagates_to_engines(self):
        config = ReasoningConfig(max_steps=3)
        service = AdvancedReasoningService(config=config)
        assert service.multi_step._config is config
        assert service.meta._config is config


class TestReason:
    def test_reason_stores_trace(self):
        service = AdvancedReasoningService()
        trace = service.reason("Is it true that water freezes at 0C?")
        assert isinstance(trace, ReasoningTrace)
        assert trace.trace_id
        assert service.repository.get_trace(trace.trace_id) is trace

    def test_reason_with_trace_id(self):
        service = AdvancedReasoningService()
        trace = service.reason("What causes rain?", trace_id="trace:fixed")
        assert trace.trace_id == "trace:fixed"

    def test_reason_empty_question_fails_closed(self):
        service = AdvancedReasoningService()
        trace = service.reason("   ")
        assert trace.status == TraceStatus.FAILED

    def test_reason_stores_every_trace(self):
        service = AdvancedReasoningService()
        service.reason("How does a turbine work?")
        service.reason("What is an array?")
        assert service.repository.trace_count == 2


class TestCausal:
    def test_causal_paths(self):
        service = AdvancedReasoningService()
        paths = service.causal_paths("ignition", "fire")
        assert isinstance(paths, tuple)
        # No provider injected -> empty, fail-soft.
        assert paths == ()

    def test_counterfactual(self):
        service = AdvancedReasoningService()
        result = service.counterfactual("ignition", "without oxygen")
        assert result.source_event == "ignition"
        assert not result.changed  # no provider -> no paths


class TestHypotheses:
    def test_generates_and_stores(self):
        service = AdvancedReasoningService()
        result = service.generate_hypotheses("The engine stopped running.")
        assert result.set_id
        assert result.count >= 1
        assert service.repository.get_hypothesis_set(result.set_id) is result


class TestVerify:
    def test_verifies_and_stores(self):
        service = AdvancedReasoningService()
        report = service.verify("Water always boils at 100C.")
        assert report.report_id
        assert service.repository.get_verification_report(report.report_id) is report

    def test_verify_trace(self):
        service = AdvancedReasoningService()
        trace = service.reason("Are transcripts beneficial for legal review?")
        report = service.verify(trace)
        assert report.target_id == trace.trace_id


class TestMeta:
    def test_assesses_and_stores(self):
        service = AdvancedReasoningService()
        assessment = service.meta_assess()
        assert assessment.assessment_id
        assert service.repository.get_meta_assessment(assessment.assessment_id) is assessment
        assert assessment.recommended_strategy == ReasoningStrategy.DECOMPOSE


class _FakeIngestSink:
    def __init__(self, accept: bool = True) -> None:
        self.accept = accept
        self.requests = []

    def enqueue_request(self, request):
        from atlas.advanced_reasoning.evolution_integration import IngestHandoffResult

        self.requests.append(request)
        if not self.accept:
            return IngestHandoffResult(False, error="refused")
        return IngestHandoffResult(True, request_id=request.request_id)


class TestIngestBridge:
    def test_service_builds_bridge_from_sink(self):
        sink = _FakeIngestSink()
        service = AdvancedReasoningService(ingest_sink=sink)
        assert isinstance(service.ingest_bridge, ReasoningIngestBridge)

    def test_fails_closed_without_sink(self):
        service = AdvancedReasoningService()
        result = service.ingest_bridge.ingest(content="insight")
        assert not result.accepted
        assert "sink" in result.error