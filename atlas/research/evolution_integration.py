"""Atlas Research — Evolution Integration (Phase 17.8).

Integrates Track A research results with the Phase 16 Evolution Framework
following the governed mutation discipline EXACTLY:

    ResearchReport
        → EvolutionRequestFactory (request_factory)
        → EvolutionRequest (target_scope=KNOWLEDGE, intended_level=INFORMATION)
        → injected ResearchIngestSink  (Phase 16 governed pipeline hand-off)
        → gateway → application → knowledge   (owned by the Phase 16 stack)

Track A never calls ``EvolutionExecutionGateway.execute_request()`` directly
(Phase 16 binding constraint: ``EvolutionAutonomyDispatcher`` is the sole
caller). The kernel wires the sink to the Phase 16 schedule-store/dispatcher
queue; in tests the sink is injected as a fake. If ingestion is refused or
the sink is missing, the bridge fails closed: no silent success, an
``IngestHandoffResult`` with ``accepted=False`` and a meaningful error.

Research executions also emit Evolution-compatible evidence:

  * ``Observation`` (RUNTIME_METRICS, metric ``research:ingest``) — consumed
    by the existing SelfObservation / EvolutionKnowledgePipeline surface.
  * ``EvolutionRecord`` (event_type ``research.ingest``) — audit evidence
    compatible with ``EvolutionMemory`` history.

GOV-008 (RESEARCH_INGEST) is registered as an additive governance rule
(scope KNOWLEDGE, min level INFORMATION). No constitutional change, no
gateway redesign — only additive rule registration.
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
from atlas.research.models import ResearchReport

RESEARCH_DOMAIN: str = "research"

# GOV-008 — RESEARCH_INGEST (additive governance support for Track A).
GOV_008_RULE_ID: str = "GOV-008"
GOV_008_DESCRIPTION: str = (
    "Research ingest (RESEARCH_INGEST) writes into Atlas knowledge only "
    "through the governed INFORMATION-scope evolution path."
)


@runtime_checkable
class ResearchIngestSink(Protocol):
    """The Phase 16 governed hand-off point for a research EvolutionRequest.

    The real implementation (wired by the kernel) forwards the request to
    the Phase 16 schedule store / dispatcher queue so it is validated,
    risk-assessed, authorized, and applied by the evolution stack — never
    by Track A directly.
    """

    def enqueue_request(self, request: EvolutionRequest) -> "IngestHandoffResult": ...


class IngestHandoffResult:
    """Outcome of handing a research evolution request to the sink."""

    __slots__ = ("accepted", "request_id", "error")

    def __init__(self, accepted: bool, request_id: str = "", error: str = "") -> None:
        self.accepted = accepted
        self.request_id = request_id
        self.error = error


@dataclass(frozen=True, slots=True)
class ResearchIngestArtifacts:
    """Deterministic artifacts produced by a research ingest (pure)."""

    request: EvolutionRequest
    observation: Observation
    evidence: EvolutionRecord


def build_ingest_payload(report: ResearchReport) -> dict[str, object]:
    """Build the INFORMATION-scope KNOWLEDGE payload (Phase 16 schema)."""
    return {
        "operation": "add",
        "entry_id": f"research:{report.report_id}",
        "domain": RESEARCH_DOMAIN,
        "content": report.findings,
        "confidence": report.confidence,
    }


class ResearchEvolutionTracker:
    """Pure builder of governed evolution artifacts for a research report."""

    def __init__(self, factory: EvolutionRequestFactory | None = None) -> None:
        self._factory = factory or EvolutionRequestFactory()

    # ------------------------------------------------------------------
    # Artifact construction (no I/O — fully deterministic on inputs)
    # ------------------------------------------------------------------

    def build_artifacts(self, report: ResearchReport) -> ResearchIngestArtifacts:
        """Build request + observation + evidence for one research report.

        Never raises for malformed reports; a report lacking a findings
        text still produces a structurally valid request that the Phase 16
        validator may reject — which is the governed pipeline's decision.
        """
        payload: dict[str, object] = build_ingest_payload(report)
        request: EvolutionRequest = self._factory.from_cli(
            target_scope=ScopeType.KNOWLEDGE,
            change_payload=payload,
            source=f"research:{report.report_id}",
        )
        observation = self._build_observation(report, request)
        evidence = self._build_evidence(report, request)
        return ResearchIngestArtifacts(
            request=request,
            observation=observation,
            evidence=evidence,
        )

    @staticmethod
    def _build_observation(
        report: ResearchReport, request: EvolutionRequest
    ) -> Observation:
        """Evolution-compatible observation for the research execution."""
        return Observation(
            category=ObservationCategory.RUNTIME_METRICS,
            metric_name="research:ingest",
            value={
                "request_id": request.request_id,
                "report_id": report.report_id,
                "scope": request.target_scope.name,
                "claim_count": len(report.claims),
                "verification_count": len(report.verifications),
                "confidence": report.confidence,
            },
            unit="research",
            description=(
                f"Research ingest request {request.request_id} created for "
                f"report {report.report_id} ({len(report.claims)} claims)."
            ),
            source="research",
        )

    @staticmethod
    def _build_evidence(
        report: ResearchReport, request: EvolutionRequest
    ) -> EvolutionRecord:
        """Audit evidence record compatible with EvolutionMemory history."""
        return EvolutionRecord(
            record_id=f"evidence:{request.request_id}",
            event_type="research.ingest",
            description=(
                f"Research report {report.report_id} ingested as governed "
                f"evolution request {request.request_id} (KNOWLEDGE scope)."
            ),
            related_ids=[report.report_id, request.request_id],
            metadata={
                "scope": request.target_scope.name,
                "intended_level": request.intended_level.name,
                "claim_count": len(report.claims),
            },
        )


class ResearchIngestBridge:
    """Hands a research report's governed request to the evolution pipeline.

    Fail-closed: without a sink, or when the sink refuses the request, the
    bridge returns ``accepted=False`` with a meaningful error — it never
    swallows the refusal, never writes knowledge itself, and never calls
    the gateway directly.
    """

    def __init__(
        self,
        tracker: ResearchEvolutionTracker | None = None,
        sink: ResearchIngestSink | None = None,
    ) -> None:
        self._tracker = tracker or ResearchEvolutionTracker()
        self._sink = sink

    @property
    def has_sink(self) -> bool:
        """True when a governed ingest sink is wired."""
        return self._sink is not None

    def ingest(self, report: ResearchReport) -> IngestHandoffResult:
        """Submit a research report through the governed evolution path."""
        artifacts: ResearchIngestArtifacts = self._tracker.build_artifacts(report)
        sink: ResearchIngestSink | None = self._sink
        if sink is None:
            return IngestHandoffResult(
                accepted=False,
                request_id=artifacts.request.request_id,
                error="research ingest sink is not wired (fail closed)",
            )
        handoff: IngestHandoffResult = sink.enqueue_request(artifacts.request)
        if not handoff.accepted:
            return IngestHandoffResult(
                accepted=False,
                request_id=artifacts.request.request_id,
                error=handoff.error or "research ingest refused by evolution pipeline",
            )
        return handoff


def register_gov_008(registry: ConstraintRegistry) -> GovernanceRule:
    """Additively register GOV-008 (RESEARCH_INGEST).

    Scope KNOWLEDGE, minimum level INFORMATION — mirrors GOV-004 and
    documents the research-ingest path. Registration is additive; a
    registry already holding GOV-008 raises ``ValueError`` (id conflicts).
    """
    rule = GovernanceRule(
        rule_id=GOV_008_RULE_ID,
        description=GOV_008_DESCRIPTION,
        scope=ScopeType.KNOWLEDGE,
        min_execution_level=ExecutionLevel.INFORMATION.value,
    )
    registry.register(rule)
    return rule
