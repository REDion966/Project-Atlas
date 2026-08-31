"""Atlas Collective — CollectiveGovernance (P4).

Implements the P4 collective-learning pipeline:

  Interaction record (principal-scoped)
    → CollectiveCandidate (bounded, provenance-preserving, CANDIDATE)
    → Governance approval (ApprovalManager, OWNER-only)
    → CollectiveKnowledge (APPROVED, advisory only)

Design contract:
  * A candidate can be produced by any principal but can NEVER self-promote.
    Promotion calls ``AuthorityService.check(principal_id, OWNER)`` and
    ``ApprovalManager.approve`` — a User is always rejected (fail-closed).
  * Provenance is immutable and carried verbatim across candidate → collective.
    Promotion changes the status (CANDIDATE → APPROVED/REJECTED), never the
    originating principal_id/authority/session provenance.
  * Only bounded, structured summaries are carried into candidates/collective;
    raw conversational text is never promoted.
  * No schema change, no migration, no RuntimeCoordinator/Atlas.tick() touch.
  * No direct tool/capability/orchestration/dev/governance execution — the
    collective layer is advisory context.

Pure logic. No storage, no AI, no runtime, no kernel.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from atlas.authority.models import AuthorityLevel
from atlas.collective.models import (
    CollectiveCandidate,
    CollectiveKind,
    CollectiveKnowledge,
    CollectiveProvenance,
    CollectiveStatus,
)
from atlas.collective.repository import CollectiveRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bounded_text(value: Any, limit: int) -> str:
    """Return a bounded, control-free string, or '' for non-strings."""
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


_CONTROL_CHARS: set[str] = {chr(i) for i in range(0x20)} | {chr(0x7F)}


def _strip_controls(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    stripped = "".join(ch for ch in value if ch not in _CONTROL_CHARS)
    return stripped.strip()[:limit]


class CollectiveGovernance:
    """Candidate extraction + governed promotion for collective learning.

    Args:
        repository: The bounded collective store to operate against.
        authority_service: The real ``AuthorityService`` (OWNER/User boundary).
        approval_manager: The real ``ApprovalManager`` (existing pipeline).
        evolution_memory: Optional ``EvolutionMemory`` for candidacy audit.
    """

    def __init__(
        self,
        repository: CollectiveRepository | None = None,
        authority_service: Any | None = None,
        approval_manager: Any | None = None,
        evolution_memory: Any | None = None,
    ) -> None:
        if not isinstance(repository, CollectiveRepository):
            raise ValueError("repository must be a CollectiveRepository (fail-closed)")
        self._repository = repository
        self._authority = authority_service
        self._approval = approval_manager
        self._evolution = evolution_memory
        self._candidate_counter = 0
        self._collective_counter = 0
        self._pending_approvals: dict[str, Any] = {}
        # De-duplication against the originating B3.1 record id.
        self._seen_source_records: set[str] = set()
        self._seen_knowledge_keys: set[str] = set()

    @property
    def repository(self) -> CollectiveRepository:
        return self._repository

    # ------------------------------------------------------------------
    # Candidate extraction (deterministic, bounded, eligible-only)
    # ------------------------------------------------------------------

    def extract_candidates(self, records: list[Any] | None) -> list[CollectiveCandidate]:
        """Extract bounded candidates from B3.1 PreferenceRecord / CorrectionRecord.

        Deterministic heuristic: a record is eligible only when its structured
        fields are present and look potentially reusable (hard-bounded length,
        basic sanity). The record's provenance is carried verbatim. Rejected
        and duplicate source-record ids are skipped (both signal a non-retry-
        worthy extraction). Returns a bounded list; never raises.

        Args:
            records: A list of PreferenceRecord or CorrectionRecord objects.

        Returns:
            The extracted CollectiveCandidate list (bounded, deterministic).
        """
        if not records or not isinstance(records, (list, tuple)):
            return []
        candidates: list[CollectiveCandidate] = []
        for record in records:
            if record is None:
                continue
            kind = self._detect_kind(record)
            if kind is None:
                continue
            source_id = getattr(record, "record_id", "")
            if not isinstance(source_id, str) or not source_id:
                continue
            if source_id in self._seen_source_records:
                continue
            provenance = self._provenance_from_record(record)
            if provenance is None:
                continue
            payload = self._payload_from_record(record, kind)
            if payload is None:
                continue
            key, value, description, evidence = payload
            # Collective key de-duplication (same key → same approved shape).
            collective_key = f"{kind.value}:{key}:{value[:120]}"
            if collective_key in self._seen_knowledge_keys:
                continue
            self._candidate_counter += 1
            candidate_id = f"COLL-C-{self._candidate_counter:08d}"
            candidate = CollectiveCandidate(
                candidate_id=candidate_id,
                kind=kind,
                key=key,
                value=value,
                description=description,
                evidence=evidence,
                provenance=provenance,
                source_record_id=source_id,
            )
            # Pre-store the pending approval entry so the governance surface
            # can be queried without touching the global proposal store.
            self._repository.store_candidate(candidate)
            self._seen_source_records.add(source_id)
            self._seen_knowledge_keys.add(collective_key)
            candidates.append(candidate)
        return candidates

    # ------------------------------------------------------------------
    # Governance approval — candidate → approved/rejected collective
    # ------------------------------------------------------------------

    def _check_owner_authority(self, principal_id: str, action: str = "collective_promote") -> bool:
        """Return True only when principal holds OWNER authority (fail-closed)."""
        if self._authority is None:
            return False
        try:
            decision = self._authority.check(principal_id, AuthorityLevel.OWNER, action)
        except Exception:
            return False
        return bool(getattr(decision, "allowed", False))

    def _audit(self, event_type: str, description: str, related_ids: list[str], metadata: dict[str, Any]) -> None:
        """Record a governance audit entry via EvolutionMemory (best-effort)."""
        if self._evolution is None or not hasattr(self._evolution, "store_record"):
            return
        try:
            from atlas.evolution.models import EvolutionRecord
            record = EvolutionRecord(
                record_id=f"coll-{event_type}-{_utc_now().microsecond:06d}",
                event_type=event_type,
                description=description,
                related_ids=list(related_ids)[:12],
                metadata=dict(metadata),
            )
            self._evolution.store_record(record)
        except Exception:
            pass

    def create_approval_request(self, candidate: CollectiveCandidate) -> Any | None:
        """Create a pending ApprovalRequest for a candidate's promotion.

        The candidate must exist in the CANDIDATE store. The returned
        ApprovalRequest is tracked locally by id; callers should then invoke
        approve/reject against it. Returns None (fail-closed) when the
        candidate is unknown.

        Args:
            candidate: The candidate to request promotion for.

        Returns:
            The pending ApprovalRequest, or None.
        """
        if candidate is None or not isinstance(candidate, CollectiveCandidate):
            return None
        stored = self._repository.get_candidate(candidate.candidate_id)
        if stored is None:
            return None
        if self._approval is None or not hasattr(self._approval, "create_approval_request"):
            return None
        try:
            from atlas.evolution.models import EvolutionProposal, ImprovementPlan
            proposal = EvolutionProposal(
                proposal_id=f"COLL-{candidate.candidate_id}",
                title=f"Collective learning: {candidate.key[:80]}",
                summary=candidate.description[:400],
                rationale=candidate.evidence[:400],
                expected_benefit=candidate.value[:400],
                risks="Bounded advisory collective knowledge; never executable.",
                impact_analysis=f"Candidate {candidate.candidate_id} across principals",
                implementation_approach="CollectiveGovernance approve/reject through existing pipeline",
                plan=ImprovementPlan(
                    plan_id=f"plan-{candidate.candidate_id}",
                    title=candidate.key[:80],
                    description=candidate.description[:400],
                    priority=candidate.provenance.authority,
                    weaknesses=[],
                    expected_benefit=candidate.value[:400],
                    complexity_estimate="low",
                    target_components=["knowledge"],
                ),
            )
        except Exception:
            return None
        try:
            request = self._approval.create_approval_request(proposal)
        except Exception:
            return None
        self._pending_approvals[request.request_id] = (candidate, proposal, request)
        # EvolutionMemory sees the audit trail (best-effort).
        self._audit(
            "collective_candidate_submit",
            f"candidate {candidate.candidate_id} submitted (principal {candidate.provenance.principal_id})",
            [candidate.candidate_id, request.request_id],
            {"candidate_id": candidate.candidate_id, "status": "pending_approval"},
        )
        return request

    def approve(
        self,
        request: Any,
        approving_principal_id: str,
    ) -> CollectiveKnowledge | None:
        """Approve a pending promotion — OWNER authority required (fail-closed).

        Args:
            request: The pending ApprovalRequest previously returned by
                ``create_approval_request``.
            approving_principal_id: The acting approver (must hold OWNER).

        Returns:
            The approved CollectiveKnowledge when governance passes, else None.
        """
        if request is None or not hasattr(request, "request_id"):
            return None
        if not isinstance(approving_principal_id, str) or not approving_principal_id.strip():
            return None
        approving_principal_id = approving_principal_id.strip()
        if not self._check_owner_authority(approving_principal_id, "collective_promote:approve"):
            self._audit(
                "collective_promote_denied",
                f"approve of {request.request_id} denied for {approving_principal_id}",
                [request.request_id, approving_principal_id],
                {"reason": "requires_owner"},
            )
            return None
        pending = self._pending_approvals.get(request.request_id)
        if pending is None:
            return None
        candidate, proposal, tracked_request = pending
        if self._approval is None or not hasattr(self._approval, "approve"):
            return None
        try:
            self._approval.approve(tracked_request, comment=f"collective approve by {approving_principal_id}")
            self._approval.update_proposal_from_decision(proposal, tracked_request)
        except Exception:
            return None
        # Persist through EvolutionMemory (second source of durable audit).
        try:
            if self._evolution is not None:
                if hasattr(self._evolution, "store_proposal"):
                    self._evolution.store_proposal(proposal)
                if hasattr(self._evolution, "update_approval_request"):
                    self._evolution.update_approval_request(tracked_request)
                elif hasattr(self._evolution, "store_approval_request"):
                    self._evolution.store_approval_request(tracked_request)
        except Exception:
            pass
        # Candidate → collective. Remove from candidate, produce the
        # APPROVED collective record (provenance carried verbatim).
        self._repository.remove_candidate(candidate.candidate_id)
        del self._pending_approvals[request.request_id]
        knowledge = self._knowledge_from_candidate(candidate, approving_principal_id)
        self._repository.store_collective(knowledge)
        self._audit(
            "collective_approved",
            f"collective {knowledge.knowledge_id} approved by {approving_principal_id}",
            [candidate.candidate_id, knowledge.knowledge_id, approving_principal_id],
            {
                "candidate_id": candidate.candidate_id,
                "knowledge_id": knowledge.knowledge_id,
                "approved_by": approving_principal_id,
            },
        )
        return knowledge

    def reject(
        self,
        request: Any,
        approving_principal_id: str,
        reason: str = "",
    ) -> bool:
        """Reject a pending promotion — OWNER authority required (fail-closed).

        Args:
            request: The pending ApprovalRequest.
            approving_principal_id: The acting approver (must hold OWNER).
            reason: Optional rejection reason.

        Returns:
            True when rejection succeeded, False otherwise.
        """
        if request is None or not hasattr(request, "request_id"):
            return False
        if not isinstance(approving_principal_id, str) or not approving_principal_id.strip():
            return False
        approving_principal_id = approving_principal_id.strip()
        if not self._check_owner_authority(approving_principal_id, "collective_promote:reject"):
            self._audit(
                "collective_promote_denied",
                f"reject of {request.request_id} denied for {approving_principal_id}",
                [request.request_id, approving_principal_id],
                {"reason": "requires_owner"},
            )
            return False
        pending = self._pending_approvals.get(request.request_id)
        if pending is None:
            return False
        candidate, proposal, tracked_request = pending
        if self._approval is None or not hasattr(self._approval, "reject"):
            return False
        try:
            self._approval.reject(tracked_request, reason or "collective candidate rejected")
            self._approval.update_proposal_from_decision(proposal, tracked_request)
        except Exception:
            return False
        try:
            if self._evolution is not None:
                if hasattr(self._evolution, "store_proposal"):
                    self._evolution.store_proposal(proposal)
                if hasattr(self._evolution, "update_approval_request"):
                    self._evolution.update_approval_request(tracked_request)
                elif hasattr(self._evolution, "store_approval_request"):
                    self._evolution.store_approval_request(tracked_request)
        except Exception:
            pass
        removed = self._repository.remove_candidate(candidate.candidate_id)
        if removed is None:
            return False
        del self._pending_approvals[request.request_id]
        # Preserve for deduplication/audit, still emerging as REJECTED (never APPROVED).
        rejected = CollectiveCandidate(
            candidate_id=removed.candidate_id,
            kind=removed.kind,
            key=removed.key,
            value=removed.value,
            description=removed.description,
            evidence=removed.evidence,
            provenance=removed.provenance,
            source_record_id=removed.source_record_id,
            status=CollectiveStatus.REJECTED,
            created_at=removed.created_at,
            metadata=dict(removed.metadata),
        )
        self._repository.store_rejected(rejected)
        self._audit(
            "collective_rejected",
            f"candidate {candidate.candidate_id} rejected by {approving_principal_id}",
            [candidate.candidate_id, approving_principal_id],
            {"candidate_id": candidate.candidate_id, "reason": reason or "rejected"},
        )
        return True

    # ------------------------------------------------------------------
    # Consumption (advisory, bounded, knowledge only)
    # ------------------------------------------------------------------

    def collective_context(self, principal_id: str | None = None, n: int = 20) -> dict[str, Any]:
        """Return bounded, JSON-safe collective knowledge for advisory use.

        Collective knowledge is approval-gated: callers with no approval never see
        it. The result is bounded and excludes raw provenance identifiers beyond
        the already-public collective record fields. Rejected and CANDIDATE
        records are never included.

        Returns:
            A bounded dict with the approved collective knowledge list.
        """
        entries = self._repository.get_collective(n=max(1, min(n, 50)))
        items: list[dict[str, Any]] = []
        for rec in entries:
            items.append({
                "collective_kind": rec.kind.value,
                "collective_key": rec.key,
                "collective_value": rec.value[:200],
                "collective_description": rec.description[:500],
                "collective_evidence": rec.evidence[:500],
                "collective_provenance": rec.provenance.to_dict(),
                "collective_knowledge_id": rec.knowledge_id,
                "collective_candidate_id": rec.candidate_id,
                "collective_status": rec.status.value,
                "collective_approved_by": rec.approved_by,
            })
        return {"collective": items, "count": len(items)}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _knowledge_from_candidate(candidate: CollectiveCandidate, approved_by: str) -> CollectiveKnowledge:
        """Produce the APPROVED collective record from a candidate (provenance preserved)."""
        from datetime import datetime, timezone

        collective_id = candidate.candidate_id.replace("COLL-C-", "COLL-K-")
        return CollectiveKnowledge(
            knowledge_id=collective_id,
            candidate_id=candidate.candidate_id,
            kind=candidate.kind,
            key=candidate.key,
            value=candidate.value,
            description=candidate.description,
            evidence=candidate.evidence,
            provenance=candidate.provenance,
            status=CollectiveStatus.APPROVED,
            approved_at=datetime.now(timezone.utc),
            approved_by=approved_by,
            metadata=dict(candidate.metadata),
        )

    @staticmethod
    def _detect_kind(record: Any) -> CollectiveKind | None:
        has_key = hasattr(record, "key") and hasattr(record, "value")
        has_corr = hasattr(record, "target") and hasattr(record, "correction")
        if has_key:
            return CollectiveKind.PREFERENCE
        if has_corr:
            return CollectiveKind.CORRECTION
        return None

    def _provenance_from_record(self, record: Any) -> CollectiveProvenance | None:
        prov = getattr(record, "provenance", None)
        if prov is None:
            return None
        principal_id = _strip_controls(getattr(prov, "principal_id", ""), 128)
        if not principal_id:
            return None
        authority = _strip_controls(getattr(prov, "authority", ""), 32)
        if not authority:
            return None
        return CollectiveProvenance(
            principal_id=principal_id,
            authority=authority,
            session_id=_strip_controls(getattr(prov, "session_id", ""), 128),
            source=_strip_controls(getattr(prov, "source", ""), 64),
            action=_strip_controls(getattr(prov, "action", ""), 80),
            recorded_at=getattr(prov, "recorded_at", _utc_now()),
            candidate_created_at=_utc_now(),
        )

    def _payload_from_record(
        self, record: Any, kind: CollectiveKind
    ) -> tuple[str, str, str, str] | None:
        """Return (key, value, description, evidence) or None when ineligible."""
        # Bounded, structured — no raw conversational text. Eligible records need
        # the structured, canonical fields B3.1 already bounds.
        if kind is CollectiveKind.PREFERENCE:
            key = _strip_controls(getattr(record, "key", ""), 200)
            value = _strip_controls(getattr(record, "value", ""), 1_000)
            if not key or not value:
                return None
            description = f"Preference {key}={value} (contributor {getattr(record, 'principal_id', '')})"
            description = description[:500]
            prov = getattr(record, "provenance", None)
            evidence = f"principal {getattr(record, 'principal_id', '')} via {getattr(prov, 'action', '')}"
            evidence = evidence[:500]
            return key, value, description, evidence
        if kind is CollectiveKind.CORRECTION:
            target = _strip_controls(getattr(record, "target", ""), 200)
            corr = _strip_controls(getattr(record, "correction", ""), 1_000)
            desc = _strip_controls(getattr(record, "description", ""), 1_000)
            if not target or not corr:
                return None
            key = target
            value = corr
            description = f"Correction for {target}: {desc}" if desc else f"Correction for {target}"
            description = description[:500]
            prov = getattr(record, "provenance", None)
            evidence = f"principal {getattr(record, 'principal_id', '')} via {getattr(prov, 'action', '')}: {desc}"
            evidence = evidence[:500]
            return key, value, description, evidence
        return None
