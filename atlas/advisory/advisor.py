"""Atlas Advisory — ProactiveAdvisor (P5/Proactive Advisory).

Composes the EXISTING post-core F1/F10/F11 signals and the B3.x/B4/P4
seams into one bounded, JSON-safe, principal-scoped advisory report.
Advisory only — never autonomous execution.

Reused seams (each is optional; missing seams degrade to no items from
that source rather than crashing the report):

  * F1  EnvironmentObserver            (post-core)  -> environment changes
  * F10 ProviderAvailabilityTracker     (post-core)  -> provider health
  * F11 SelfManagementReview           (post-core)  -> maintenance needs
  * B3.x InteractionLearningBridge
              .planning_context_provider(principal_id)
                                            -> principal-scoped
                                               private preferences
  * P4   CollectiveGovernance
              .collective_context()         -> approved collective
                                               knowledge

Design contract:
  * Pure: never imports kernel, runtime, AI, storage, governance.
  * Deterministic: identical inputs produce identical reports.
  * Bounded: every list/tuple is hard-capped; every text field is bounded.
  * Fail-closed: a missing source is silent, not fatal; a failing source
    is recorded in ``source_errors`` and the report still composes.
  * Owner / User authority: a USER principal never gets an item that
    implies OWNER-only action; ``requires_owner`` is True only when the
    suggested action names an OWNER-only path.
  * Never executes: the only executable surfaces this module touches are
    the existing kernel bridges; this module only calls existing
    self-management review etc. (read-only) and composes their output.
    The ``suggested_action`` strings are hints for the operator, not
    invocations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from atlas.advisory.models import (
    AdvisoryItem,
    AdvisoryReport,
    AdvisorySeverity,
    AdvisorySource,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


#: Upper bound on items per advisory run. Past this the report is truncated.
_MAX_ITEMS: int = 32

#: Bounded text fields.
_MAX_SUMMARY_CHARS: int = 400
_MAX_ACTION_CHARS: int = 200
_MAX_EVIDENCE_IDS: int = 8

#: Owner-only action hints. A User never gets an item suggesting one of these.
_OWNER_ONLY_ACTIONS: frozenset[str] = frozenset({
    "atlas.run_development_cycle",          # F9 — DRAFT proposal path
    "atlas.confirm_development_approval",   # explicit human approval
    "atlas.run_development_execution",      # APPROVED-only execution
    "atlas.submit_development_for_promotion_review",  # Stage H
    "atlas.pending_promotion_reviews",      # Stage H read-only view
})


def _bounded_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


class ProactiveAdvisor:
    """Composes bounded user-facing observations/suggestions from existing seams.

    Args:
        environment_observer: Optional F1 ``EnvironmentObserver`` (duck-typed
            — uses ``last_result`` when present).
        availability: Optional F10 ``ProviderAvailabilityTracker`` (duck-typed
            — uses ``snapshot()`` when present).
        self_management_review: Optional F11 ``SelfManagementReview`` (duck-typed
            — uses ``run_review()`` when present).
        interaction_bridge: Optional B3.x ``InteractionLearningBridge`` (duck-typed
            — uses ``planning_context_provider(principal_id)`` when present).
        collective_governance: Optional P4 ``CollectiveGovernance`` (duck-typed
            — uses ``collective_context()`` when present).
    """

    def __init__(
        self,
        environment_observer: Any | None = None,
        availability: Any | None = None,
        self_management_review: Any | None = None,
        interaction_bridge: Any | None = None,
        collective_governance: Any | None = None,
    ) -> None:
        self._environment_observer = environment_observer
        self._availability = availability
        self._self_management_review = self_management_review
        self._interaction_bridge = interaction_bridge
        self._collective_governance = collective_governance
        self._counter = 0
        # Monotonic counter for stable, deterministic item ids.
        self._item_counter = 0

    @property
    def advisory_count(self) -> int:
        """Total advisory runs this advisor has produced."""
        return self._counter

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------

    def run_advisory(
        self,
        principal_id: str = "",
    ) -> AdvisoryReport:
        """Run ONE bounded advisory composition and return a report.

        Args:
            principal_id: The principal the report is scoped to. Required
                for principal-scoped sources (interaction bridge). An empty
                value scopes to a generic non-principal view.

        Returns:
            An ``AdvisoryReport`` with bounded items, source_errors, and
            the list of sources that contributed.
        """
        if not isinstance(principal_id, str):
            principal_id = ""
        principal_id = principal_id.strip()
        self._counter += 1
        advisory_id = f"ADV-{self._counter:06d}"
        generated_at = _utc_now()

        items: list[AdvisoryItem] = []
        source_errors: list[tuple[str, str]] = []
        sources_used: list[str] = []

        self._collect_environment(items, source_errors, sources_used, principal_id)
        self._collect_availability(items, source_errors, sources_used, principal_id)
        self._collect_self_management(items, source_errors, sources_used, principal_id)
        self._collect_interaction(items, source_errors, sources_used, principal_id)
        self._collect_collective(items, source_errors, sources_used, principal_id)

        # Truncate deterministically (oldest first preserved up to cap).
        if len(items) > _MAX_ITEMS:
            items = items[:_MAX_ITEMS]

        return AdvisoryReport(
            advisory_id=advisory_id,
            generated_at=generated_at,
            principal_id=principal_id,
            items=tuple(items),
            source_errors=tuple(source_errors)[-8:],
            sources_used=tuple(sources_used),
        )

    # ------------------------------------------------------------------
    # Source collectors (each bounded, fail-soft)
    # ------------------------------------------------------------------

    def _next_item_id(self, source_label: str) -> str:
        self._item_counter += 1
        return f"ADV-ITEM-{self._item_counter:06d}"

    def _record(
        self,
        items: list[AdvisoryItem],
        severity: AdvisorySeverity,
        source: AdvisorySource,
        kind: str,
        summary: str,
        evidence_ids: list[str] | tuple[str, ...],
        suggested_action: str,
        requires_owner: bool,
        principal_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if len(items) >= _MAX_ITEMS:
            return
        bounded_summary = _bounded_text(summary, _MAX_SUMMARY_CHARS)
        bounded_action = _bounded_text(suggested_action, _MAX_ACTION_CHARS)
        if not bounded_summary:
            return
        bounded_evidence = tuple(
            str(e)[:128] for e in list(evidence_ids)[:_MAX_EVIDENCE_IDS]
            if e
        )
        items.append(
            AdvisoryItem(
                item_id=self._next_item_id(source.value),
                severity=severity,
                source=source,
                kind=kind[:80] or "observation",
                summary=bounded_summary,
                evidence_ids=bounded_evidence,
                suggested_action=bounded_action,
                requires_owner=bool(requires_owner),
                principal_id=principal_id,
                recorded_at=_utc_now(),
                metadata=dict(metadata or {}),
            )
        )

    def _collect_environment(
        self,
        items: list[AdvisoryItem],
        errors: list[tuple[str, str]],
        used: list[str],
        principal_id: str,
    ) -> None:
        if self._environment_observer is None:
            return
        last_result = getattr(self._environment_observer, "last_result", None)
        if last_result is None:
            return
        try:
            changes = list(getattr(last_result, "changes", ()) or ())
        except Exception as exc:
            errors.append(("environment", str(exc)[:200]))
            return
        used.append("environment")
        # Filter to non-UNCHANGED and cap. (UNCHANGED was already filtered
        # by the F1 layer for event emission; here we still skip them.)
        non_unchanged = [
            c for c in changes
            if getattr(c, "change_type", None) is not None
            and getattr(c.change_type, "name", "") != "UNCHANGED"
        ]
        for change in non_unchanged[:_MAX_EVIDENCE_IDS]:
            change_type = getattr(change.change_type, "name", "CHANGED")
            entity_key = getattr(getattr(change, "entity", None), "key", "")
            summary = f"Environment {change_type}: {entity_key}"
            self._record(
                items,
                AdvisorySeverity.NOTICE,
                AdvisorySource.ENVIRONMENT,
                kind=f"environment_{change_type.lower()}",
                summary=summary,
                evidence_ids=[entity_key] if entity_key else [],
                suggested_action="atlas.observe_environment",  # F1 only
                requires_owner=False,
                principal_id=principal_id,
                metadata={"source": "environment_observer"},
            )

    def _collect_availability(
        self,
        items: list[AdvisoryItem],
        errors: list[tuple[str, str]],
        used: list[str],
        principal_id: str,
    ) -> None:
        if self._availability is None:
            return
        snap = getattr(self._availability, "snapshot", None)
        if not callable(snap):
            return
        try:
            snapshot = snap()
        except Exception as exc:
            errors.append(("availability", str(exc)[:200]))
            return
        if not isinstance(snapshot, dict):
            return
        used.append("availability")
        status = str(snapshot.get("status", "UNKNOWN"))
        if status == "HEALTHY":
            return  # No advisory noise for healthy providers.
        severity = (
            AdvisorySeverity.WARNING
            if status in ("OFFLINE", "DEGRADED")
            else AdvisorySeverity.NOTICE
        )
        summary = (
            f"AI provider availability reported {status} "
            f"({snapshot.get('recent_failures', 0)} recent failures)."
        )
        self._record(
            items,
            severity,
            AdvisorySource.AVAILABILITY,
            kind="provider_availability",
            summary=summary,
            evidence_ids=[str(snapshot.get("name", "ai_provider"))],
            suggested_action="atlas.run_self_management_review",  # F11 surface
            requires_owner=False,
            principal_id=principal_id,
            metadata={"status": status},
        )

    def _collect_self_management(
        self,
        items: list[AdvisoryItem],
        errors: list[tuple[str, str]],
        used: list[str],
        principal_id: str,
    ) -> None:
        if self._self_management_review is None:
            return
        run = getattr(self._self_management_review, "run_review", None)
        if not callable(run):
            return
        try:
            report = run()
        except Exception as exc:
            errors.append(("self_management", str(exc)[:200]))
            return
        used.append("self_management")
        needs = list(getattr(report, "needs", ()) or ())
        for need in needs[:_MAX_EVIDENCE_IDS]:
            severity = (
                AdvisorySeverity.WARNING
                if "offline" in (need.kind or "")
                or "stale" in (need.kind or "")
                else AdvisorySeverity.NOTICE
            )
            suggested = "atlas.run_self_management_review"
            self._record(
                items,
                severity,
                AdvisorySource.SELF_MANAGEMENT,
                kind=str(need.kind or "maintenance"),
                summary=str(need.summary or "Maintenance need flagged."),
                evidence_ids=list(need.evidence_ids or [])[:_MAX_EVIDENCE_IDS],
                suggested_action=suggested,
                requires_owner=False,
                principal_id=principal_id,
                metadata={"need_id": str(need.need_id or "")},
            )
        # Surface a lifecycle status hint when components are degraded.
        for name in list(getattr(report, "offline_components", ()) or ()):
            self._record(
                items,
                AdvisorySeverity.WARNING,
                AdvisorySource.SELF_MANAGEMENT,
                kind="offline_component",
                summary=f"Lifecycle component OFFLINE: {name}",
                evidence_ids=[name],
                suggested_action="atlas.run_self_management_review",
                requires_owner=False,
                principal_id=principal_id,
                metadata={"component": name},
            )
        for name in list(getattr(report, "degraded_components", ()) or ()):
            self._record(
                items,
                AdvisorySeverity.WARNING,
                AdvisorySource.SELF_MANAGEMENT,
                kind="degraded_component",
                summary=f"Lifecycle component DEGRADED: {name}",
                evidence_ids=[name],
                suggested_action="atlas.run_self_management_review",
                requires_owner=False,
                principal_id=principal_id,
                metadata={"component": name},
            )

    def _collect_interaction(
        self,
        items: list[AdvisoryItem],
        errors: list[tuple[str, str]],
        used: list[str],
        principal_id: str,
    ) -> None:
        if self._interaction_bridge is None:
            return
        if not principal_id:
            # The principal-scoped context provider requires a principal.
            return
        provider_factory = getattr(
            self._interaction_bridge, "planning_context_provider", None
        )
        if not callable(provider_factory):
            return
        try:
            provider = provider_factory(principal_id)
        except Exception as exc:
            errors.append(("interaction", str(exc)[:200]))
            return
        if not callable(provider):
            return
        try:
            context = provider()
        except Exception as exc:
            errors.append(("interaction", str(exc)[:200]))
            return
        if not isinstance(context, dict):
            return
        used.append("interaction")
        prefs = list(context.get("preferences", []) or [])
        corrs = list(context.get("corrections", []) or [])
        # Note: never echo raw user text. We only surface the bounded
        # provenance + key/correction-target so the operator can decide
        # whether to inspect.
        for pref in prefs[:_MAX_EVIDENCE_IDS]:
            prov = pref.get("provenance", {}) if isinstance(pref, dict) else {}
            self._record(
                items,
                AdvisorySeverity.INFO,
                AdvisorySource.INTERACTION,
                kind="private_preference",
                summary=(
                    f"Private preference '{pref.get('key', '')}' is set for "
                    f"principal {prov.get('principal_id', principal_id)}."
                ),
                evidence_ids=[str(prov.get("session_id", "")) or "session:unknown"],
                suggested_action="atlas.chat",  # observe via conversation
                requires_owner=False,
                principal_id=principal_id,
                metadata={"provenance": dict(prov) if isinstance(prov, dict) else {}},
            )
        for corr in corrs[:_MAX_EVIDENCE_IDS]:
            prov = corr.get("provenance", {}) if isinstance(corr, dict) else {}
            self._record(
                items,
                AdvisorySeverity.INFO,
                AdvisorySource.INTERACTION,
                kind="private_correction",
                summary=(
                    f"Private correction on '{corr.get('target', '')}' "
                    f"recorded for principal {prov.get('principal_id', principal_id)}."
                ),
                evidence_ids=[str(prov.get("session_id", "")) or "session:unknown"],
                suggested_action="atlas.chat",
                requires_owner=False,
                principal_id=principal_id,
                metadata={"provenance": dict(prov) if isinstance(prov, dict) else {}},
            )

    def _collect_collective(
        self,
        items: list[AdvisoryItem],
        errors: list[tuple[str, str]],
        used: list[str],
        principal_id: str,
    ) -> None:
        if self._collective_governance is None:
            return
        coll_provider = getattr(
            self._collective_governance, "collective_context", None
        )
        if not callable(coll_provider):
            return
        try:
            context = coll_provider()
        except Exception as exc:
            errors.append(("collective", str(exc)[:200]))
            return
        if not isinstance(context, dict):
            return
        used.append("collective")
        entries = list(context.get("collective", []) or [])
        for entry in entries[:_MAX_EVIDENCE_IDS]:
            kind = str(entry.get("collective_kind", ""))
            key = str(entry.get("collective_key", ""))
            prov = (
                entry.get("collective_provenance", {})
                if isinstance(entry, dict)
                else {}
            )
            source_principal = (
                prov.get("principal_id", "")
                if isinstance(prov, dict)
                else ""
            )
            # Collective items hint at the conversation surface so the
            # operator can let the user observe their behavior, but
            # require no action.
            self._record(
                items,
                AdvisorySeverity.INFO,
                AdvisorySource.COLLECTIVE,
                kind=f"collective_{kind}" if kind else "collective_record",
                summary=(
                    f"Approved collective {kind or 'record'}: '{key}' "
                    f"(contributor {source_principal})."
                ),
                evidence_ids=[str(entry.get("collective_knowledge_id", ""))],
                suggested_action="atlas.chat",
                requires_owner=False,
                principal_id=principal_id,
                metadata={"kind": kind, "key": key},
            )

    # ------------------------------------------------------------------
    # Admin / helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_owner_only_action(action: str) -> bool:
        """True when a suggested action names an OWNER-only governed path.

        Public helper so the kernel CLI / tests can pre-filter items
        before showing them to a USER.
        """
        return action in _OWNER_ONLY_ACTIONS

    @staticmethod
    def owner_only_actions() -> frozenset[str]:
        """Return the bounded set of OWNER-only suggested actions."""
        return _OWNER_ONLY_ACTIONS
