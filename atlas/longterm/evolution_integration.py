"""Atlas Long-Term Learning — Evolution Integration (Track C, Batch 4).

Integrates Track C consolidation with the Phase 16 Evolution Framework
following the governed mutation discipline EXACTLY — mirroring the Track A
:mod:`atlas.research.evolution_integration` and Track B
:mod:`atlas.toolchain.evolution_integration` architecture:

    ConsolidationRecord
        → EvolutionRequestFactory (request_factory)
        → EvolutionRequest (target_scope=MEMORY, intended_level=INFORMATION)
        → injected LongTermIngestSink  (Phase 16 governed pipeline hand-off)
        → gateway → application        (owned by the Phase 16 stack)

Track C never calls ``EvolutionExecutionGateway.execute_request()`` directly
(Phase 16 binding constraint: ``EvolutionAutonomyDispatcher`` is the sole
caller). The kernel wires the sink to the Phase 16 schedule-store/dispatcher
queue; in tests the sink is injected as a fake. If ingestion is refused or
the sink is missing, the bridge fails closed: no silent success, an
``IngestHandoffResult`` with ``accepted=False`` and a meaningful error.

Consolidation therefore NEVER mutates the long-term repositories directly
from Track C code — forgetting/merging is a governed mutation owned by the
Phase 16 pipeline (GOV-010 documents the path).

Consolidation also emits Evolution-compatible evidence:

  * ``Observation`` (RUNTIME_METRICS, metric ``memory:consolidate``) —
    consumed by the existing SelfObservation / EvolutionKnowledgePipeline.
  * ``EvolutionRecord`` (event_type ``memory.consolidate``) — audit evidence
    compatible with ``EvolutionMemory`` history.

GOV-010 (MEMORY_CONSOLIDATE / LONGTERM_INGEST) is registered as an additive
governance rule (scope MEMORY, min level INFORMATION). No constitutional
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
from atlas.longterm.models import ConsolidationRecord

LONGTERM_DOMAIN: str = "longterm"

# GOV-010 — MEMORY_CONSOLIDATE / LONGTERM_INGEST (additive governance support
# for Track C). Mirrors GOV-008/GOV-009: INFORMATION-scope MEMORY request.
GOV_010_RULE_ID: str = "GOV-010"
GOV_010_DESCRIPTION: str = (
    "Memory consolidation / long-term ingest (LONGTERM_INGEST) writes into "
    "Atlas state only through the governed INFORMATION-scope evolution path."
)


@runtime_checkable
class LongTermIngestSink(Protocol):
    """The Phase 16 governed hand-off point for a long-term EvolutionRequest.

    The real implementation (wired by the kernel) forwards the request to
    the Phase 16 schedule store / dispatcher queue so it is validated,
    risk-assessed, authorized, and applied by the evolution stack — never
    by Track C directly.
    """

    def enqueue_request(self, request: EvolutionRequest) -> "IngestHandoffResult": ...


class IngestHandoffResult:
    """Outcome of handing a long-term evolution request to the sink."""

    __slots__ = ("accepted", "request_id", "error")

    def __init__(self, accepted: bool, request_id: str = "", error: str = "") -> None:
        self.accepted = accepted
        self.request_id = request_id
        self.error = error


@dataclass(frozen=True, slots=True)
class LongTermIngestArtifacts:
    """Deterministic artifacts produced by a long-term ingest (pure)."""

    request: EvolutionRequest
    observation: Observation
    evidence: EvolutionRecord


def build_ingest_payload(record: ConsolidationRecord) -> dict[str, object]:
    """Build the INFORMATION-scope MEMORY payload (Phase 16 schema).

    Deterministic: identical records always produce identical payloads.
    The Phase 16 validator owns schema decisions; Track C only builds the
    structurally valid request.
    """
    return {
        "operation": record.operation or "consolidate",
        "entry_id": f"longterm:{record.record_id}",
        "domain": LONGTERM_DOMAIN,
        "content": record.reason,
        "confidence": 1.0,
        "record_id": record.record_id,
        "status": record.status.name,
        "target_type": record.target_type,
        "target_ids": list(record.target_ids),
    }


class LongTermEvolutionTracker:
    """Pure builder of governed evolution artifacts for a consolidation."""

    def __init__(self, factory: EvolutionRequestFactory | None = None) -> None:
        self._factory = factory or EvolutionRequestFactory()

    # ------------------------------------------------------------------
    # Artifact construction (no I/O — fully deterministic on inputs)
    # ------------------------------------------------------------------

    def build_artifacts(
        self, record: ConsolidationRecord
    ) -> LongTermIngestArtifacts:
        """Build request + observation + evidence for one consolidation.

        Never raises for malformed records; a record lacking a reason
        still produces a structurally valid request that the Phase 16
        validator may reject — which is the governed pipeline's decision.
        """
        payload: dict[str, object] = build_ingest_payload(record)
        request: EvolutionRequest = self._factory.from_cli(
            target_scope=ScopeType.MEMORY,
            change_payload=payload,
            source=f"longterm:{record.record_id}",
        )
        observation = self._build_observation(record, request)
        evidence = self._build_evidence(record, request)
        return LongTermIngestArtifacts(
            request=request,
            observation=observation,
            evidence=evidence,
        )

    @staticmethod
    def _build_observation(
        record: ConsolidationRecord, request: EvolutionRequest
    ) -> Observation:
        """Evolution-compatible observation for the consolidation."""
        return Observation(
            category=ObservationCategory.RUNTIME_METRICS,
            metric_name="memory:consolidate",
            value={
                "request_id": request.request_id,
                "record_id": record.record_id,
                "scope": request.target_scope.name,
                "operation": record.operation,
                "target_type": record.target_type,
                "target_count": len(record.target_ids),
            },
            unit="longterm",
            description=(
                f"Memory consolidation request {request.request_id} created "
                f"for record {record.record_id} ({record.operation})."
            ),
            source="longterm",
        )

    @staticmethod
    def _build_evidence(
        record: ConsolidationRecord, request: EvolutionRequest
    ) -> EvolutionRecord:
        """Audit evidence record compatible with EvolutionMemory history."""
        return EvolutionRecord(
            record_id=f"evidence:{request.request_id}",
            event_type="memory.consolidate",
            description=(
                f"Consolidation record {record.record_id} ingested as governed "
                f"evolution request {request.request_id} (MEMORY scope)."
            ),
            related_ids=[record.record_id, request.request_id],
            metadata={
                "scope": request.target_scope.name,
                "intended_level": request.intended_level.name,
                "operation": record.operation,
                "target_type": record.target_type,
            },
        )


class LongTermIngestBridge:
    """Hands a consolidation's governed request to the evolution pipeline.

    Fail-closed: without a sink, or when the sink refuses the request, the
    bridge returns ``accepted=False`` with a meaningful error — it never
    swallows the refusal, never mutates the long-term repositories itself,
    and never calls the gateway or dispatcher directly.
    """

    def __init__(
        self,
        tracker: LongTermEvolutionTracker | None = None,
        sink: LongTermIngestSink | None = None,
    ) -> None:
        self._tracker = tracker or LongTermEvolutionTracker()
        self._sink = sink

    @property
    def has_sink(self) -> bool:
        """True when a governed ingest sink is wired."""
        return self._sink is not None

    def ingest(self, record: ConsolidationRecord) -> IngestHandoffResult:
        """Submit a consolidation record through the governed evolution path."""
        artifacts: LongTermIngestArtifacts = self._tracker.build_artifacts(record)
        sink: LongTermIngestSink | None = self._sink
        if sink is None:
            return IngestHandoffResult(
                accepted=False,
                request_id=artifacts.request.request_id,
                error="longterm ingest sink is not wired (fail closed)",
            )
        handoff: IngestHandoffResult = sink.enqueue_request(artifacts.request)
        if not handoff.accepted:
            return IngestHandoffResult(
                accepted=False,
                request_id=artifacts.request.request_id,
                error=handoff.error or "longterm ingest refused by evolution pipeline",
            )
        return handoff


def register_gov_010(registry: ConstraintRegistry) -> GovernanceRule:
    """Additively register GOV-010 (LONGTERM_INGEST).

    Scope MEMORY, minimum level INFORMATION — mirrors GOV-008/GOV-009 and
    documents the consolidation ingest path. Registration is additive; a
    registry already holding GOV-010 raises ``ValueError`` (id conflicts).
    """
    rule = GovernanceRule(
        rule_id=GOV_010_RULE_ID,
        description=GOV_010_DESCRIPTION,
        scope=ScopeType.MEMORY,
        min_execution_level=ExecutionLevel.INFORMATION.value,
    )
    registry.register(rule)
    return rule
