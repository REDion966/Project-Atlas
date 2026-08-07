"""Atlas Advanced Reasoning — Capability Handlers (Track D, Batch 3).

Registers the Track D capabilities following the Atlas ``CapabilityRegistry``
pattern (``CapabilityHandler = Callable[[dict], ExecutionResult]``):

  reasoning.trace          — deterministic multi-step reasoning to a trace
  reasoning.causal         — causal path analysis for an event/property
  reasoning.counterfactual — what-if evaluation under an altered assumption
  reasoning.hypotheses     — generate and rank competing hypotheses
  reasoning.verify         — self-verify a trace or conclusion
  reasoning.meta           — read a meta-reasoning strategy-effectiveness report
  reasoning.ingest         — GOVERNED: submit a distilled insight via the bridge

Handlers are pure bridges: all work is delegated to the injected
``AdvancedReasoningService`` (constructor-injected composition). No handler
mutates Atlas state. ``reasoning.ingest`` NEVER mutates any store — it builds
an INFORMATION-scope KNOWLEDGE request and hands it through the
``ReasoningIngestBridge``; without a sink it fails closed.

No handler mutates the ``CapabilityRegistry`` directly — the
:meth:`AdvancedReasoningCapabilityFactory.register` method is the only
registration surface.
"""

from __future__ import annotations

from typing import Any, Callable

from atlas.advanced_reasoning.evolution_integration import IngestHandoffResult
from atlas.advanced_reasoning.models import ReasoningTrace
from atlas.advanced_reasoning.service import AdvancedReasoningService

from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry

CapabilityHandler = Callable[[dict[str, Any]], ExecutionResult]

#: Upper bound for optional ``limit`` / ``max_steps`` integer inputs.
_MAX_LIMIT: int = 500


class AdvancedReasoningCapabilityFactory:
    """Constructs the seven Track D capability handlers with DI.

    Args:
        service: The composed advanced-reasoning service the handlers route
            to. A default service is constructed when ``None`` is given.
    """

    def __init__(self, service: AdvancedReasoningService | None = None) -> None:
        self._service = service or AdvancedReasoningService()

    @property
    def service(self) -> AdvancedReasoningService:
        return self._service

    # ------------------------------------------------------------------
    # Registration surface
    # ------------------------------------------------------------------

    def handlers(self) -> dict[str, CapabilityHandler]:
        """Return the seven reasoning capabilities keyed by name."""
        return {
            "reasoning.trace": self._trace_handler,
            "reasoning.causal": self._causal_handler,
            "reasoning.counterfactual": self._counterfactual_handler,
            "reasoning.hypotheses": self._hypotheses_handler,
            "reasoning.verify": self._verify_handler,
            "reasoning.meta": self._meta_handler,
            "reasoning.ingest": self._ingest_handler,
        }

    def register(self, registry: CapabilityRegistry) -> None:
        """Register all seven handlers into a ``CapabilityRegistry``."""
        for name, handler in self.handlers().items():
            registry.register(name, handler)

    # ------------------------------------------------------------------
    # reasoning.trace
    # ------------------------------------------------------------------

    def _trace_handler(self, payload: dict[str, Any]) -> ExecutionResult:
        try:
            question = str(payload.get("question") or "").strip()
            if not question:
                return ExecutionResult(
                    capability="reasoning.trace",
                    success=False,
                    error="reasoning.trace requires a non-empty question",
                    metadata={"handler": "reasoning.trace"},
                )
            trace: ReasoningTrace = self._service.reason(
                question=question,
                max_steps=self._positive_int(payload.get("max_steps")),
                trace_id=self._optional_str(payload.get("trace_id")),
            )
            return ExecutionResult(
                capability="reasoning.trace",
                success=True,
                output={
                    "trace": trace.to_dict(),
                    "trace_id": trace.trace_id,
                    "question": trace.question,
                    "conclusion": trace.conclusion,
                    "confidence": trace.confidence,
                    "status": trace.status.name,
                    "strategy": trace.strategy.name,
                },
                metadata={"handler": "reasoning.trace", "trace_id": trace.trace_id},
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="reasoning.trace",
                success=False,
                error=str(exc),
                metadata={"handler": "reasoning.trace"},
            )

    # ------------------------------------------------------------------
    # reasoning.causal
    # ------------------------------------------------------------------

    def _causal_handler(self, payload: dict[str, Any]) -> ExecutionResult:
        try:
            source = str(payload.get("source") or "").strip()
            target = str(payload.get("target") or "").strip()
            if not source or not target:
                return ExecutionResult(
                    capability="reasoning.causal",
                    success=False,
                    error="reasoning.causal requires source and target",
                    metadata={"handler": "reasoning.causal"},
                )
            paths = self._service.causal_paths(
                source=source,
                target=target,
                max_depth=self._positive_int(payload.get("max_depth")),
            )
            return ExecutionResult(
                capability="reasoning.causal",
                success=True,
                output={
                    "paths": tuple(p.to_dict() for p in paths),
                    "explanations": tuple(self._service.causal.explain_all(paths)),
                    "count": len(paths),
                },
                metadata={
                    "handler": "reasoning.causal",
                    "source": source,
                    "target": target,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="reasoning.causal",
                success=False,
                error=str(exc),
                metadata={"handler": "reasoning.causal"},
            )

    # ------------------------------------------------------------------
    # reasoning.counterfactual
    # ------------------------------------------------------------------

    def _counterfactual_handler(self, payload: dict[str, Any]) -> ExecutionResult:
        try:
            event = str(payload.get("event") or "").strip()
            assumption = str(payload.get("assumption") or "").strip()
            if not event or not assumption:
                return ExecutionResult(
                    capability="reasoning.counterfactual",
                    success=False,
                    error="reasoning.counterfactual requires event and assumption",
                    metadata={"handler": "reasoning.counterfactual"},
                )
            result = self._service.counterfactual(
                source_event=event,
                assumption=assumption,
                max_depth=self._positive_int(payload.get("max_depth")),
                result_id=self._optional_str(payload.get("result_id")),
            )
            return ExecutionResult(
                capability="reasoning.counterfactual",
                success=True,
                output={
                    "result": result.to_dict(),
                    "changed": result.changed,
                    "effect_summary": result.effect_summary,
                },
                metadata={"handler": "reasoning.counterfactual", "source_event": event},
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="reasoning.counterfactual",
                success=False,
                error=str(exc),
                metadata={"handler": "reasoning.counterfactual"},
            )

    # ------------------------------------------------------------------
    # reasoning.hypotheses
    # ------------------------------------------------------------------

    def _hypotheses_handler(self, payload: dict[str, Any]) -> ExecutionResult:
        try:
            claim = str(payload.get("claim") or "").strip()
            if not claim:
                return ExecutionResult(
                    capability="reasoning.hypotheses",
                    success=False,
                    error="reasoning.hypotheses requires a claim",
                    metadata={"handler": "reasoning.hypotheses"},
                )
            result = self._service.generate_hypotheses(
                claim=claim,
                limit=self._positive_int(payload.get("limit")),
                set_id=self._optional_str(payload.get("set_id")),
            )
            return ExecutionResult(
                capability="reasoning.hypotheses",
                success=True,
                output={
                    "hypothesis_set": result.to_dict(),
                    "set_id": result.set_id,
                    "count": result.count,
                    "top_hypothesis_id": result.top_hypothesis_id,
                },
                metadata={"handler": "reasoning.hypotheses", "set_id": result.set_id},
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="reasoning.hypotheses",
                success=False,
                error=str(exc),
                metadata={"handler": "reasoning.hypotheses"},
            )

    # ------------------------------------------------------------------
    # reasoning.verify
    # ------------------------------------------------------------------

    def _verify_handler(self, payload: dict[str, Any]) -> ExecutionResult:
        try:
            trace_id = self._optional_str(payload.get("trace_id"))
            claim = str(payload.get("claim") or "").strip()
            if not trace_id and not claim:
                return ExecutionResult(
                    capability="reasoning.verify",
                    success=False,
                    error="reasoning.verify requires a trace_id or claim",
                    metadata={"handler": "reasoning.verify"},
                )
            if trace_id:
                trace = self._service.repository.get_trace(trace_id)
                if trace is None:
                    return ExecutionResult(
                        capability="reasoning.verify",
                        success=False,
                        error=f"reasoning.verify: no trace found for {trace_id!r}",
                        metadata={"handler": "reasoning.verify", "trace_id": trace_id},
                    )
                report = self._service.verify(trace)
            else:
                report = self._service.verify(claim)
            return ExecutionResult(
                capability="reasoning.verify",
                success=True,
                output={
                    "report": report.to_dict(),
                    "report_id": report.report_id,
                    "verdict": report.verdict.name,
                    "target_id": report.target_id,
                },
                metadata={"handler": "reasoning.verify", "report_id": report.report_id},
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="reasoning.verify",
                success=False,
                error=str(exc),
                metadata={"handler": "reasoning.verify"},
            )

    # ------------------------------------------------------------------
    # reasoning.meta
    # ------------------------------------------------------------------

    def _meta_handler(self, payload: dict[str, Any]) -> ExecutionResult:
        try:
            limit = self._positive_int(payload.get("limit"))
            assessment = self._service.meta_assess(
                traces=self._traces_payload(payload),
                window_size=limit,
                assessment_id=self._optional_str(payload.get("assessment_id")),
            )
            return ExecutionResult(
                capability="reasoning.meta",
                success=True,
                output={
                    "assessment": assessment.to_dict(),
                    "assessment_id": assessment.assessment_id,
                    "recommended_strategy": assessment.recommended_strategy.name,
                    "recommendation_reason": assessment.recommendation_reason,
                },
                metadata={
                    "handler": "reasoning.meta",
                    "assessment_id": assessment.assessment_id,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="reasoning.meta",
                success=False,
                error=str(exc),
                metadata={"handler": "reasoning.meta"},
            )

    # ------------------------------------------------------------------
    # reasoning.ingest (GOVERNED — never mutates any store)
    # ------------------------------------------------------------------

    def _ingest_handler(self, payload: dict[str, Any]) -> ExecutionResult:
        try:
            trace_id = self._optional_str(payload.get("trace_id"))
            content = str(payload.get("content") or "").strip()
            strategy_name = str(payload.get("strategy_name") or "").strip()
            confidence = self._confidence(payload.get("confidence"))

            source_trace_id: str = trace_id
            if trace_id:
                trace = self._service.repository.get_trace(trace_id)
                if trace is None:
                    return ExecutionResult(
                        capability="reasoning.ingest",
                        success=False,
                        error=f"reasoning.ingest: no trace found for {trace_id!r}",
                        metadata={"handler": "reasoning.ingest", "trace_id": trace_id},
                    )
                if not content:
                    content = trace.conclusion or trace.question
                if not strategy_name:
                    strategy_name = trace.strategy.name
            if not content:
                return ExecutionResult(
                    capability="reasoning.ingest",
                    success=False,
                    error="reasoning.ingest requires a trace_id or content",
                    metadata={"handler": "reasoning.ingest"},
                )

            handoff: IngestHandoffResult = self._service.ingest_bridge.ingest(
                content=content,
                source_trace_id=source_trace_id,
                strategy_name=strategy_name,
                confidence=confidence,
            )
            if not handoff.accepted:
                return ExecutionResult(
                    capability="reasoning.ingest",
                    success=False,
                    error=handoff.error or "reasoning ingest refused",
                    output={"request_id": handoff.request_id, "accepted": False},
                    metadata={
                        "handler": "reasoning.ingest",
                        "governed": True,
                        "accepted": False,
                    },
                )
            return ExecutionResult(
                capability="reasoning.ingest",
                success=True,
                output={
                    "request_id": handoff.request_id,
                    "accepted": True,
                    "source_trace_id": source_trace_id,
                },
                metadata={
                    "handler": "reasoning.ingest",
                    "governed": True,
                    "accepted": True,
                    "request_id": handoff.request_id,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="reasoning.ingest",
                success=False,
                error=str(exc),
                metadata={"handler": "reasoning.ingest", "governed": True},
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _positive_int(raw: Any, default: int | None = None) -> int | None:
        """Coerce an optional integer into a bounded positive int."""
        if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
            return default
        return min(raw, _MAX_LIMIT)

    @staticmethod
    def _confidence(raw: Any) -> float:
        """Coerce an optional confidence into [0.0, 1.0]."""
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return 0.0
        return max(0.0, min(1.0, float(raw)))

    @staticmethod
    def _optional_str(raw: Any) -> str:
        """Coerce an optional value into a stripped string (or "")."""
        return str(raw).strip() if raw not in (None, "") else ""

    def _traces_payload(self, payload: dict[str, Any]) -> tuple[Any, ...]:
        """Extract an optional ``traces`` sequence from a payload."""
        raw = payload.get("traces")
        if isinstance(raw, (tuple, list)):
            return tuple(raw)
        return tuple()