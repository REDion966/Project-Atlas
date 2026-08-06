"""Track C — LongTermEvolutionTracker / IngestBridge tests (Batch 4)."""

from atlas.evolution.governance.constraint_registry import ConstraintRegistry
from atlas.evolution.governance.models import ScopeType
from atlas.longterm.evolution_integration import (
    IngestHandoffResult,
    LongTermEvolutionTracker,
    LongTermIngestBridge,
    build_ingest_payload,
    register_gov_010,
)
from atlas.longterm.models import ConsolidationRecord, ConsolidationStatus


def _make_record(record_id: str = "consol:1") -> ConsolidationRecord:
    return ConsolidationRecord(
        record_id=record_id,
        status=ConsolidationStatus.PENDING,
        operation="forget",
        target_type="episode",
        target_ids=("e1", "e2"),
        reason="low importance",
    )


class _FakeSink:
    def __init__(self, accept: bool = True):
        self.accept = accept
        self.requests = []

    def enqueue_request(self, request) -> IngestHandoffResult:
        self.requests.append(request)
        if not self.accept:
            return IngestHandoffResult(False, error="refused")
        return IngestHandoffResult(True, request_id=request.request_id)


class TestBuildPayload:
    def test_structural_fields(self):
        payload = build_ingest_payload(_make_record())
        assert payload["operation"] == "forget"
        assert payload["domain"] == "longterm"
        assert payload["target_type"] == "episode"
        assert payload["target_ids"] == ["e1", "e2"]
        assert payload["confidence"] == 1.0

    def test_deterministic(self):
        first = build_ingest_payload(_make_record("consol:1"))
        second = build_ingest_payload(_make_record("consol:1"))
        assert first == second


class TestTracker:
    def test_build_artifacts(self):
        tracker = LongTermEvolutionTracker()
        artifacts = tracker.build_artifacts(_make_record())
        assert artifacts.request.target_scope == ScopeType.MEMORY
        assert artifacts.observation.metric_name == "memory:consolidate"
        assert artifacts.evidence.event_type == "memory.consolidate"

    def test_observation_value_shape(self):
        tracker = LongTermEvolutionTracker()
        artifacts = tracker.build_artifacts(_make_record("consol:7"))
        value = artifacts.observation.value
        assert value["record_id"] == "consol:7"
        assert value["target_count"] == 2


class TestBridge:
    def test_fails_closed_without_sink(self):
        bridge = LongTermIngestBridge()
        result = bridge.ingest(_make_record())
        assert not result.accepted
        assert "sink" in result.error
        assert result.request_id

    def test_accepts_via_sink(self):
        sink = _FakeSink(accept=True)
        bridge = LongTermIngestBridge(sink=sink)
        result = bridge.ingest(_make_record())
        assert result.accepted
        assert len(sink.requests) == 1

    def test_refused_by_sink(self):
        sink = _FakeSink(accept=False)
        bridge = LongTermIngestBridge(sink=sink)
        result = bridge.ingest(_make_record())
        assert not result.accepted
        assert "refused" in result.error


class TestGOV010:
    def test_registers(self):
        registry = ConstraintRegistry()
        rule = register_gov_010(registry)
        assert rule.rule_id == "GOV-010"
        assert rule.scope == ScopeType.MEMORY
