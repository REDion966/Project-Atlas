"""Phase 18.9 — Toolchain evolution integration tests."""

import pytest

from atlas.evolution.governance.constraint_registry import ConstraintRegistry
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ObservationCategory
from atlas.toolchain.evolution_integration import (
    GOV_009_RULE_ID,
    IngestHandoffResult,
    ToolchainEvolutionTracker,
    ToolchainIngestBridge,
    build_ingest_payload,
    register_gov_009,
)
from atlas.toolchain.models import (
    Skill,
    SkillKind,
    SkillStatus,
    ToolChain,
    ToolStep,
)


def make_skill(
    skill_id: str = "skill:test:1",
    name: str = "Read File",
    status: SkillStatus = SkillStatus.DRAFT,
) -> Skill:
    chain = ToolChain(
        chain_id="chain::skill:test:1",
        goal="Read a file.",
        steps=(
            ToolStep(step_id="step:0000", tool_name="read_file"),
        ),
        strategy="sequential",
    )
    return Skill(
        skill_id=skill_id,
        name=name,
        description="Reads a file from disk.",
        kind=SkillKind.COMPOSED,
        category="file",
        chain=chain,
        status=status,
    )


class TestRequestCreation:
    def test_builds_information_scope_request(self):
        tracker = ToolchainEvolutionTracker()
        artifacts = tracker.build_artifacts(make_skill())
        request = artifacts.request
        assert request.target_scope == ScopeType.KNOWLEDGE
        assert request.intended_level.name == "INFORMATION"
        assert request.change_payload["operation"] == "activate"
        assert request.change_payload["entry_id"] == "skill:skill:test:1"
        assert request.change_payload["domain"] == "toolchain"

    def test_payload_is_phase16_schema_compliant(self):
        payload = build_ingest_payload(make_skill())
        assert {
            "operation",
            "entry_id",
            "domain",
            "content",
            "confidence",
            "skill_id",
            "skill_name",
            "kind",
            "category",
        }.issubset(payload.keys())

    def test_artifacts_include_observation_and_evidence(self):
        artifacts = ToolchainEvolutionTracker().build_artifacts(make_skill())
        assert artifacts.observation.metric_name == "toolchain:ingest"
        assert artifacts.observation.category == ObservationCategory.RUNTIME_METRICS
        assert artifacts.evidence.event_type == "toolchain.ingest"

    def test_observation_references_request(self):
        artifacts = ToolchainEvolutionTracker().build_artifacts(make_skill())
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
        bridge = ToolchainIngestBridge(sink=sink)
        result = bridge.ingest(make_skill())
        assert result.accepted
        assert sink.received is not None
        assert sink.received.target_scope == ScopeType.KNOWLEDGE

    def test_bridge_never_bypasses_sink_to_gateway(self):
        sink = self.FakeSink()
        bridge = ToolchainIngestBridge(sink=sink)
        bridge.ingest(make_skill())
        # Track B never calls execute_request itself; the only hand-off is
        # through the injected sink (Phase 16 sole-dispatcher discipline).
        assert sink.received is not None
        assert not hasattr(bridge, "_gateway")

    def test_missing_sink_fails_closed(self):
        bridge = ToolchainIngestBridge()  # no sink
        assert not bridge.has_sink
        result = bridge.ingest(make_skill())
        assert not result.accepted
        assert "not wired" in result.error

    def test_refused_sink_fails_closed(self):
        bridge = ToolchainIngestBridge(sink=self.FakeSink(accepted=False))
        result = bridge.ingest(make_skill())
        assert not result.accepted
        assert result.error == "refused"


class TestGov009:
    def test_register_gov_009_additive(self):
        registry = ConstraintRegistry()
        rule = register_gov_009(registry)
        assert rule.rule_id == GOV_009_RULE_ID
        assert rule.scope == ScopeType.KNOWLEDGE
        assert rule.min_execution_level == 2  # INFORMATION
        assert registry.get_rule(GOV_009_RULE_ID) is rule

    def test_gov_009_duplicate_registration_raises(self):
        registry = ConstraintRegistry()
        register_gov_009(registry)
        with pytest.raises(ValueError):
            register_gov_009(registry)

    def test_gov_009_preserves_existing_rules(self):
        registry = ConstraintRegistry()
        register_gov_009(registry)
        assert registry.get_rule("GOV-001") is not None
        assert registry.get_rule("GOV-004") is not None
        assert registry.get_rule("GOV-008") is None  # Track A rule not auto-loaded


class TestDeterminism:
    def test_build_artifacts_is_stable_fields(self):
        first = ToolchainEvolutionTracker().build_artifacts(make_skill())
        second = ToolchainEvolutionTracker().build_artifacts(make_skill())
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
        artifacts = ToolchainEvolutionTracker().build_artifacts(make_skill())
        assert artifacts.evidence.related_ids == [
            "skill:test:1",
            artifacts.request.request_id,
        ]
