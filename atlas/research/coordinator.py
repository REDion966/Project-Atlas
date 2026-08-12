"""Atlas Research — Concrete Research Coordinator (Phase 21).

Composes the existing Track A components into the first concrete
:class:`~atlas.evolution.research_coordinator.ResearchCoordinator`
implementation:

    ResearchQuery
      → ResearchPlanner.plan          (deterministic decomposition)
      → source resolver               (existing three-adaptor mechanism)
      → KnowledgeExtractor.extract    (claim extraction)
      → ClaimVerifier.verify          (cross-source verification)
      → ResearchReport
      → ResearchStorage (best-effort) + governed ResearchIngestBridge (fail-closed)

The coordinator is a composition ROOT only: every dependency is
constructor-injected and none of the Track A components are reimplemented
here. It implements the legacy abstract ``ResearchCoordinator`` contract
(``conduct_research`` / ``validate_findings``) with a synchronous core so
capability handlers can execute research without an event loop. The legacy
boundary model (:class:`~atlas.evolution.models.ResearchResult`) is the
return type; the modern :class:`~atlas.research.models.ResearchReport`
remains the internal working artifact. No duplicate research subsystem is
introduced.

Fail-soft conventions (repository-wide): any unexpected failure in a
research run degrades to a ``ResearchResult`` with ``confidence == 0.0``
and empty findings — it never raises into the caller. Storage writes and
governed ingestion are best-effort and must not break the research result.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from atlas.evolution.models import ResearchQuery, ResearchResult
from atlas.evolution.research_coordinator import ResearchCoordinator
from atlas.research.extractor import KnowledgeExtractor
from atlas.research.models import (
    ResearchPlan,
    ResearchReport,
    ResearchSource,
    SourceProfile,
)
from atlas.research.planner import ResearchPlanner
from atlas.research.verifier import ClaimVerifier

# A source resolver maps explicit source specs (URIs or source objects) to
# resolved ResearchSource / SourceProfile instances. The kernel injects the
# existing Track A resolution mechanism (ResearchCapabilityFactory._resolve_sources).
SourceResolver = Callable[[list], list]


def _default_resolver(specs: list) -> list:
    """Fallback resolver reusing the three Track A source adapters.

    Used only when the kernel does not inject the production resolver
    (isolated unit tests / standalone construction). Mirrors the existing
    Track A resolution mechanism without importing the capability layer.
    """
    from pathlib import Path

    from atlas.research.sources import (
        CodebaseSourceAdapter,
        DocumentSourceAdapter,
        WorkspaceSourceAdapter,
    )

    document = DocumentSourceAdapter()
    workspace = WorkspaceSourceAdapter(root=Path("."))
    codebase = CodebaseSourceAdapter()
    resolved: list = []
    if not isinstance(specs, list):
        return resolved
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
                else:
                    continue
                resolved.append(candidate)
            except (ValueError, OSError):
                continue
    return resolved


class ConcreteResearchCoordinator(ResearchCoordinator):
    """First concrete implementation of the legacy ResearchCoordinator ABC.

    Composes the existing Track A planner, extractor, verifier, storage and
    governed ingest bridge. All dependencies are injected; every component
    is reused, none are recreated or reimplemented.
    """

    def __init__(
        self,
        planner: ResearchPlanner | None = None,
        extractor: KnowledgeExtractor | None = None,
        verifier: ClaimVerifier | None = None,
        storage: Any | None = None,
        ingest: Any | None = None,
        resolve_sources: SourceResolver | None = None,
    ) -> None:
        """Initialise the coordinator with injected Track A components.

        Args:
            planner: Existing ResearchPlanner (defaults to a fresh one).
            extractor: Existing KnowledgeExtractor (defaults to a fresh one).
            verifier: Existing ClaimVerifier (defaults to a fresh one).
            storage: Optional ResearchStorage adapter (best-effort writes).
            ingest: Optional governed ResearchIngestBridge (fail-closed).
            resolve_sources: Optional resolver reusing the existing Track A
                source-adapter mechanism. Defaults to a standalone resolver.
        """
        self._planner = planner or ResearchPlanner()
        self._extractor = extractor or KnowledgeExtractor()
        self._verifier = verifier or ClaimVerifier()
        self._storage = storage
        self._ingest = ingest
        self._resolve_sources = resolve_sources or _default_resolver

    # ------------------------------------------------------------------
    # Public sync entry point (used by capability handlers)
    # ------------------------------------------------------------------

    def run(self, query: ResearchQuery | None) -> ResearchResult:
        """Execute the complete Track A research pipeline synchronously.

        Deterministic where the underlying Track A components are
        deterministic. Fail-soft: never raises; on any unexpected failure
        returns a ``ResearchResult`` with ``confidence == 0.0``.
        """
        if query is None or not str(getattr(query, "question", "") or "").strip():
            return ResearchResult(
                query_id=str(getattr(query, "query_id", "unknown")),
                findings="",
                sources=[],
                confidence=0.0,
                completed_at=datetime.now(),
            )

        try:
            plan: ResearchPlan = self._planner.plan(query)
            specs = self._query_source_specs(query)
            resolved = self._resolve_sources(specs)
            profiles = [s for s in resolved if isinstance(s, SourceProfile)]
            source_uris = [
                getattr(s, "uri", "")
                for s in resolved
                if isinstance(s, (ResearchSource, SourceProfile)) and getattr(s, "uri", "")
            ]

            claims = []
            for profile in profiles:
                claims.extend(self._extractor.extract(profile))

            verifications = self._verifier.verify(claims, profiles) if claims else []

            report = ResearchReport(
                report_id=f"report:{query.query_id}:{plan.plan_id}",
                plan_id=plan.plan_id,
                query_id=query.query_id,
                question=query.question,
                findings=self._build_findings(plan, verifications),
                claims=tuple(claims),
                verifications=tuple(verifications),
                confidence=(
                    sum(v.score for v in verifications) / len(verifications)
                    if verifications
                    else 0.0
                ),
                metadata={"target_sources": [k.name for k in plan.target_sources]},
            )

            self._persist_report(report)
            self._submit_governed_ingest(report)

            return ResearchResult(
                query_id=query.query_id,
                findings=report.findings,
                sources=list(source_uris),
                confidence=report.confidence,
                completed_at=datetime.now(),
            )
        except Exception:
            # Fail-soft: 0.0-confidence result, never a raised exception.
            return ResearchResult(
                query_id=str(getattr(query, "query_id", "unknown")),
                findings="",
                sources=[],
                confidence=0.0,
                completed_at=datetime.now(),
            )

    # ------------------------------------------------------------------
    # Legacy abstract contract (async wrappers over the sync core)
    # ------------------------------------------------------------------

    async def conduct_research(self, query: ResearchQuery) -> ResearchResult:
        """ABC-compliant async research entry point (delegates to run)."""
        return self.run(query)

    async def validate_findings(self, result: ResearchResult | None) -> float:
        """ABC-compliant findings validation: report confidence (never raises)."""
        if result is None:
            return 0.0
        try:
            return float(getattr(result, "confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    # ------------------------------------------------------------------
    # Composition introspection (tests / diagnostics)
    # ------------------------------------------------------------------

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
    def storage(self):
        return self._storage

    @property
    def ingest(self):
        return self._ingest

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _query_source_specs(query: ResearchQuery) -> list:
        """Source specs from the query context (``context["sources"]``)."""
        context = getattr(query, "context", None) or {}
        specs = context.get("sources", []) if isinstance(context, dict) else []
        return specs if isinstance(specs, list) else []

    @staticmethod
    def _build_findings(plan: ResearchPlan, verifications) -> str:
        """Deterministic findings text (verification outcome tally)."""
        outcomes: dict[str, int] = {}
        for v in verifications:
            label = getattr(v, "metadata", {}).get("outcome", v.status.name)
            outcomes[label] = outcomes.get(label, 0) + 1
        parts = [f"{k}={n}" for k, n in sorted(outcomes.items())]
        return "verification summary: " + (", ".join(parts) if parts else "no claims verified")

    def _persist_report(self, report: ResearchReport) -> None:
        """Best-effort report persistence into the injected storage."""
        storage = self._storage
        if storage is None:
            return
        try:
            if not storage.is_available():
                return
            storage.store_report(report)
        except Exception:
            pass

    def _submit_governed_ingest(self, report: ResearchReport) -> None:
        """Submit the report through the governed ingest bridge (fail-closed).

        The bridge is intentionally governed: without a wired sink it
        refuses (accepted=False) and the refusal is recorded, never
        bypassed. Batch 1+2 does not depend on ingestion succeeding.
        """
        ingest = self._ingest
        if ingest is None:
            return
        try:
            if not getattr(ingest, "has_sink", False):
                return
            ingest.ingest(report)
        except Exception:
            pass

    def __repr__(self) -> str:
        return (
            f"ConcreteResearchCoordinator("
            f"planner={type(self._planner).__name__}, "
            f"extractor={type(self._extractor).__name__}, "
            f"verifier={type(self._verifier).__name__}, "
            f"storage={type(self._storage).__name__ if self._storage else None}, "
            f"ingest={type(self._ingest).__name__ if self._ingest else None})"
        )
