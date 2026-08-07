"""Track D — evolution integration tests (Batch 3)."""

from atlas.advanced_reasoning.evolution_integration import (
    REASONING_DOMAIN,
    build_ingest_payload,
    register_gov_011,
    ReasoningEvolutionTracker,
    ReasoningIngestBridge,
    IngestHandoffResult,
)
from atlas.evolution.governance.constraint_registry import ConstraintRegistry
from atlas.evolution.governance.models import ScopeType


class _FakeSink:
    def __init__(self, accept: bool = True) -> None:
        self.accept = accept
        self.requests = []

    def enqueue_request(self, request) -> IngestHandoffResult:
        self.requests.append(request)
        if not self.accept:
            return IngestHandoffResult(False, error="refused")
        return IngestHandoffResult(True, request_id=request.request_id)


class TestBuildPayload:
    def test_deterministic_payload(self):
        p1 = build_ingest_payload("insight", source_trace_id="t1", strategy_name="D", confidence=0.7)
        p2 = build_ingest_payload("insight", source_trace_id="t1", strategy_name="D", confidence=0.7)
        assert p1 == p2
        assert p1["operation"] == "reasoning_ingest"
        assert p1["domain"] == REASONING_DOMAIN
        assert p1["source_trace_id"] == "t1"

    def test_unknown_trace_id(self):
        payload = build_ingest_payload("insight")
        assert payload["source_trace_id"] == ""


class TestTracker:
    def test_builds_artifacts(self):
        tracker = ReasoningEvolutionTracker()
        artifacts = tracker.build_artifacts(
            content="insight",
            source_trace_id="t1",
            strategy_name="D",
            confidence=0.7,
        )
        assert artifacts.request.target_scope == ScopeType.KNOWLEDGE
        assert artifacts.observation is not None
        assert artifacts.evidence.event_type == "reasoning.ingest"
        assert "t1" in artifacts.evidence.related_ids


class TestBridge:
    def test_fails_closed_without_sink(self):
        bridge = ReasoningIngestBridge(sink=None)
        result = bridge.ingest(content="insight")
        assert not result.accepted
        assert "sink" in result.error

    def test_accepting_sink_succeeds(self):
        sink = _FakeSink(accept=True)
        bridge = ReasoningIngestBridge(sink=sink)
        result = bridge.ingest(content="insight", source_trace_id="t1")
        assert result.accepted
        assert len(sink.requests) == 1
        assert sink.requests[0].target_scope == ScopeType.KNOWLEDGE

    def test_refusing_sink_fails(self):
        sink = _FakeSink(accept=False)
        bridge = ReasoningIngestBridge(sink=sink)
        result = bridge.ingest(content="insight")
        assert not result.accepted
        assert "refused" in result.error

    def test_has_sink_flag(self):
        assert ReasoningIngestBridge(sink=_FakeSink()).has_sink is True
        assert ReasoningIngestBridge(sink=None).has_sink is False


class TestGov011:
    def test_register_adds_rule(self):
        registry = ConstraintRegistry()
        rule = register_gov_011(registry)
        assert rule.rule_id == "GOV-011"
        assert rule.scope == ScopeType.KNOWLEDGE
        assert registry.get_rule("GOV-011") is rule

    def test_duplicate_register_raises(self):
        registry = ConstraintRegistry()
        register_gov_011(registry)
        try:
            register_gov_011(registry)
            assert False, "expected ValueError on duplicate"
        except ValueError:
            pass