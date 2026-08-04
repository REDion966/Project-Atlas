"""Phase 17.8 — Research evolution integration tests."""

import pytest

from atlas.evolution.governance.constraint_registry import ConstraintRegistry
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ObservationCategory
from atlas.research.evolution_integration import (
    GOV_008_RULE_ID,
    IngestHandoffResult,
    ResearchEvolutionTracker,
    ResearchIngestBridge,
    build_ingest_payload,
    register_gov_008,
)
from atlas.research.models import (
    ClaimVerification,
    KnowledgeClaim,
    ResearchReport,
    VerificationStatus,
)


def make_report():
    claim = KnowledgeClaim(claim_id="claim:1", statement="Atlas uses SQLite.")
    verification = ClaimVerification(
        verification_id="verify:1",
        claim_id="claim:1",
        status=VerificationStatus.SUPPORTED,
        score=0.9,
    )
    return ResearchReport(
        report_id="report:1",
        plan_id="plan::1",
        query_id="q1",
        question="What storage?",
        findings="Atlas uses SQLite.",
        confidence=0.9,
        claims=(claim,),
        verifications=(verification,),
    )


class TestRequestCreation:
    def test_builds_information_scope_request(self):
        tracker = ResearchEvolutionTracker()
        artifacts = tracker.build_artifacts(make_report())
        request = artifacts.request
        assert request.target_scope == ScopeType.KNOWLEDGE
        assert request.intended_level.name == "INFORMATION"
        assert request.change_payload["operation"] == "add"
        assert request.change_payload["entry_id"] == "research:report:1"
        assert request.change_payload["domain"] == "research"

    def test_payload_is_phase16_schema_compliant(self):
        payload = build_ingest_payload(make_report())
        assert {"operation", "entry_id", "domain", "content", "confidence"}.issubset(
            payload.keys()
        )

    def test_artifacts_include_observation_and_evidence(self):
        artifacts = ResearchEvolutionTracker().build_artifacts(make_report())
        assert artifacts.observation.metric_name == "research:ingest"
        assert artifacts.observation.category == ObservationCategory.RUNTIME_METRICS
        assert artifacts.evidence.event_type == "research.ingest"

    def test_observation_references_request(self):
        artifacts = ResearchEvolutionTracker().build_artifacts(make_report())
        assert artifacts.observation.value["request_id"] == artifacts.request.request_id


class TestGatewayHandoff:
    class FakeSink:
        def __init__(self, accepted=True):
            self.accepted = accepted
            self.received = None

        def enqueue_request(self, request):
            self.received = request
            return IngestHandoffResult(
                accepted=self.accepted,
                request_id=request.request_id,
                error="" if self.accepted else "refused",
            )

    def test_handoff_through_injected_sink(self):
        sink = self.FakeSink()
        bridge = ResearchIngestBridge(sink=sink)
        result = bridge.ingest(make_report())
        assert result.accepted
        assert sink.received is not None
        assert sink.received.target_scope == ScopeType.KNOWLEDGE

    def test_bridge_never_bypasses_sink_to_gateway(self):
        sink = self.FakeSink()
        bridge = ResearchIngestBridge(sink=sink)
        bridge.ingest(make_report())
        # Track A never calls execute_request itself; the only hand-off is
        # through the injected sink (Phase 16 sole-dispatcher discipline).
        assert sink.received is not None
        assert not hasattr(bridge, "_gateway")

    def test_missing_sink_fails_closed(self):
        bridge = ResearchIngestBridge()  # no sink
        assert not bridge.has_sink
        result = bridge.ingest(make_report())
        assert not result.accepted
        assert "not wired" in result.error

    def test_refused_sink_fails_closed(self):
        bridge = ResearchIngestBridge(sink=self.FakeSink(accepted=False))
        result = bridge.ingest(make_report())
        assert not result.accepted
        assert result.error == "refused"


class TestGov008:
    def test_register_gov_008_additive(self):
        registry = ConstraintRegistry()
        rule = register_gov_008(registry)
        assert rule.rule_id == GOV_008_RULE_ID
        assert rule.scope == ScopeType.KNOWLEDGE
        assert rule.min_execution_level == 2  # INFORMATION
        assert registry.get_rule(GOV_008_RULE_ID) is rule

    def test_gov_008_duplicate_registration_raises(self):
        registry = ConstraintRegistry()
        register_gov_008(registry)
        with pytest.raises(ValueError):
            register_gov_008(registry)

    def test_gov_008_preserves_existing_rules(self):
        registry = ConstraintRegistry()
        register_gov_008(registry)
        assert registry.get_rule("GOV-001") is not None
        assert registry.get_rule("GOV-004") is not None


class TestDeterminism:
    def test_build_artifacts_is_stable_fields(self):
        first = ResearchEvolutionTracker().build_artifacts(make_report())
        second = ResearchEvolutionTracker().build_artifacts(make_report())
        assert (
            first.request.change_payload,
            first.observation.metric_name,
            first.evidence.event_type,
        ) == (
            second.request.change_payload,
            second.observation.metric_name,
            second.evidence.event_type,
        )


class TestObservationAndEvidence:
    def test_evidence_related_ids(self):
        artifacts = ResearchEvolutionTracker().build_artifacts(make_report())
        assert artifacts.evidence.related_ids == [
            "report:1",
            artifacts.request.request_id,
        ]
