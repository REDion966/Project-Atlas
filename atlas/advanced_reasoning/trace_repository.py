"""Atlas Advanced Reasoning — ReasoningTraceRepository (Track D, Batch 3).

Bounded in-memory store for reasoning artifacts (traces, hypothesis sets,
verification reports, meta assessments). Storage-agnostic: persistence is
delegated to an injected :class:`AdvancedReasoningStorage` protocol adapter
(dual-write, best-effort). Failures in storage writes never break the
in-memory path — exactly the Track C ``EpisodicRepository`` degradation model.

No SQLite. No kernel. No gateway. No runtime. No events. Pure logic.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from atlas.advanced_reasoning.models import (
    HypothesisSet,
    MetaAssessment,
    ReasoningTrace,
    VerificationReport,
)

logger = logging.getLogger(__name__)

#: Default maximum number of traces retained before eviction.
_DEFAULT_MAX_TRACES: int = 500


class ReasoningTraceRepository:
    """Bounded repository for reasoning artifacts.

    Stores :class:`ReasoningTrace`, :class:`HypothesisSet`,
    :class:`VerificationReport` and :class:`MetaAssessment` objects in memory.
    When an ``AdvancedReasoningStorage`` adapter is injected, writes are
    dual-routed (best-effort; storage failures are logged and swallowed).
    Reads fall back to memory when storage is unavailable.
    """

    def __init__(
        self,
        max_traces: int = _DEFAULT_MAX_TRACES,
        storage: Any | None = None,
    ) -> None:
        """Initialize the repository.

        Args:
            max_traces: Maximum number of traces retained before eviction.
            storage: Optional ``AdvancedReasoningStorage`` protocol adapter.
        """
        if max_traces <= 0:
            raise ValueError("max_traces must be positive")
        self._max_traces = max_traces
        self._storage = storage

        self._traces: deque[ReasoningTrace] = deque(maxlen=max_traces)
        self._trace_index: dict[str, ReasoningTrace] = {}
        self._hypothesis_sets: dict[str, HypothesisSet] = {}
        self._verification_reports: dict[str, VerificationReport] = {}
        self._meta_assessments: dict[str, MetaAssessment] = {}

    # ------------------------------------------------------------------
    # Traces
    # ------------------------------------------------------------------

    def store_trace(self, trace: ReasoningTrace) -> None:
        """Store or update a reasoning trace.

        If the trace already exists, the old entry is replaced in place so
        the index stays consistent. When full, the oldest trace is evicted.
        """
        old = self._trace_index.get(trace.trace_id)
        if old is not None:
            self._traces.remove(old)
            self._traces.append(trace)
            self._trace_index[trace.trace_id] = trace
        else:
            if len(self._traces) == self._max_traces:
                evicted = self._traces.popleft()
                self._trace_index.pop(evicted.trace_id, None)
            self._traces.append(trace)
            self._trace_index[trace.trace_id] = trace
        self._try_storage_write("store_trace", trace)

    def get_trace(self, trace_id: str) -> ReasoningTrace | None:
        """Retrieve a single trace by ID."""
        return self._trace_index.get(trace_id)

    def recent_traces(self, n: int = 100) -> list[ReasoningTrace]:
        """Return the most recent n traces (newest first)."""
        if n <= 0:
            return []
        return list(reversed(self._traces))[:n]

    @property
    def trace_count(self) -> int:
        """Number of retained traces (always <= max_traces)."""
        return len(self._traces)

    # ------------------------------------------------------------------
    # Hypothesis sets
    # ------------------------------------------------------------------

    def store_hypothesis_set(self, hypothesis_set: HypothesisSet) -> None:
        """Store or update a hypothesis set."""
        self._hypothesis_sets[hypothesis_set.set_id] = hypothesis_set
        self._try_storage_write("store_hypothesis_set", hypothesis_set)

    def get_hypothesis_set(self, set_id: str) -> HypothesisSet | None:
        """Retrieve a hypothesis set by ID."""
        return self._hypothesis_sets.get(set_id)

    @property
    def hypothesis_set_count(self) -> int:
        """Number of retained hypothesis sets."""
        return len(self._hypothesis_sets)

    # ------------------------------------------------------------------
    # Verification reports
    # ------------------------------------------------------------------

    def store_verification_report(self, report: VerificationReport) -> None:
        """Store a verification report (append-only log semantics)."""
        self._verification_reports[report.report_id] = report
        self._try_storage_write("store_verification_report", report)

    def get_verification_report(self, report_id: str) -> VerificationReport | None:
        """Retrieve a verification report by ID."""
        return self._verification_reports.get(report_id)

    @property
    def verification_report_count(self) -> int:
        """Number of retained verification reports."""
        return len(self._verification_reports)

    # ------------------------------------------------------------------
    # Meta assessments
    # ------------------------------------------------------------------

    def store_meta_assessment(self, assessment: MetaAssessment) -> None:
        """Store a meta assessment (append-only log semantics)."""
        self._meta_assessments[assessment.assessment_id] = assessment
        self._try_storage_write("store_meta_assessment", assessment)

    def get_meta_assessment(self, assessment_id: str) -> MetaAssessment | None:
        """Retrieve a meta assessment by ID."""
        return self._meta_assessments.get(assessment_id)

    @property
    def meta_assessment_count(self) -> int:
        """Number of retained meta assessments."""
        return len(self._meta_assessments)

    # ------------------------------------------------------------------
    # Summary & admin
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a summary dict of the repository state."""
        return {
            "trace_count": self.trace_count,
            "hypothesis_set_count": self.hypothesis_set_count,
            "verification_report_count": self.verification_report_count,
            "meta_assessment_count": self.meta_assessment_count,
            "max_traces": self._max_traces,
            "storage_available": self._storage is not None and bool(
                getattr(self._storage, "is_available", lambda: False)()
            ),
        }

    def clear(self) -> None:
        """Clear all stored data."""
        self._traces.clear()
        self._trace_index.clear()
        self._hypothesis_sets.clear()
        self._verification_reports.clear()
        self._meta_assessments.clear()

    # ------------------------------------------------------------------
    # Storage integration (best-effort dual-write)
    # ------------------------------------------------------------------

    def _try_storage_write(self, method_name: str, data: object) -> None:
        """Write to the storage adapter, degrading gracefully on failure."""
        storage = self._storage
        if storage is None:
            return
        try:
            if not storage.is_available():
                return
            writer = getattr(storage, method_name, None)
            if writer is not None:
                writer(data)  # type: ignore[operator]
        except Exception:
            logger.exception(
                "Advanced-reasoning storage write failed for %s", method_name
            )

    def restore(self) -> dict[str, Any]:
        """Load persisted artifacts from storage into memory.

        Returns a summary dict of the number of restored artifacts. If no
        storage is injected or the storage is unavailable, returns zeros.
        """
        storage = self._storage
        if storage is None or not self._storage_available():
            return self._zero_restore()

        restored = 0
        try:
            for trace in storage.load_traces():
                if trace.trace_id not in self._trace_index:
                    self._traces.append(trace)
                    self._trace_index[trace.trace_id] = trace
                    restored += 1
        except Exception:
            logger.exception("Failed to restore traces from storage")
        return {"restored_artifacts": restored}

    def _storage_available(self) -> bool:
        try:
            return bool(self._storage.is_available())
        except Exception:
            return False

    @staticmethod
    def _zero_restore() -> dict[str, Any]:
        return {"restored_artifacts": 0}
