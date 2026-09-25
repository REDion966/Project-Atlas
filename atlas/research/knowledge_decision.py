"""Atlas Research — Knowledge Decision / Conversation↔Knowledge integration (D3).

Deterministic, model-independent integration of the D1 Conversation Engine's
knowledge requirement with the EXISTING validated-knowledge retrieval and the
D2 controlled external acquisition boundary:

    knowledge requirement
      -> existing validated knowledge (ValidatedKnowledgeRetriever)
      -> sufficient?  -> answer from it (NO external acquisition)
      -> otherwise    -> D2 ExternalKnowledgeAcquirer (authorized only)
      -> re-read validated knowledge
      -> honest, bounded decision

Boundaries preserved:
  * no second knowledge store / research engine / planner / retriever;
  * external acquisition only through D2 (authorization enforced there);
  * external content is data, never authority;
  * deterministic, no model, no network unless D2 authorizes a host.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

_MAX_QUERY_CHARS: int = 400


class KnowledgeSufficiency(str, Enum):
    """Deterministic outcome of a knowledge decision."""

    SUFFICIENT = "sufficient"          # validated knowledge answers the request
    CONTRADICTORY = "contradictory"    # material conflicting evidence exists
    STALE = "stale"                    # relevant knowledge exists but not current
    INSUFFICIENT = "insufficient"      # not enough evidence to answer
    UNKNOWN = "unknown"                # sufficiency could not be established
    UNSUPPORTED = "unsupported"        # not a knowledge request / malformed


@dataclass(frozen=True, slots=True)
class KnowledgeAnswer:
    """Bounded, JSON-safe knowledge decision + answer material.

    Carries only EXISTING validated claims / provenance; it fabricates nothing
    and grants no authority.
    """

    status: KnowledgeSufficiency
    objective: str
    query: str = ""
    claims: tuple[dict[str, Any], ...] = ()
    sources: tuple[str, ...] = ()
    contradictions: bool = False
    freshness_required: bool = False
    acquisition_status: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "objective": self.objective,
            "query": self.query,
            "claims": [dict(c) for c in self.claims],
            "sources": list(self.sources),
            "contradictions": self.contradictions,
            "freshness_required": self.freshness_required,
            "acquisition_status": self.acquisition_status,
            "message": self.message,
        }


def _status_value(result: Any) -> str:
    status = getattr(result, "status", None)
    return str(getattr(status, "value", status) or "")


def _text(value: Any, limit: int = _MAX_QUERY_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


#: Deterministic freshness cue vocabulary (a bounded semantic rule, not a
#: per-phrase patch). A request carrying one of these asks for currency.
_FRESHNESS_CUES: frozenset[str] = frozenset(
    {
        "current", "currently", "latest", "recent", "recently", "now", "today",
        "still", "up-to-date", "status", "new", "newest", "updated",
    }
)


def required_freshness(text: str) -> bool:
    """True when the request deterministically asks for current information."""
    if not isinstance(text, str):
        return False
    tokens = {t.strip(".,?!;:'\"()") for t in text.lower().split()}
    return bool(tokens & _FRESHNESS_CUES) or "up to date" in text.lower()


class KnowledgeDecisionService:
    """Deterministic knowledge sufficiency + acquisition integration.

    Args:
        validated_retriever: The existing ``ValidatedKnowledgeRetriever``.
        external_acquirer: Optional D2 ``ExternalKnowledgeAcquirer``. When
            absent, no external acquisition is possible.
    """

    def __init__(
        self,
        *,
        validated_retriever: Any,
        external_acquirer: Any | None = None,
    ) -> None:
        self._retriever = validated_retriever
        self._acquirer = external_acquirer

    # ------------------------------------------------------------------
    # Conversation-facing local-first enrichment
    # ------------------------------------------------------------------

    def retrieve_with_acquisition(
        self,
        query: str,
        *,
        candidate_urls: Sequence[str] = (),
    ) -> Any | None:
        """Return validated knowledge for ``query``, acquiring only if needed.

        Local-first (mandatory): existing validated knowledge is returned with
        NO external acquisition. Only when the local store has nothing does the
        governed D2 boundary run; the store is then re-read. Returns the
        existing ``ValidatedKnowledgeResult`` or ``None`` (never fabricates).
        """
        existing = self._retrieve(query)
        if self._covers(existing):
            return existing
        if self._acquirer is None:
            return None
        try:
            self._acquirer.acquire(
                objective=query,
                candidate_urls=tuple(candidate_urls or ()),
                knowledge_query=query,
            )
        except Exception:  # fail closed
            return None
        refreshed = self._retrieve(query)
        return refreshed if self._covers(refreshed) else None

    # ------------------------------------------------------------------
    # Structured decision (API / tests)
    # ------------------------------------------------------------------

    def decide(
        self,
        objective: str,
        *,
        knowledge_query: str = "",
        candidate_urls: Sequence[str] = (),
        force_freshness: bool | None = None,
    ) -> KnowledgeAnswer:
        """Decide sufficiency and (only if needed) acquire; never fabricates."""
        objective_text = _text(objective)
        if not objective_text:
            return KnowledgeAnswer(
                status=KnowledgeSufficiency.UNSUPPORTED,
                objective="",
                message="A non-empty knowledge objective is required.",
            )
        query = _text(knowledge_query) or objective_text
        needs_current = (
            required_freshness(objective_text)
            if force_freshness is None
            else bool(force_freshness)
        )

        result = self._retrieve(query)
        items = self._items(result)
        if items and not needs_current:
            return self._sufficient(objective_text, query, result, needs_current, "")

        # Insufficient or stale -> governed D2 acquisition (if wired).
        if self._acquirer is None:
            return KnowledgeAnswer(
                status=(
                    KnowledgeSufficiency.STALE
                    if (items and needs_current)
                    else KnowledgeSufficiency.INSUFFICIENT
                ),
                objective=objective_text,
                query=query,
                freshness_required=needs_current,
                message="No external acquisition path is available.",
            )

        try:
            acquisition = self._acquirer.acquire(
                objective=objective_text,
                candidate_urls=tuple(candidate_urls or ()),
                knowledge_query=query,
            )
        except Exception:  # fail closed
            return KnowledgeAnswer(
                status=KnowledgeSufficiency.INSUFFICIENT,
                objective=objective_text,
                query=query,
                freshness_required=needs_current,
                acquisition_status="failed",
                message="Acquisition failed closed.",
            )

        acquisition_status = str(
            getattr(getattr(acquisition, "status", None), "value", "") or ""
        )
        if acquisition_status == "existing_knowledge":
            existing_result = getattr(acquisition, "existing", None) or result
            return self._sufficient(
                objective_text, query, existing_result, needs_current, acquisition_status
            )
        if acquisition_status != "acquired":
            return KnowledgeAnswer(
                status=(
                    KnowledgeSufficiency.STALE
                    if (items and needs_current)
                    else KnowledgeSufficiency.UNKNOWN
                ),
                objective=objective_text,
                query=query,
                freshness_required=needs_current,
                acquisition_status=acquisition_status,
                message=str(getattr(acquisition, "message", "") or ""),
            )

        refreshed = self._retrieve(query)
        findings = str(
            getattr(getattr(acquisition, "acquisition", None), "findings", "") or ""
        )
        if "CONTESTED" in findings.upper():
            return KnowledgeAnswer(
                status=KnowledgeSufficiency.CONTRADICTORY,
                objective=objective_text,
                query=query,
                claims=self._claims(refreshed),
                sources=self._sources(refreshed),
                contradictions=True,
                freshness_required=needs_current,
                acquisition_status=acquisition_status,
                message="Acquired evidence conflicts; the contradiction is preserved.",
            )
        if self._covers(refreshed):
            return self._sufficient(
                objective_text, query, refreshed, needs_current, acquisition_status
            )
        return KnowledgeAnswer(
            status=KnowledgeSufficiency.INSUFFICIENT,
            objective=objective_text,
            query=query,
            freshness_required=needs_current,
            acquisition_status=acquisition_status,
            message="Acquisition produced no validated knowledge (fail-closed).",
        )

    # ------------------------------------------------------------------
    # Internals (reuse existing result objects; invent nothing)
    # ------------------------------------------------------------------

    def _retrieve(self, query: str) -> Any | None:
        try:
            return self._retriever.retrieve(query)
        except Exception:  # fail closed -> treat as no knowledge
            return None

    @staticmethod
    def _items(result: Any) -> tuple[Any, ...]:
        items = getattr(result, "items", None)
        if not items:
            return ()
        try:
            return tuple(items)
        except TypeError:
            return ()

    def _covers(self, result: Any) -> bool:
        return _status_value(result) == "ok" and bool(self._items(result))

    @staticmethod
    def _claims(result: Any) -> tuple[dict[str, Any], ...]:
        out: list[dict[str, Any]] = []
        for item in KnowledgeDecisionService._items(result)[:3]:
            to_dict = getattr(item, "to_dict", None)
            if callable(to_dict):
                try:
                    out.append(dict(to_dict()))
                except Exception:  # pragma: no cover - defensive
                    continue
        return tuple(out)

    @staticmethod
    def _sources(result: Any) -> tuple[str, ...]:
        uris: list[str] = []
        for item in KnowledgeDecisionService._items(result):
            for citation in tuple(getattr(item, "citations", ()) or ()):
                uri = _text(getattr(citation, "source_uri", ""))
                if uri and uri not in uris:
                    uris.append(uri)
        return tuple(uris[:5])

    def _sufficient(
        self,
        objective: str,
        query: str,
        result: Any,
        needs_current: bool,
        acquisition_status: str,
    ) -> KnowledgeAnswer:
        return KnowledgeAnswer(
            status=KnowledgeSufficiency.SUFFICIENT,
            objective=objective,
            query=query,
            claims=self._claims(result),
            sources=self._sources(result),
            freshness_required=needs_current,
            acquisition_status=acquisition_status,
            message=(
                "Validated knowledge covers the request."
                if not acquisition_status
                else "Validated knowledge covers the request (via acquisition)."
            ),
        )
