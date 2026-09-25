"""Atlas Research — External Knowledge Acquisition (D2).

A thin, deterministic, model-independent composition service that gives Atlas
*controlled* access to external information, reusing the EXISTING C6 pipeline
end to end:

    knowledge objective
      -> existing validated-knowledge sufficiency check (ValidatedKnowledgeRetriever)
      -> authorized external source selection (existing WebHostPolicy, deny-by-default)
      -> existing InformationAcquisitionService
      -> existing ResearchPlanner / SourceAdapter (WebSourceAdapter)
      -> existing KnowledgeExtractor / ClaimVerifier
      -> existing ResearchSQLiteStorage + governed ingest
      -> bounded ExternalAcquisitionResult

ARCHITECTURAL BOUNDARY:
  * no second web client / source adapter / database / citation / verifier /
    retriever / freshness system — every component is reused.
  * authorization is enforced AT THE ADAPTER (``WebSourceAdapter`` host policy);
    this service only FILTERS candidate URLs against that same policy so a
    caller can never claim "this source is authorized" and bypass it.
  * deny-by-default: with no allowlist entry, no host is fetchable.
  * external content is DATA, never instructions and never authority. Nothing
    here approves, authorizes, executes, promotes, or self-modifies.
  * no AI requirement: the whole path is deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from atlas.research.sources.web import DENY_ALL_HOSTS, WebHostPolicy, WebSourceAdapter

_MAX_OBJECTIVE_CHARS: int = 400
_DEFAULT_MAX_SOURCES: int = 5


class ExternalAcquisitionStatus(str, Enum):
    """Outcome of one controlled external-knowledge acquisition request."""

    EXISTING_KNOWLEDGE = "existing_knowledge"  # existing validated knowledge suffices
    ACQUIRED = "acquired"                      # external evidence acquired + validated
    NO_AUTHORIZED_SOURCE = "no_authorized_source"  # deny-by-default / all candidates denied
    FAILED = "failed"                          # nothing usable acquired (fail-closed)


@dataclass(frozen=True, slots=True)
class ExternalAcquisitionResult:
    """Bounded, deterministic result of one external-knowledge acquisition.

    ``acquisition`` and ``existing`` are the EXISTING Atlas result objects
    (``AcquisitionResult`` / ``ValidatedKnowledgeResult``) — this service
    introduces no second result schema beyond this thin envelope.
    """

    status: ExternalAcquisitionStatus
    objective: str
    knowledge_query: str = ""
    authorized_sources: tuple[str, ...] = ()
    denied_sources: tuple[str, ...] = ()
    acquisition: Any | None = None
    existing: Any | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict (delegates to existing result dicts)."""
        acquisition = self.acquisition
        existing = self.existing
        return {
            "status": self.status.value,
            "objective": self.objective,
            "knowledge_query": self.knowledge_query,
            "authorized_sources": list(self.authorized_sources),
            "denied_sources": list(self.denied_sources),
            "message": self.message,
            "acquisition": (
                acquisition.to_dict() if hasattr(acquisition, "to_dict") else None
            ),
            "existing": existing.to_dict() if hasattr(existing, "to_dict") else None,
        }


class ExternalKnowledgeAcquirer:
    """Controlled external-knowledge acquisition over the existing pipeline.

    Args:
        acquisition_service: The existing ``InformationAcquisitionService``.
        validated_retriever: Optional existing ``ValidatedKnowledgeRetriever``
            used for the sufficiency pre-check (skip acquisition when validated
            knowledge already covers the objective).
        host_policy: The existing ``WebHostPolicy``. Defaults to
            ``DENY_ALL_HOSTS`` (no host fetchable).
        max_sources: Bound on authorized candidate sources per request.
    """

    def __init__(
        self,
        *,
        acquisition_service: Any,
        validated_retriever: Any | None = None,
        host_policy: WebHostPolicy | None = None,
        max_sources: int = _DEFAULT_MAX_SOURCES,
    ) -> None:
        if max_sources < 1:
            raise ValueError("max_sources must be >= 1")
        self._acquisition = acquisition_service
        self._retriever = validated_retriever
        self._host_policy: WebHostPolicy = host_policy or DENY_ALL_HOSTS
        self._max_sources = max_sources
        # The web adapter is the single authoritative authorization boundary.
        # ``supports`` performs no I/O (no DNS), so this is a pure policy check.
        self._adapter = WebSourceAdapter(host_policy=self._host_policy)

    @property
    def host_policy(self) -> WebHostPolicy:
        """The applied (read-only) host authorization policy."""
        return self._host_policy

    def authorize(self, urls: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Split candidate URLs into ``(authorized, denied)`` via the adapter policy.

        Deterministic; I/O-free; never raises. Non-string/blank entries are
        ignored. A denied URL is one the authoritative web adapter would refuse
        (deny-by-default, SSRF/IP-blocked, credential-bearing, non-http(s)).
        """
        authorized: list[str] = []
        denied: list[str] = []
        for url in urls or ():
            if not isinstance(url, str):
                continue
            candidate = url.strip()
            if not candidate or candidate in authorized or candidate in denied:
                continue
            try:
                permitted = bool(self._adapter.supports(candidate))
            except Exception:  # fail closed on any policy error
                permitted = False
            (authorized if permitted else denied).append(candidate)
            if len(authorized) >= self._max_sources:
                break
        return tuple(authorized), tuple(denied)

    def acquire(
        self,
        objective: str,
        *,
        candidate_urls: Sequence[str] = (),
        knowledge_query: str = "",
    ) -> ExternalAcquisitionResult:
        """Acquire external knowledge for ``objective`` when knowledge is absent.

        Order: existing validated knowledge -> authorized external sources ->
        existing acquisition pipeline. Never fabricates and never raises.
        """
        objective_text = (
            objective.strip()[:_MAX_OBJECTIVE_CHARS]
            if isinstance(objective, str)
            else ""
        )
        if not objective_text:
            return ExternalAcquisitionResult(
                status=ExternalAcquisitionStatus.FAILED,
                objective="",
                message="A non-empty knowledge objective is required.",
            )
        query = (
            knowledge_query.strip()[:_MAX_OBJECTIVE_CHARS]
            if isinstance(knowledge_query, str) and knowledge_query.strip()
            else objective_text
        )

        existing = self._retrieve_existing(query)
        if existing is not None and self._covers(existing):
            return ExternalAcquisitionResult(
                status=ExternalAcquisitionStatus.EXISTING_KNOWLEDGE,
                objective=objective_text,
                knowledge_query=query,
                existing=existing,
                message=(
                    "Existing validated knowledge covers the objective; no "
                    "external acquisition was performed."
                ),
            )

        authorized, denied = self.authorize(candidate_urls)
        if not authorized:
            return ExternalAcquisitionResult(
                status=ExternalAcquisitionStatus.NO_AUTHORIZED_SOURCE,
                objective=objective_text,
                knowledge_query=query,
                denied_sources=denied,
                existing=existing,
                message=(
                    "No authorized external source is available "
                    "(deny-by-default). No external content was acquired."
                ),
            )
        if self._acquisition is None:
            return ExternalAcquisitionResult(
                status=ExternalAcquisitionStatus.FAILED,
                objective=objective_text,
                knowledge_query=query,
                authorized_sources=authorized,
                denied_sources=denied,
                message="No acquisition service is wired.",
            )

        try:
            result = self._acquisition.acquire(
                question=objective_text, sources=tuple(authorized)
            )
        except Exception as exc:  # fail closed; never fabricate
            return ExternalAcquisitionResult(
                status=ExternalAcquisitionStatus.FAILED,
                objective=objective_text,
                knowledge_query=query,
                authorized_sources=authorized,
                denied_sources=denied,
                message=f"Acquisition failed closed: {type(exc).__name__}.",
            )

        acquired = (
            getattr(result, "status", "") in ("ok", "partial")
            and bool(getattr(result, "sources", ()))
        )
        return ExternalAcquisitionResult(
            status=(
                ExternalAcquisitionStatus.ACQUIRED
                if acquired
                else ExternalAcquisitionStatus.FAILED
            ),
            objective=objective_text,
            knowledge_query=query,
            authorized_sources=authorized,
            denied_sources=denied,
            acquisition=result,
            message=(
                "External evidence acquired and processed through the existing "
                "evidence/validation pipeline."
                if acquired
                else "External acquisition produced no usable evidence (fail-closed)."
            ),
        )

    def acquire_for_intake(
        self,
        semantic: Any,
        *,
        candidate_urls: Sequence[str] = (),
        knowledge_query: str = "",
    ) -> ExternalAcquisitionResult:
        """Acquire for a D1 ``SemanticIntake`` knowledge requirement.

        Consumes the structured D1 semantic boundary (``required_knowledge`` /
        ``requested_information`` / ``objective``) instead of raw text, so the
        acquisition layer never depends on conversational phrasing.
        """
        objective = self._objective_from_intake(semantic)
        return self.acquire(
            objective,
            candidate_urls=candidate_urls,
            knowledge_query=knowledge_query,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _objective_from_intake(semantic: Any) -> str:
        for attr in ("required_knowledge", "requested_information", "objective"):
            value = getattr(semantic, attr, None)
            if isinstance(value, (list, tuple)) and value:
                first = value[0]
                if isinstance(first, str) and first.strip():
                    return first.strip()
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _retrieve_existing(self, query: str) -> Any | None:
        if self._retriever is None:
            return None
        try:
            return self._retriever.retrieve(query)
        except Exception:  # fail closed -> treat as no existing knowledge
            return None

    @staticmethod
    def _covers(existing: Any) -> bool:
        status = getattr(existing, "status", None)
        value = getattr(status, "value", status)
        return value == "ok" and bool(getattr(existing, "items", ()))
