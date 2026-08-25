"""Atlas Research — Capability Handlers (Phase 17.7).

Registers the three Track A capabilities following the Atlas
``CapabilityRegistry`` pattern (``CapabilityHandler = Callable[[dict], ExecutionResult]``):

  research.query      — full pipeline: plan → adapt → extract → verify → report
  research.verify     — verify extracted claims against sources
  research.summarize  — deterministic summary of a research report

Handlers are pure bridges: all work is delegated to injected components
(planner, adapters, extractor, verifier). Deterministic, no mutation,
no evolution, no storage writes from the handlers themselves.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from atlas.evolution.models import ResearchQuery
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.research.coordinator import ConcreteResearchCoordinator
from atlas.research.extractor import KnowledgeExtractor
from atlas.research.models import (
    ClaimVerification,
    KnowledgeClaim,
    ResearchPlan,
    ResearchReport,
    ResearchSource,
    SourceProfile,
)
from atlas.research.planner import ResearchPlanner
from atlas.research.sources import (
    CodebaseSourceAdapter,
    DocumentSourceAdapter,
    WebSourceAdapter,
    WorkspaceSourceAdapter,
)
from atlas.research.sources.web import web_host_policy_from_hosts
from atlas.research.verifier import ClaimVerifier

CapabilityHandler = Callable[[dict], ExecutionResult]


class ResearchCapabilityFactory:
    """Constructs the Track A capability handlers with DI.

    Phase 21 adds an optional ``coordinator``. When injected, a fourth
    additive capability ``research.coordinate`` is registered that delegates
    the whole Track A pipeline to the concrete ResearchCoordinator. Without a
    coordinator the factory is identical to the pre-Phase-21 surface
    (research.query / research.verify / research.summarize).
    """

    def __init__(
        self,
        planner: ResearchPlanner | None = None,
        extractor: KnowledgeExtractor | None = None,
        verifier: ClaimVerifier | None = None,
        coordinator: ConcreteResearchCoordinator | None = None,
        web_hosts: Sequence[str] = (),
    ) -> None:
        """Initialise the factory with injected Track A components.

        Args:
            planner: Existing ResearchPlanner (defaults to a fresh one).
            extractor: Existing KnowledgeExtractor (defaults to a fresh one).
            verifier: Existing ClaimVerifier (defaults to a fresh one).
            coordinator: Optional concrete ResearchCoordinator.
            web_hosts: Explicit web host allowlist for the bounded web source
                adapter. Empty (the default) keeps the adapter deny-by-default;
                all SSRF protections remain mandatory regardless of entries.
        """
        self._planner = planner or ResearchPlanner()
        self._extractor = extractor or KnowledgeExtractor()
        self._verifier = verifier or ClaimVerifier()
        self._coordinator = coordinator
        self._web_host_policy = web_host_policy_from_hosts(web_hosts)

    @property
    def planner(self) -> ResearchPlanner:
        return self._planner

    @property
    def extractor(self) -> KnowledgeExtractor:
        return self._extractor

    @property
    def verifier(self) -> ClaimVerifier:
        return self._verifier

    @property
    def coordinator(self) -> ConcreteResearchCoordinator | None:
        """Return the injected concrete coordinator, or None."""
        return self._coordinator

    def set_coordinator(self, coordinator: ConcreteResearchCoordinator) -> None:
        """Atomically (re)bind the coordinator and expose research.coordinate.

        Additive Phase 21 wiring: called by the kernel after the coordinator
        is fully constructed (post storage init) so the same factory's
        planner/extractor/verifier instances are reused — no duplicate
        Track A components are created.
        """
        self._coordinator = coordinator

    def register_coordinator(
        self,
        coordinator: ConcreteResearchCoordinator,
        registry: CapabilityRegistry,
    ) -> None:
        """Additively register ``research.coordinate`` into a registry.

        The kernel calls this once the concrete coordinator exists. It never
        re-registers the existing three research handlers (which would raise
        ``ValueError`` on duplicate registration); it only adds the new
        plan-reachable capability if absent.
        """
        self.set_coordinator(coordinator)
        if not registry.has("research.coordinate"):
            registry.register("research.coordinate", self._coordinate_handler)

    # ------------------------------------------------------------------
    # Registration surface
    # ------------------------------------------------------------------

    def handlers(self) -> dict[str, CapabilityHandler]:
        """Return the research capabilities keyed by name.

        Additive (Phase 21): ``research.coordinate`` is only included when
        a concrete coordinator has been injected. Without a coordinator the
        returned map is identical to the pre-Phase-21 three-handler surface.
        """
        handlers: dict[str, CapabilityHandler] = {
            "research.query": self._query_handler,
            "research.verify": self._verify_handler,
            "research.summarize": self._summarize_handler,
        }
        if self._coordinator is not None:
            handlers["research.coordinate"] = self._coordinate_handler
        return handlers

    def register(self, registry: CapabilityRegistry) -> None:
        """Register all handlers into a CapabilityRegistry."""
        for name, handler in self.handlers().items():
            registry.register(name, handler)

    # ------------------------------------------------------------------
    # research.coordinate — plan-driven delegation to the coordinator
    # ------------------------------------------------------------------

    def _coordinate_handler(self, params: dict) -> ExecutionResult:
        """Delegate the full Track A pipeline to the injected coordinator.

        Reachable from a planning step whose action is ``research.coordinate``
        through the existing CapabilityRegistry/Router/Dispatcher path. Invokes
        the coordinator exactly once. Fail-soft: the coordinator never raises,
        and a defensive boundary converts unexpected errors into a failed
        ExecutionResult (same convention as the other research handlers).
        """
        coordinator = self._coordinator
        if coordinator is None:
            return ExecutionResult(
                capability="research.coordinate",
                success=False,
                error="research coordinator is not injected",
                metadata={"handler": "research.coordinate"},
            )
        question = params.get("question")
        if not isinstance(question, str) or not question.strip():
            # Plan steps reach this handler through the capability passthrough,
            # which delivers the step's action as ``{"action": ...}`` (same
            # style as the other research handlers). Fall back to the action so
            # a bare plan step still executes the coordinator deterministically.
            action = params.get("action")
            if isinstance(action, str) and action.strip():
                question = action
            else:
                return ExecutionResult(
                    capability="research.coordinate",
                    success=False,
                    error="'question' is required",
                    metadata={"handler": "research.coordinate"},
                )
        query_id = str(params.get("query_id", "cli"))
        query = ResearchQuery(
            query_id=query_id,
            question=question,
            context=dict(params.get("context", {}) or {}),
        )
        try:
            result = coordinator.run(query)
            return ExecutionResult(
                capability="research.coordinate",
                success=True,
                output={
                    "query_id": result.query_id,
                    "findings": result.findings,
                    "sources": list(result.sources or []),
                    "confidence": result.confidence,
                    "completed_at": result.completed_at.isoformat()
                    if hasattr(result.completed_at, "isoformat")
                    else str(result.completed_at),
                },
                metadata={"handler": "research.coordinate"},
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="research.coordinate",
                success=False,
                error=str(exc),
                metadata={"handler": "research.coordinate"},
            )

    # ------------------------------------------------------------------
    # research.query — full pipeline
    # ------------------------------------------------------------------

    def _query_handler(self, params: dict) -> ExecutionResult:
        question = params.get("question")
        if not isinstance(question, str) or not question.strip():
            return ExecutionResult(
                capability="research.query",
                success=False,
                error="'question' is required",
                metadata={"handler": "research.query"},
            )
        query_id = str(params.get("query_id", "cli"))
        try:
            sources = self._resolve_sources(params.get("sources", []))
            plan: ResearchPlan = self._planner.plan(
                ResearchQuery(query_id=query_id, question=question)
            )
            claims: list[KnowledgeClaim] = []
            profiles = [p for p in sources if isinstance(p, SourceProfile)]
            for profile in profiles:
                claims.extend(self._extractor.extract(profile))
            verifications: list[ClaimVerification] = []
            if claims:
                verifications = self._verifier.verify(claims, profiles)
            report = ResearchReport(
                report_id=f"report:{query_id}:{plan.plan_id}",
                plan_id=plan.plan_id,
                query_id=query_id,
                question=question,
                findings=self._summarize_report_text(plan, verifications),
                claims=tuple(claims),
                verifications=tuple(verifications),
                confidence=(
                    sum(v.score for v in verifications) / len(verifications)
                    if verifications
                    else 0.0
                ),
                metadata={"target_sources": [k.name for k in plan.target_sources]},
            )
            return ExecutionResult(
                capability="research.query",
                success=True,
                output={"report": report.to_dict()},
                metadata={"handler": "research.query", "claims": len(claims)},
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="research.query",
                success=False,
                error=str(exc),
                metadata={"handler": "research.query"},
            )

    # ------------------------------------------------------------------
    # research.verify — verify claims against sources
    # ------------------------------------------------------------------

    def _verify_handler(self, params: dict) -> ExecutionResult:
        claims = params.get("claims")
        sources = params.get("sources")
        if not isinstance(claims, list) or not all(
            isinstance(c, KnowledgeClaim) for c in claims
        ):
            return ExecutionResult(
                capability="research.verify",
                success=False,
                error="'claims' must be a list of KnowledgeClaim",
                metadata={"handler": "research.verify"},
            )
        if not isinstance(sources, list) or not all(
            isinstance(s, (ResearchSource, SourceProfile)) for s in sources
        ):
            return ExecutionResult(
                capability="research.verify",
                success=False,
                error="'sources' must be a list of source objects",
                metadata={"handler": "research.verify"},
            )
        try:
            verifications = self._verifier.verify(claims, sources)
            return ExecutionResult(
                capability="research.verify",
                success=True,
                output={"verifications": [v.to_dict() for v in verifications]},
                metadata={"handler": "research.verify", "count": len(verifications)},
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="research.verify",
                success=False,
                error=str(exc),
                metadata={"handler": "research.verify"},
            )

    # ------------------------------------------------------------------
    # research.summarize — deterministic report summary
    # ------------------------------------------------------------------

    def _summarize_handler(self, params: dict) -> ExecutionResult:
        report = params.get("report")
        if not isinstance(report, ResearchReport):
            return ExecutionResult(
                capability="research.summarize",
                success=False,
                error="'report' must be a ResearchReport",
                metadata={"handler": "research.summarize"},
            )
        summary = self._summarize_report_text(None, list(report.verifications))
        return ExecutionResult(
            capability="research.summarize",
            success=True,
            output={"summary": summary},
            metadata={"handler": "research.summarize"},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_sources(self, specs: list) -> list[ResearchSource | SourceProfile]:
        """Resolve URI specs via the local adapters (workspace/codebase/doc/web)."""
        if not isinstance(specs, list):
            return []
        document = DocumentSourceAdapter()
        workspace = WorkspaceSourceAdapter(root=Path("."))
        codebase = CodebaseSourceAdapter()
        web = WebSourceAdapter(host_policy=self._web_host_policy)
        resolved: list[ResearchSource | SourceProfile] = []
        for spec in specs:
            if isinstance(spec, (ResearchSource, SourceProfile)):
                resolved.append(spec)
                continue
            if isinstance(spec, str):
                try:
                    if workspace.supports(spec):
                        candidate = workspace.load(spec)
                    elif codebase.supports(spec):
                        candidate = codebase.load(spec)
                    elif document.supports(spec):
                        candidate = document.load(spec)
                    elif web.supports(spec):
                        # Web is tried last; the default adapter is
                        # deny-by-default so explicit configuration is
                        # required before any host may be fetched.
                        candidate = web.load(spec)
                    else:
                        continue
                    resolved.append(candidate)
                except (ValueError, OSError):
                    continue
        return resolved

    @staticmethod
    def _summarize_report_text(
        plan: ResearchPlan | None, verifications: list[ClaimVerification]
    ) -> str:
        outcomes: dict[str, int] = {}
        for v in verifications:
            label = v.metadata.get("outcome", v.status.name)
            outcomes[label] = outcomes.get(label, 0) + 1
        parts = [f"{k}={n}" for k, n in sorted(outcomes.items())]
        return "verification summary: " + (", ".join(parts) if parts else "no claims verified")


# ---------------------------------------------------------------------------
# Module-level convenience for registry registration
# ---------------------------------------------------------------------------

_research_factory: ResearchCapabilityFactory | None = None


def research_handlers() -> dict[str, CapabilityHandler]:
    """Return the three research capability handlers (cached factory)."""
    global _research_factory
    if _research_factory is None:
        _research_factory = ResearchCapabilityFactory()
    return _research_factory.handlers()
