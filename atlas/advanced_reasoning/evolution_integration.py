"""Atlas Advanced Reasoning — Evolution Integration (Track D, Batch 3).

Integrates Track D governed ingestion with the Phase 16 Evolution Framework
following the governed mutation discipline EXACTLY — mirroring the Track A
:mod:`atlas.research.evolution_integration`, Track B
:mod:`atlas.toolchain.evolution_integration`, and Track C
:mod:`atlas.longterm.evolution_integration` architecture:

    ReasoningInsight
        → EvolutionRequestFactory (request_factory)
        → EvolutionRequest (target_scope=KNOWLEDGE, intended_level=INFORMATION)
        → injected ReasoningIngestSink  (Phase 16 governed pipeline hand-off)
        → gateway → application        (owned by the Phase 16 stack)

Track D never calls ``EvolutionExecutionGateway.execute_request()`` directly
(Phase 16 binding constraint: ``EvolutionAutonomyDispatcher`` is the sole
caller). The kernel wires the sink to the Phase 16 schedule-store/dispatcher
queue; in tests the sink is injected as a fake. If ingestion is refused or
the sink is missing, the bridge fails closed: no silent success, an
``IngestHandoffResult`` with ``accepted=False`` and a meaningful error.

Reasoning itself is pure computation (Batches 1–2); this module is the ONLY
place that may build an Evolution request for the track, and only through the
explicit ``ingest`` surface — no other Track D component mutates state.

Ingestion also emits Evolution-compatible evidence:

  * ``Observation`` (RUNTIME_METRICS, metric ``reasoning:ingest``) —
    consumed by the existing SelfObservation / EvolutionKnowledgePipeline.
  * ``EvolutionRecord`` (event_type ``reasoning.ingest``) — audit evidence
    compatible with ``EvolutionMemory`` history.

GOV-011 (REASONING_INGEST) is registered as an additive governance rule
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

REASONING_DOMAIN: str = "advanced_reasoning"

# GOV-011 — REASONING_INGEST (additive governance support for Track D).
# Mirrors GOV-008/GOV-009/GOV-010: INFORMATION-scope KNOWLEDGE request.
GOV_011_RULE_ID: str = "GOV-011"
GOV_011_DESCRIPTION: str = (
    "Distilled reasoning insights / strategies (REASONING_INGEST) write into "
    "Atlas state only through the governed INFORMATION-scope evolution path."
)


@runtime_checkable
class ReasoningIngestSink(Protocol):
    """The Phase 16 governed hand-off point for a Track D EvolutionRequest.

    The real implementation (wired by the kernel) forwards the request to
    the Phase 16 schedule store / dispatcher queue so it is validated,
    risk-assessed, authorized, and applied by the evolution stack — never
    by Track D directly.
    """

    def enqueue_request(self, request: EvolutionRequest) -> "IngestHandoffResult": ...


class IngestHandoffResult:
    """Outcome of handing a reasoning evolution request to the sink."""

    __slots__ = ("accepted", "request_id", "error")

    def __init__(self, accepted: bool, request_id: str = "", error: str = "") -> None:
        self.accepted = accepted
        self.request_id = request_id
        self.error = error


@dataclass(frozen=True, slots=True)
class ReasoningIngestArtifacts:
    """Deterministic artifacts produced by a Track D ingest (pure)."""

    request: EvolutionRequest
    observation: Observation
    evidence: EvolutionRecord


def build_ingest_payload(
    content: str,
    source_trace_id: str = "",
    strategy_name: str = "",
    confidence: float = 0.0,
) -> dict[str, object]:
    """Build the INFORMATION-scope KNOWLEDGE payload (Phase 16 schema).

    Deterministic: identical inputs always produce identical payloads.
    The Phase 16 validator owns schema decisions; Track D only builds the
    structurally valid request.
    """
    return {
        "operation": "reasoning_ingest",
        "entry_id": f"advanced_reasoning:insight:{source_trace_id or 'unknown'}",
        "domain": REASONING_DOMAIN,
        "content": content,
        "confidence": confidence,
        "source_trace_id": source_trace_id,
        "strategy_name": strategy_name,
    }


class ReasoningEvolutionTracker:
    """Pure builder of governed evolution artifacts for a reasoning insight."""

    def __init__(self, factory: EvolutionRequestFactory | None = None) -> None:
        self._factory = factory or EvolutionRequestFactory()

    def build_artifacts(
        self,
        content: str,
        source_trace_id: str = "",
        strategy_name: str = "",
        confidence: float = 0.0,
    ) -> ReasoningIngestArtifacts:
        """Build request + observation + evidence for one reasoning insight.

        Never raises for malformed content; an empty insight still produces
        a structurally valid request that the Phase 16 validator may reject —
        which is the governed pipeline's decision.
        """
        payload: dict[str, object] = build_ingest_payload(
            content=content,
            source_trace_id=source_trace_id,
            strategy_name=strategy_name,
            confidence=confidence,
        )
        request: EvolutionRequest = self._factory.from_cli(
            target_scope=ScopeType.KNOWLEDGE,
            change_payload=payload,
            source=f"advanced_reasoning:{source_trace_id or 'insight'}",
        )
        observation = self._build_observation(request, source_trace_id, strategy_name)
        evidence = self._build_evidence(request, source_trace_id, content)
        return ReasoningIngestArtifacts(
            request=request,
            observation=observation,
            evidence=evidence,
        )

    @staticmethod
    def _build_observation(
        request: EvolutionRequest,
        source_trace_id: str,
        strategy_name: str,
    ) -> Observation:
        """Evolution-compatible observation for the reasoning ingest."""
        return Observation(
            category=ObservationCategory.RUNTIME_METRICS,
            metric_name="reasoning:ingest",
            value={
                "request_id": request.request_id,
                "scope": request.target_scope.name,
                "intended_level": request.intended_level.name,
                "source_trace_id": source_trace_id,
                "strategy_name": strategy_name,
            },
            unit="advanced_reasoning",
            description=(
                f"Reasoning ingest request {request.request_id} created "
                f"for trace {source_trace_id or 'unknown'}."
            ),
            source=REASONING_DOMAIN,
        )

    @staticmethod
    def _build_evidence(
        request: EvolutionRequest,
        source_trace_id: str,
        content: str,
    ) -> EvolutionRecord:
        """Audit evidence record compatible with EvolutionMemory history."""
        return EvolutionRecord(
            record_id=f"evidence:{request.request_id}",
            event_type="reasoning.ingest",
            description=(
                f"Reasoning insight from trace {source_trace_id or 'unknown'} "
                f"ingested as governed evolution request {request.request_id} "
                f"(KNOWLEDGE scope)."
            ),
            related_ids=[request.request_id, source_trace_id],
            metadata={
                "scope": request.target_scope.name,
                "intended_level": request.intended_level.name,
                "operation": "reasoning_ingest",
                "content_preview": content[:120],
            },
        )


class ReasoningIngestBridge:
    """Hands a reasoning insight's governed request to the evolution pipeline.

    Fail-closed: without a sink, or when the sink refuses the request, the
    bridge returns ``accepted=False`` with a meaningful error — it never
    swallows the refusal, never mutates state itself, and never calls the
    gateway or dispatcher directly.
    """

    def __init__(
        self,
        tracker: ReasoningEvolutionTracker | None = None,
        sink: ReasoningIngestSink | None = None,
    ) -> None:
        self._tracker = tracker or ReasoningEvolutionTracker()
        self._sink = sink

    @property
    def has_sink(self) -> bool:
        """True when a governed ingest sink is wired."""
        return self._sink is not None

    def ingest(
        self,
        content: str,
        source_trace_id: str = "",
        strategy_name: str = "",
        confidence: float = 0.0,
    ) -> IngestHandoffResult:
        """Submit a reasoning insight through the governed evolution path."""
        artifacts: ReasoningIngestArtifacts = self._tracker.build_artifacts(
            content=content,
            source_trace_id=source_trace_id,
            strategy_name=strategy_name,
            confidence=confidence,
        )
        sink: ReasoningIngestSink | None = self._sink
        if sink is None:
            return IngestHandoffResult(
                accepted=False,
                request_id=artifacts.request.request_id,
                error="reasoning ingest sink is not wired (fail closed)",
            )
        handoff: IngestHandoffResult = sink.enqueue_request(artifacts.request)
        if not handoff.accepted:
            return IngestHandoffResult(
                accepted=False,
                request_id=artifacts.request.request_id,
                error=handoff.error or "reasoning ingest refused by evolution pipeline",
            )
        return handoff


def register_gov_011(registry: ConstraintRegistry) -> GovernanceRule:
    """Additively register GOV-011 (REASONING_INGEST).

    Scope KNOWLEDGE, minimum level INFORMATION — mirrors GOV-008/GOV-009 and
    documents the reasoning ingest path. Registration is additive; a
    registry already holding GOV-011 raises ``ValueError`` (id conflicts).
    """
    rule = GovernanceRule(
        rule_id=GOV_011_RULE_ID,
        description=GOV_011_DESCRIPTION,
        scope=ScopeType.KNOWLEDGE,
        min_execution_level=ExecutionLevel.INFORMATION.value,
    )
    registry.register(rule)
    return rule
