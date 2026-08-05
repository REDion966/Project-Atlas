"""Atlas Toolchain — Evolution Integration (Phase 18.9).

Integrates Track B toolchain skill activations with the Phase 16 Evolution
Framework following the governed mutation discipline EXACTLY — mirroring
the Track A :mod:`atlas.research.evolution_integration` architecture:

    Skill (activation intent)
        → EvolutionRequestFactory (request_factory)
        → EvolutionRequest (target_scope=KNOWLEDGE, intended_level=INFORMATION)
        → injected ToolchainIngestSink  (Phase 16 governed pipeline hand-off)
        → gateway → application         (owned by the Phase 16 stack)

Track B never calls ``EvolutionExecutionGateway.execute_request()`` directly
(Phase 16 binding constraint: ``EvolutionAutonomyDispatcher`` is the sole
caller). The kernel wires the sink to the Phase 16 schedule-store/dispatcher
queue; in tests the sink is injected as a fake. If ingestion is refused or
the sink is missing, the bridge fails closed: no silent success, an
``IngestHandoffResult`` with ``accepted=False`` and a meaningful error.

Skill activation therefore NEVER mutates the :class:`SkillRegistry` directly
from Track B code — the registry transition is a governed mutation owned by
the Phase 16 pipeline (GOV-009 documents the path).

Toolchain executions also emit Evolution-compatible evidence:

  * ``Observation`` (RUNTIME_METRICS, metric ``toolchain:ingest``) — consumed
    by the existing SelfObservation / EvolutionKnowledgePipeline surface.
  * ``EvolutionRecord`` (event_type ``toolchain.ingest``) — audit evidence
    compatible with ``EvolutionMemory`` history.

GOV-009 (SKILL_ACTIVATE / TOOLCHAIN_INGEST) is registered as an additive
governance rule (scope KNOWLEDGE, min level INFORMATION). No constitutional
change, no gateway redesign — only additive rule registration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from atlas.evolution.autonomy.models import EvolutionRequest
from atlas.evolution.autonomy.request_factory import EvolutionRequestFactory
from atlas.evolution.governance.constraint_registry import ConstraintRegistry
from atlas.evolution.governance.models import GovernanceRule, ScopeType
from atlas.evolution.models import (
    EvolutionRecord,
    ExecutionLevel,
    Observation,
    ObservationCategory,
)
from atlas.toolchain.models import Skill

TOOLCHAIN_DOMAIN: str = "toolchain"

# GOV-009 — SKILL_ACTIVATE / TOOLCHAIN_INGEST (additive governance support
# for Track B). Mirrors GOV-008: INFORMATION-scope KNOWLEDGE request only.
GOV_009_RULE_ID: str = "GOV-009"
GOV_009_DESCRIPTION: str = (
    "Skill activation / toolchain ingest (TOOLCHAIN_INGEST) writes into "
    "Atlas state only through the governed INFORMATION-scope evolution path."
)


@runtime_checkable
class ToolchainIngestSink(Protocol):
    """The Phase 16 governed hand-off point for a toolchain EvolutionRequest.

    The real implementation (wired by the kernel) forwards the request to
    the Phase 16 schedule store / dispatcher queue so it is validated,
    risk-assessed, authorized, and applied by the evolution stack — never
    by Track B directly.
    """

    def enqueue_request(self, request: EvolutionRequest) -> "IngestHandoffResult": ...


class IngestHandoffResult:
    """Outcome of handing a toolchain evolution request to the sink."""

    __slots__ = ("accepted", "request_id", "error")

    def __init__(self, accepted: bool, request_id: str = "", error: str = "") -> None:
        self.accepted = accepted
        self.request_id = request_id
        self.error = error


@dataclass(frozen=True, slots=True)
class ToolchainIngestArtifacts:
    """Deterministic artifacts produced by a toolchain ingest (pure)."""

    request: EvolutionRequest
    observation: Observation
    evidence: EvolutionRecord


def build_ingest_payload(skill: Skill) -> dict[str, object]:
    """Build the INFORMATION-scope KNOWLEDGE payload (Phase 16 schema).

    Deterministic: identical skills always produce identical payloads.
    The Phase 16 validator owns schema decisions; Track B only builds the
    structurally valid request.
    """
    return {
        "operation": "activate",
        "entry_id": f"skill:{skill.skill_id}",
        "domain": TOOLCHAIN_DOMAIN,
        "content": skill.description or skill.name,
        "confidence": 1.0,
        "skill_id": skill.skill_id,
        "skill_name": skill.name,
        "kind": skill.kind.name,
        "category": skill.category,
    }


class ToolchainEvolutionTracker:
    """Pure builder of governed evolution artifacts for a skill activation."""

    def __init__(self, factory: EvolutionRequestFactory | None = None) -> None:
        self._factory = factory or EvolutionRequestFactory()

    # ------------------------------------------------------------------
    # Artifact construction (no I/O — fully deterministic on inputs)
    # ------------------------------------------------------------------

    def build_artifacts(self, skill: Skill) -> ToolchainIngestArtifacts:
        """Build request + observation + evidence for one skill activation.

        Never raises for malformed skills; a skill lacking a description
        still produces a structurally valid request that the Phase 16
        validator may reject — which is the governed pipeline's decision.
        """
        payload: dict[str, object] = build_ingest_payload(skill)
        request: EvolutionRequest = self._factory.from_cli(
            target_scope=ScopeType.KNOWLEDGE,
            change_payload=payload,
            source=f"toolchain:{skill.skill_id}",
        )
        observation = self._build_observation(skill, request)
        evidence = self._build_evidence(skill, request)
        return ToolchainIngestArtifacts(
            request=request,
            observation=observation,
            evidence=evidence,
        )

    @staticmethod
    def _build_observation(
        skill: Skill, request: EvolutionRequest
    ) -> Observation:
        """Evolution-compatible observation for the skill activation."""
        return Observation(
            category=ObservationCategory.RUNTIME_METRICS,
            metric_name="toolchain:ingest",
            value={
                "request_id": request.request_id,
                "skill_id": skill.skill_id,
                "scope": request.target_scope.name,
                "kind": skill.kind.name,
                "category": skill.category,
            },
            unit="toolchain",
            description=(
                f"Skill activation request {request.request_id} created for "
                f"skill {skill.skill_id} ({skill.kind.name})."
            ),
            source="toolchain",
        )

    @staticmethod
    def _build_evidence(
        skill: Skill, request: EvolutionRequest
    ) -> EvolutionRecord:
        """Audit evidence record compatible with EvolutionMemory history."""
        return EvolutionRecord(
            record_id=f"evidence:{request.request_id}",
            event_type="toolchain.ingest",
            description=(
                f"Skill {skill.skill_id} activation ingested as governed "
                f"evolution request {request.request_id} (KNOWLEDGE scope)."
            ),
            related_ids=[skill.skill_id, request.request_id],
            metadata={
                "scope": request.target_scope.name,
                "intended_level": request.intended_level.name,
                "kind": skill.kind.name,
            },
        )


class ToolchainIngestBridge:
    """Hands a skill activation's governed request to the evolution pipeline.

    Fail-closed: without a sink, or when the sink refuses the request, the
    bridge returns ``accepted=False`` with a meaningful error — it never
    swallows the refusal, never mutates the skill registry itself, and never
    calls the gateway or dispatcher directly.
    """

    def __init__(
        self,
        tracker: ToolchainEvolutionTracker | None = None,
        sink: ToolchainIngestSink | None = None,
    ) -> None:
        self._tracker = tracker or ToolchainEvolutionTracker()
        self._sink = sink

    @property
    def has_sink(self) -> bool:
        """True when a governed ingest sink is wired."""
        return self._sink is not None

    def ingest(self, skill: Skill) -> IngestHandoffResult:
        """Submit a skill activation through the governed evolution path."""
        artifacts: ToolchainIngestArtifacts = self._tracker.build_artifacts(skill)
        sink: ToolchainIngestSink | None = self._sink
        if sink is None:
            return IngestHandoffResult(
                accepted=False,
                request_id=artifacts.request.request_id,
                error="toolchain ingest sink is not wired (fail closed)",
            )
        handoff: IngestHandoffResult = sink.enqueue_request(artifacts.request)
        if not handoff.accepted:
            return IngestHandoffResult(
                accepted=False,
                request_id=artifacts.request.request_id,
                error=handoff.error or "toolchain ingest refused by evolution pipeline",
            )
        return handoff


def register_gov_009(registry: ConstraintRegistry) -> GovernanceRule:
    """Additively register GOV-009 (TOOLCHAIN_INGEST).

    Scope KNOWLEDGE, minimum level INFORMATION — mirrors GOV-008 and
    documents the skill-activation ingest path. Registration is additive;
    a registry already holding GOV-009 raises ``ValueError`` (id conflicts).
    """
    rule = GovernanceRule(
        rule_id=GOV_009_RULE_ID,
        description=GOV_009_DESCRIPTION,
        scope=ScopeType.KNOWLEDGE,
        min_execution_level=ExecutionLevel.INFORMATION.value,
    )
    registry.register(rule)
    return rule
