"""Atlas Research — Storage Protocol (Phase 17.6).

Pure interfaces for research persistence. Implemented by
:class:`~atlas.storage.research_storage.ResearchSQLiteStorage`.

Persistence ONLY: sources, claims, verifications, citations, reports.
No business logic. No gateway. No kernel.
"""

from typing import Protocol, runtime_checkable

from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    ResearchReport,
    ResearchSource,
)


@runtime_checkable
class ResearchStorage(Protocol):
    """Persistence surface for Track A research artifacts."""

    # -- lifecycle ---------------------------------------------------------

    def initialize(self) -> None: ...

    def close(self) -> None: ...

    def is_available(self) -> bool: ...

    # -- sources (append-only) --------------------------------------------

    def store_source(self, source: ResearchSource) -> None: ...

    def load_sources(self) -> list[ResearchSource]: ...

    # -- claims (idempotent upsert) ----------------------------------------

    def store_claim(self, claim: KnowledgeClaim) -> None: ...

    def load_claims(self) -> list[KnowledgeClaim]: ...

    # -- verifications (append-only log) -----------------------------------

    def store_verification(self, verification: ClaimVerification) -> None: ...

    def load_verifications(self) -> list[ClaimVerification]: ...

    # -- citations (idempotent upsert per record id) -----------------------

    def store_citation(self, citation: CitationRecord) -> None: ...

    def load_citations(self) -> list[CitationRecord]: ...

    # -- reports (append-only log) -----------------------------------------

    def store_report(self, report: ResearchReport) -> None: ...

    def load_reports(self) -> list[ResearchReport]: ...


@runtime_checkable
class ResearchIngestDispatcher(Protocol):
    """The single hand-off point from Track A to the Phase 16 mutation path.

    Track A never calls the execution gateway directly (Phase 16 binding
    constraint: ``EvolutionAutonomyDispatcher`` is the sole caller of
    ``gateway.execute_request()``). Research results are instead handed to
    this protocol; the kernel will wire the real implementation to the
    Phase 16 ``ScheduleStore``/dispatcher queue so the request is enqueued
    and applied only through governed evolution.
    """

    def enqueue_request(self, request_id: str) -> "IngestHandoffResult": ...


class IngestHandoffResult:
    """Result of handing a research evolution request to the dispatcher."""

    __slots__ = ("accepted", "request_id", "error")

    def __init__(self, accepted: bool, request_id: str = "", error: str = "") -> None:
        self.accepted = accepted
        self.request_id = request_id
        self.error = error
