"""Atlas Advanced Reasoning — AdvancedReasoningService (Track D, Batch 3).

Constructor-injected composition root for the advanced-reasoning track. Owns
the deterministic engines (multi-step, causal, hypotheses, verifier, meta),
the reasoning repository, and the governed ingest bridge. Pure bridges route
to this service — no handler mutates state or imports infrastructure.

Design (§9): the engines are private Atlas-owned dependencies composed into
``AdvancedReasoningService``; protocol providers (EvidenceProvider,
CausalGraphProvider, ReasonerModel/VerificationModel/HypothesisModel) are
injected into the engines at the kernel boundary, never imported here. The
governed ingest sink is injected into the bridge; without it, ingestion
fails closed.

No infrastructure imports. No storage. No kernel. No events. Pure logic.
"""

from __future__ import annotations

from typing import Any

from atlas.advanced_reasoning.causal import CausalReasoner
from atlas.advanced_reasoning.evolution_integration import (
    ReasoningIngestBridge,
    ReasoningIngestSink,
)
from atlas.advanced_reasoning.hypotheses import HypothesisGenerator
from atlas.advanced_reasoning.meta import MetaReasoningEngine
from atlas.advanced_reasoning.models import (
    CausalPath,
    CounterfactualResult,
    HypothesisSet,
    MetaAssessment,
    ReasoningConfig,
    ReasoningTrace,
    VerificationReport,
)
from atlas.advanced_reasoning.multi_step import MultiStepReasoner
from atlas.advanced_reasoning.trace_repository import ReasoningTraceRepository
from atlas.advanced_reasoning.verify import SelfVerifier


class AdvancedReasoningService:
    """Composed advanced-reasoning track service.

    Args:
        multi_step: Optional injected multi-step reasoner.
        causal: Optional injected causal reasoner.
        hypotheses: Optional injected hypothesis generator.
        verifier: Optional injected self-verifier.
        meta: Optional injected meta-reasoning engine.
        repository: Optional injected reasoning repository.
        ingest_bridge: Optional injected governed ingest bridge.
        config: Optional reasoning configuration.
        ingest_sink: Optional governed ingest sink (used to build the default
            bridge when ``ingest_bridge`` is omitted).
    """

    def __init__(
        self,
        multi_step: MultiStepReasoner | None = None,
        causal: CausalReasoner | None = None,
        hypotheses: HypothesisGenerator | None = None,
        verifier: SelfVerifier | None = None,
        meta: MetaReasoningEngine | None = None,
        repository: ReasoningTraceRepository | None = None,
        ingest_bridge: ReasoningIngestBridge | None = None,
        config: ReasoningConfig | None = None,
        ingest_sink: ReasoningIngestSink | None = None,
    ) -> None:
        self._config = config or ReasoningConfig()
        self._multi_step = multi_step or MultiStepReasoner(config=self._config)
        self._causal = causal or CausalReasoner()
        self._hypotheses = hypotheses or HypothesisGenerator(config=self._config)
        self._verifier = verifier or SelfVerifier()
        self._meta = meta or MetaReasoningEngine(config=self._config)
        self._repository = repository or ReasoningTraceRepository()
        self._ingest_bridge = ingest_bridge or ReasoningIngestBridge(
            sink=ingest_sink
        )

    @property
    def config(self) -> ReasoningConfig:
        return self._config

    @property
    def multi_step(self) -> MultiStepReasoner:
        return self._multi_step

    @property
    def causal(self) -> CausalReasoner:
        return self._causal

    @property
    def hypotheses(self) -> HypothesisGenerator:
        return self._hypotheses

    @property
    def verifier(self) -> SelfVerifier:
        return self._verifier

    @property
    def meta(self) -> MetaReasoningEngine:
        return self._meta

    @property
    def repository(self) -> ReasoningTraceRepository:
        return self._repository

    @property
    def ingest_bridge(self) -> ReasoningIngestBridge:
        return self._ingest_bridge

    # ------------------------------------------------------------------
    # Domain operations
    # ------------------------------------------------------------------

    def reason(
        self,
        question: str,
        max_steps: int | None = None,
        trace_id: str | None = None,
    ) -> ReasoningTrace:
        """Run deterministic multi-step reasoning and store the trace."""
        trace = self._multi_step.reason(
            question=question,
            max_steps=max_steps,
            trace_id=trace_id,
        )
        self._repository.store_trace(trace)
        return trace

    def causal_paths(
        self,
        source: str,
        target: str,
        max_depth: int | None = None,
    ) -> tuple[CausalPath, ...]:
        """Analyze causal chains from ``source`` to ``target``."""
        return self._causal.analyze(source, target, max_depth=max_depth)

    def counterfactual(
        self,
        source_event: str,
        assumption: str,
        max_depth: int | None = None,
        result_id: str | None = None,
    ) -> CounterfactualResult:
        """Evaluate a what-if counterfactual (read-only)."""
        return self._causal.counterfactual(
            source_event=source_event,
            assumption=assumption,
            max_depth=max_depth,
            result_id=result_id,
        )

    def generate_hypotheses(
        self,
        claim: str,
        limit: int | None = None,
        set_id: str | None = None,
    ) -> HypothesisSet:
        """Generate and rank competing hypotheses, storing the set."""
        result = self._hypotheses.generate(claim, limit=limit, set_id=set_id)
        self._repository.store_hypothesis_set(result)
        return result

    def verify(
        self,
        target: ReasoningTrace | str,
        report_id: str | None = None,
    ) -> VerificationReport:
        """Self-verify a trace or a raw claim, storing the report."""
        report = self._verifier.verify(target, report_id=report_id)
        self._repository.store_verification_report(report)
        return report

    def meta_assess(
        self,
        traces: tuple[Any, ...] = (),
        window_size: int | None = None,
        assessment_id: str | None = None,
    ) -> MetaAssessment:
        """Produce a meta-reasoning assessment, storing it."""
        assessment = self._meta.assess(
            traces=traces,
            window_size=window_size,
            assessment_id=assessment_id,
        )
        self._repository.store_meta_assessment(assessment)
        return assessment