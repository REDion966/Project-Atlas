"""Atlas Interaction — InteractionLearningBridge (P3/B3.2).

Integrates per-user B3.1 preference/correction records into the EXISTING
learning and planning-context mechanisms:

  1. Learning integration — each recorded PreferenceRecord / CorrectionRecord
     becomes a bounded, attributable ``LearningInsight`` stored in the EXISTING
     ``LearningMemory`` (via ``LearningEngine.memory.store_insights``). The
     ``metadata`` carries the immutable provenance (principal, authority,
     session) plus the source record id, so the insight stays attributable to
     its originating principal/session.

  2. Planning-context integration — a principal-scoped, advisory
     ``planning_context_provider`` surfaces the user's own preferences and
     corrections as bounded JSON-safe context for future decisions. Records
     never leak across principals: the provider reads only the acting
     principal's records. Advisory only — it never executes tools, actions,
     governance, approvals, promotion, or self-modification.

  * A User's record is stored at USER importance/confidence (never elevated).
  * AuthorityLevel can never change: provenance is immutable, and this module
    never touches AuthorityService or any session/principal store.
  * No schema change, no migration, no RuntimeCoordinator change, no
    Atlas.tick() change.

Reuses existing seams only: ``atlas.learning_engine.models.LearningInsight``,
``atlas.learning_engine.learning_memory.LearningMemory``,
``atlas.interaction.*`` (B3.1). No new learning subsystem, no storage, no AI.
"""

from __future__ import annotations

from typing import Any

from atlas.interaction.models import (
    CorrectionRecord,
    InteractionKind,
    PreferenceRecord,
)
from atlas.interaction.repository import InteractionRepository

#: LearningInsight fields this bridge emits (bounded, deterministic).
_INSIGHT_ID_PREFIX: str = "LRN-INT"
_MAX_INSIGHTS_PER_FLUSH: int = 200
_MAX_CONTEXT_ITEMS: int = 8
_MAX_ITEM_CHARS: int = 400


def _bounded_text(value: Any, limit: int) -> str:
    """Return a bounded string, or '' for non-strings."""
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _provenance_meta(record: Any) -> dict[str, str]:
    """Project the immutable provenance metadata from a B3.1 record."""
    provenance = getattr(record, "provenance", None)
    if provenance is None:
        return {}
    return {
        "principal_id": _bounded_text(
            getattr(provenance, "principal_id", ""), 128
        ),
        "authority": _bounded_text(getattr(provenance, "authority", ""), 32),
        "session_id": _bounded_text(getattr(provenance, "session_id", ""), 128),
        "source": _bounded_text(getattr(provenance, "source", ""), 64),
    }


class InteractionLearningBridge:
    """Flushes B3.1 records into existing LearningMemory + planning context.

    Args:
        repository: The B3.1 InteractionRepository to read records from.
        learning_memory: The existing ``LearningMemory`` to write insights
            into (duck-typed; any object exposing ``store_insights``).
    """

    def __init__(
        self,
        repository: InteractionRepository,
        learning_memory: Any | None = None,
    ) -> None:
        if not isinstance(repository, InteractionRepository):
            raise ValueError("repository must be an InteractionRepository (fail-closed)")
        self._repository = repository
        self._learning_memory = learning_memory
        self._flush_counter = 0

    @property
    def repository(self) -> InteractionRepository:
        return self._repository

    # ------------------------------------------------------------------
    # Learning integration (B3.1 records → existing LearningInsight)
    # ------------------------------------------------------------------

    def flush_to_learning(self) -> int:
        """Flush every stored B3.1 record into the existing LearningMemory.

        Each record becomes one bounded ``LearningInsight`` (preference →
        ``TOOL_USAGE``/``OPTIMIZATION``; correction → ``FAILURE_AVOIDANCE``),
        carrying immutable provenance in ``metadata``. Repeated calls re-emit
        the same records deterministically (idempotent at the record level;
        ``LearningMemory``/consolidator dedupe by content). ``LearningInsight``
        imports stay inside this method so a missing learning package never
        breaks record capture (fail-closed at the integration seam).

        Returns:
            The number of insights written (bounded per call).
        """
        if self._learning_memory is None:
            return 0
        writer = getattr(self._learning_memory, "store_insights", None)
        if not callable(writer):
            return 0
        try:
            from atlas.learning_engine.models import (
                InsightImportance,
                LearningCategory,
                LearningInsight,
            )
        except Exception:
            return 0

        insights: list[LearningInsight] = []

        # Bounded read of all stored records. Principal attribution is
        # preserved in the insight metadata (never used to elevate).
        preferences = self._repository.get_all_preferences(
            n=_MAX_INSIGHTS_PER_FLUSH // 2
        )
        corrections = self._repository.get_all_corrections(
            n=_MAX_INSIGHTS_PER_FLUSH // 2
        )

        for pref in preferences:
            insights.append(
                self._preference_insight(pref, LearningInsight, LearningCategory, InsightImportance)
            )
        for corr in corrections:
            insights.append(
                self._correction_insight(corr, LearningInsight, LearningCategory, InsightImportance)
            )

        if not insights:
            return 0
        writer(insights)
        self._flush_counter += len(insights)
        return len(insights)

    # ------------------------------------------------------------------
    # Planning-context integration (principal-scoped, advisory)
    # ------------------------------------------------------------------

    def planning_context_provider(self, principal_id: str = ""):
        """Return a zero-argument provider of principal-scoped advisory context.

        The returned callable builds a bounded, JSON-safe dict carrying ONLY
        the acting principal's own preferences and corrections, plus their
        provenance. It is advisory context for future reasoning/decisions —
        never executable and never capable of changing authority, execution,
        governance, approval, or promotion state.

        Args:
            principal_id: The acting principal to scope context to.

        Returns:
            A callable returning a bounded dict, or None when ``principal_id``
            is missing/empty (fail-closed).
        """
        if not isinstance(principal_id, str) or not principal_id.strip():
            return None

        def _provider() -> dict[str, Any]:
            return self._build_principal_context(principal_id)

        return _provider

    def _build_principal_context(self, principal_id: str) -> dict[str, Any]:
        """Build the bounded advisory context for ONE principal."""
        prefs = self._repository.get_preferences(principal_id, n=_MAX_CONTEXT_ITEMS)
        corrs = self._repository.get_corrections(principal_id, n=_MAX_CONTEXT_ITEMS)
        return {
            "principal_id": _bounded_text(principal_id, 128),
            "preferences": [self._pref_to_context(p) for p in prefs],
            "corrections": [self._corr_to_context(c) for c in corrs],
        }

    # ------------------------------------------------------------------
    # Projection helpers (deterministic, bounded, provenance-preserving)
    # ------------------------------------------------------------------

    @staticmethod
    def _pref_to_context(pref: PreferenceRecord) -> dict[str, Any]:
        return {
            "kind": InteractionKind.PREFERENCE.value,
            "key": _bounded_text(pref.key, 200),
            "value": _bounded_text(pref.value, _MAX_ITEM_CHARS),
            "provenance": _provenance_meta(pref),
        }

    @staticmethod
    def _corr_to_context(corr: CorrectionRecord) -> dict[str, Any]:
        return {
            "kind": InteractionKind.CORRECTION.value,
            "target": _bounded_text(corr.target, 200),
            "description": _bounded_text(corr.description, _MAX_ITEM_CHARS),
            "correction": _bounded_text(corr.correction, _MAX_ITEM_CHARS),
            "provenance": _provenance_meta(corr),
        }

    @classmethod
    def _preference_insight(cls, pref, LearningInsight, LearningCategory, InsightImportance):
        meta = _provenance_meta(pref)
        meta["record_id"] = _bounded_text(getattr(pref, "record_id", ""), 128)
        meta["source_record_kind"] = InteractionKind.PREFERENCE.value
        return LearningInsight(
            insight_id=f"{_INSIGHT_ID_PREFIX}-P-{cls._record_suffix(pref)}",
            category=LearningCategory.TOOL_USAGE,
            title=f"Preference: {_bounded_text(pref.key, 120)}",
            description=_bounded_text(pref.value, 1000),
            importance=InsightImportance.MEDIUM,
            confidence=0.6,
            observation_count=1,
            applicable_areas=["interaction"],
            metadata=meta,
        )

    @classmethod
    def _correction_insight(cls, corr, LearningInsight, LearningCategory, InsightImportance):
        meta = _provenance_meta(corr)
        meta["record_id"] = _bounded_text(getattr(corr, "record_id", ""), 128)
        meta["source_record_kind"] = InteractionKind.CORRECTION.value
        body = _bounded_text(corr.description, 600)
        if body and _bounded_text(corr.correction, 600):
            body = f"{body} -> {_bounded_text(corr.correction, 600)}"
        else:
            body = body or _bounded_text(corr.correction, 600)
        return LearningInsight(
            insight_id=f"{_INSIGHT_ID_PREFIX}-C-{cls._record_suffix(corr)}",
            category=LearningCategory.FAILURE_AVOIDANCE,
            title=f"Correction: {_bounded_text(corr.target, 120)}",
            description=body,
            importance=InsightImportance.MEDIUM,
            confidence=0.5,
            observation_count=1,
            applicable_areas=["interaction"],
            metadata=meta,
        )

    @staticmethod
    def _record_suffix(record: Any) -> str:
        return _bounded_text(getattr(record, "record_id", ""), 128)
