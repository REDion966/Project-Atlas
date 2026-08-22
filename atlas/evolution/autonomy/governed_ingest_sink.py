"""Atlas Evolution Autonomy — GovernanceIngestSink — Foundation Strengthening Batch 12.

Concrete governed ingest sink shared by all four track ingest bridges
(Research, Toolchain, LongTerm, Advanced Reasoning).

The bridge modules already declare structurally identical ``*IngestSink``
protocols (``enqueue_request(EvolutionRequest) -> IngestHandoffResult``).
This single implementation satisfies all four protocols by persisting each
bridge-produced ``EvolutionRequest`` as a DRAFTED record in the existing
kernel-owned ``ScheduleStore``.

RESPONSIBILITIES (only): persist governed requests.
- ``enqueue_request`` performs a structural safety check (non-None request,
  non-empty request_id/source, supported state scope), deduplicates by
  request_id via ``ScheduleStore.get_request``, and persists via
  ``ScheduleStore.create_request(...)`` as DRAFTED.
- ``to_applier_entries`` is a pure, deterministic translation helper for the
  future application/dispatch boundary. It converts the flat validator-form
  payload (``operation``/``entry_id``/``domain``/``content``/...) into the
  applier ``entries: [...]`` form. The PERSISTED request always retains the
  original flat payload; this helper never alters stored state.

HARD BOUNDARY — this sink:
- NEVER calls Validator, RiskAssessor, AuthorizationManager.
- NEVER calls authorize_autonomously().
- NEVER calls ApplicationEngine.apply().
- NEVER executes, approves, or authorizes anything.
- Fails closed on every invalid or storage-error path.

Pure logic except for the injected ScheduleStore. No AI. No async.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlas.evolution.autonomy.models import EvolutionRequest
from atlas.evolution.autonomy.schedule_store import ScheduleStore
from atlas.evolution.governance.models import ScopeType

#: Scopes an ingest may persist. CONFIG/CAPABILITY are intentionally absent:
#: CONFIG mutation is staged-config-governed; CAPABILITY registration must go
#: through the registry's own governance. These stay fail-closed.
_INGESTABLE_SCOPES: frozenset[ScopeType] = frozenset(
    {ScopeType.MEMORY, ScopeType.KNOWLEDGE}
)


@dataclass(slots=True)
class IngestHandoffResult:
    """Outcome of handing a governed request to the sink.

    Structurally identical to the per-bridge ``IngestHandoffResult`` classes
    (``accepted`` / ``request_id`` / ``error``) so bridges can duck-type it.
    """

    accepted: bool
    request_id: str = ""
    error: str = ""


class GovernanceIngestSink:
    """Persists bridge-produced EvolutionRequests as DRAFTED via ScheduleStore.

    One kernel-private instance is shared by all four ingest bridges.
    """

    def __init__(
        self,
        schedule_store: ScheduleStore,
    ) -> None:
        if schedule_store is None:
            raise ValueError("ScheduleStore is required")
        self._schedule_store = schedule_store

    @property
    def schedule_store(self) -> ScheduleStore:
        """The underlying request-lifecycle store."""
        return self._schedule_store

    # ------------------------------------------------------------------
    # Protocol entry point (satisfies all four *IngestSink protocols)
    # ------------------------------------------------------------------

    def enqueue_request(self, request: EvolutionRequest) -> IngestHandoffResult:
        """Persist ``request`` as DRAFTED; fail closed on any invalid input.

        Steps:
          1. Structural safety check (None / missing id / missing source /
             unsupported scope) → fail closed.
          2. Idempotency: if a request with the same request_id already
             exists, return accepted=False (no duplicate write).
          3. Persist via ``ScheduleStore.create_request`` as DRAFTED.
          4. Return an accepted handoff with the request_id.

        Never raises: all storage failures are caught and returned as a
        failed handoff.
        """
        if request is None:
            return IngestHandoffResult(accepted=False, error="request is None")
        request_id = getattr(request, "request_id", "") or ""
        source = getattr(request, "source", "") or ""
        if not request_id:
            return IngestHandoffResult(accepted=False, error="request_id is missing")
        if not source:
            return IngestHandoffResult(
                accepted=False,
                request_id=request_id,
                error="request source is missing",
            )
        if request.target_scope not in _INGESTABLE_SCOPES:
            return IngestHandoffResult(
                accepted=False,
                request_id=request_id,
                error=(
                    f"Scope {request.target_scope.name} is not ingestable "
                    "by the governed sink (fail closed)"
                ),
            )

        # Idempotency guard by request_id.
        try:
            existing = self._schedule_store.get_request(request_id)
        except Exception as exc:  # pragma: no cover - storage failure path
            return IngestHandoffResult(
                accepted=False,
                request_id=request_id,
                error=f"schedule store read failed: {exc}",
            )
        if existing is not None:
            return IngestHandoffResult(
                accepted=False,
                request_id=request_id,
                error="duplicate request already persisted",
            )

        # Persist as DRAFTED. Store stays the single lifecycle boundary.
        try:
            self._schedule_store.create_request(
                request_id=request_id,
                source=source,
                target_scope=request.target_scope,
                change_payload=request.change_payload,
                intended_level=request.intended_level,
                version_target=request.version_target,
            )
        except Exception as exc:
            return IngestHandoffResult(
                accepted=False,
                request_id=request_id,
                error=f"schedule store persistence failed: {exc}",
            )

        return IngestHandoffResult(
            accepted=True,
            request_id=request_id,
            error="",
        )

    # ------------------------------------------------------------------
    # Pure translation helper (future application/dispatch boundary)
    # ------------------------------------------------------------------

    @staticmethod
    def to_applier_entries(request: EvolutionRequest) -> dict[str, Any]:
        """Translate a flat validator-form request into applier entry form.

        Deterministic pure function. For:
        - KNOWLEDGE: ``{"entries": [{"knowledge_key": entry_id, ...}]}``
        - MEMORY:    ``{"entries": [{"memory_id": entry_id, ...}]}``

        The stored request payload is NEVER modified; this helper exists only
        so the future dispatcher can shape a request for
        ``ApplicationEngine.apply()``. It does not duplicate Validator rules.
        """
        payload = request.change_payload or {}
        scope = request.target_scope
        entry_id = str(payload.get("entry_id", ""))
        content = payload.get("content", "")

        if scope == ScopeType.MEMORY:
            entry: dict[str, Any] = {"memory_id": entry_id}
            if content:
                entry["content"] = content
            return {"entries": [entry]}

        entry = {"knowledge_key": entry_id}
        if content:
            entry["content"] = content
        if payload.get("confidence") is not None:
            entry["confidence"] = payload["confidence"]
        return {"entries": [entry]}
