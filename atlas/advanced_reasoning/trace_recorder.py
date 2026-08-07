"""Atlas Advanced Reasoning — ReasoningTraceRecorder (Track D, Batch 2).

Pure, event-driven recorder for completed reasoning traces. Maintains a
bounded in-memory ring buffer and exposes the read-only
:meth:`recent` / :meth:`count` / :meth:`summary` surface consumed by the
:class:`~atlas.advanced_reasoning.meta.MetaReasoningEngine` (and compatible
with the existing atlas.reasoning ``ReasoningRecorder`` duck-type).

The recorder is event-driven by *design*: it exposes a
:meth:`on_pipeline_completed` handler that the kernel may subscribe to the
existing ``runtime.pipeline.completed`` event. This module NEVER imports the
EventBus — the subscription itself is kernel-owned.

Pure logic. No storage. No kernel. No AI SDKs. No atlas.reasoning imports.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from atlas.advanced_reasoning.models import ReasoningTrace

#: Bounded buffer size used when a caller does not specify one.
_DEFAULT_MAX_SIZE: int = 100


class ReasoningTraceRecorder:
    """Bounded in-memory ring buffer for reasoning traces.

    Args:
        max_size: Maximum number of traces retained. Older traces are
            discarded when the buffer exceeds this size. Must be positive.
    """

    def __init__(self, max_size: int = _DEFAULT_MAX_SIZE) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be a positive integer")
        self._max_size = max_size
        self._traces: deque[ReasoningTrace] = deque(maxlen=max_size)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, trace: ReasoningTrace) -> None:
        """Append a reasoning trace to the buffer.

        When the buffer is full, the oldest trace is automatically discarded.
        Non-trace payloads are ignored (fail-soft) — the recorder never
        raises on malformed input.
        """
        if not isinstance(trace, ReasoningTrace):
            return
        self._traces.append(trace)

    def on_pipeline_completed(self, payload: dict[str, Any] | None = None) -> None:
        """Event-handler entry point for ``runtime.pipeline.completed``.

        The kernel owns the EventBus subscription; this module only exposes
        the handler. Traces are not derivable from the event payload itself,
        so this method is a no-op placeholder kept for wiring symmetry: the
        kernel is expected to push completed ``ReasoningTrace`` objects via
        :meth:`record` when they become available.

        Args:
            payload: Optional event payload (currently unused).
        """
        return None

    # ------------------------------------------------------------------
    # Read surface (duck-typed with ReasoningRecorder)
    # ------------------------------------------------------------------

    def recent(self, n: int = 10) -> list[ReasoningTrace]:
        """Return the most recent n traces, newest first.

        Args:
            n: Number of traces to return; capped by the buffer size.

        Returns:
            A list of up to n ReasoningTrace instances, newest first.
        """
        if n <= 0:
            return []
        return list(reversed(self._traces))[:n]

    def count(self) -> int:
        """Return the number of retained traces (always <= max_size)."""
        return len(self._traces)

    @property
    def max_size(self) -> int:
        """Return the configured maximum buffer size."""
        return self._max_size

    def summary(self) -> dict[str, Any]:
        """Return an aggregate summary of retained traces.

        Mirrors the ReasoningRecorder summary contract: count, success count,
        failure count, success rate, latest timestamp, and per-strategy
        distribution.
        """
        total = self.count()
        if total == 0:
            return {
                "count": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": None,
                "latest_timestamp": None,
                "strategy_distribution": {},
            }
        success_count = sum(
            1 for t in self._traces if self._trace_success(t) is True
        )
        failure_count = sum(
            1 for t in self._traces if self._trace_success(t) is False
        )
        distribution: dict[str, int] = {}
        for trace in self._traces:
            key = trace.strategy.name
            distribution[key] = distribution.get(key, 0) + 1
        latest = max(
            (t.completed_at or t.started_at for t in self._traces),
            default=None,
        )
        return {
            "count": total,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": round(success_count / total, 4) if total else None,
            "latest_timestamp": latest.isoformat() if latest else None,
            "strategy_distribution": distribution,
        }

    def clear(self) -> None:
        """Remove all retained traces."""
        self._traces.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _trace_success(trace: ReasoningTrace) -> bool | None:
        """Best-effort success flag for a trace; None when indeterminate."""
        if trace.status.name == "COMPLETED":
            return True
        if trace.status.name in ("FAILED", "RAN_OUT_OF_BUDGET"):
            return False
        return None
