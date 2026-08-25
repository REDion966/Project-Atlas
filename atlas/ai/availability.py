"""Atlas AI — Provider Availability (Post-Core F10).

A small, deterministic, observation-only availability component that derives
an AI-provider health state from bounded recent outcome records.

Design constraints (resource independence / model-optional intelligence):
  * Reuses the EXISTING ``FailureClassification`` taxonomy
    (:func:`atlas.ai.failure.classify_failure`) as the only source of failure
    reasons, and the EXISTING lifecycle vocabulary
    (:class:`atlas.lifecycle.models.ComponentStatus`: HEALTHY / DEGRADED /
    OFFLINE / UNKNOWN) as the availability states.
  * Bounded: keeps at most ``window`` recent ``(timestamp, reason, ok)``
    outcomes (default 32). No persistence, no growth.
  * On demand only: the tracker records outcomes when a caller reports them
    and computes status/snapshot when asked. No background monitoring, no
    threads, no asyncio, no network activity, no provider restart/recovery.
  * Deterministic: identical outcome sequences always yield identical
    status/snapshot results for an identical injected clock.
  * Model-independent by construction: recording and computing never calls
    a model and never requires one. An unused tracker is simply UNKNOWN.
  * Fail-safe: unknown exceptions are conservatively recorded via the
    existing classifier (which itself never raises).

Pure logic. No infrastructure. No provider imports. No AI calls.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Deque

from atlas.ai.failure import classify_failure
from atlas.lifecycle.models import ComponentStatus

#: Default bounded window of recent outcomes.
DEFAULT_WINDOW: int = 32

#: Upper bound for a stored failure-reason string.
_MAX_REASON_CHARS: int = 64


def utc_now() -> datetime:
    """Return the current UTC-aware datetime."""
    return datetime.now(timezone.utc)


class ProviderAvailabilityTracker:
    """Bounded, deterministic recorder of provider/model call outcomes.

    Args:
        name: Stable identity of the tracked subject (e.g. ``"ai_provider"``).
        window: Maximum number of recent outcomes retained (>= 1).
        clock: Optional ``Callable[[], datetime]`` (UTC) for deterministic
            tests; defaults to :func:`utc_now`.
    """

    def __init__(
        self,
        *,
        name: str = "ai_provider",
        window: int = DEFAULT_WINDOW,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if int(window) < 1:
            raise ValueError("window must be >= 1")
        self._name = name.strip()[:128]
        self._clock = clock or utc_now
        self._outcomes: Deque[tuple[datetime, str, bool]] = deque(
            maxlen=int(window)
        )
        self._recorded_total = 0

    # -- recording -----------------------------------------------------------

    def record_success(self) -> None:
        """Record one successful provider/model interaction."""
        self._append(ok=True, reason="success", exc=None)

    def record_failure(
        self,
        exc: BaseException | None = None,
        *,
        reason: str = "",
    ) -> None:
        """Record one failed interaction.

        Args:
            exc: The provider exception, classified through the EXISTING
                :func:`classify_failure` taxonomy when provided.
            reason: Explicit bounded reason used when no exception is given
                (defaults to ``"failure"``).
        """
        self._append(ok=False, reason=reason, exc=exc)

    def _append(
        self,
        *,
        ok: bool,
        reason: str,
        exc: BaseException | None,
    ) -> None:
        if exc is not None:
            classification = classify_failure(exc)
            reason = classification.reason or ("success" if ok else "failure")
        elif not reason:
            reason = "success" if ok else "failure"
        self._outcomes.append((self._clock(), reason[:_MAX_REASON_CHARS], ok))
        self._recorded_total += 1

    # -- deterministic derivation ---------------------------------------------

    @property
    def name(self) -> str:
        """The tracked subject identity."""
        return self._name

    def status(self) -> ComponentStatus:
        """Derive the availability state from the bounded recent history.

        Rules (deterministic):
          * no recorded outcomes                -> UNKNOWN
          * failures and successes both present -> DEGRADED
          * failures only                       -> OFFLINE
          * successes only                      -> HEALTHY
        """
        if not self._outcomes:
            return ComponentStatus.UNKNOWN
        has_failure = any(not ok for _, _, ok in self._outcomes)
        has_success = any(ok for _, _, ok in self._outcomes)
        if has_failure and has_success:
            return ComponentStatus.DEGRADED
        if has_failure:
            return ComponentStatus.OFFLINE
        return ComponentStatus.HEALTHY

    def snapshot(self) -> dict[str, Any]:
        """Return a bounded, JSON-safe observation/provenance representation."""
        successes = sum(1 for _, _, ok in self._outcomes if ok)
        failures = len(self._outcomes) - successes
        reasons: dict[str, int] = {}
        for _, reason, ok in self._outcomes:
            if not ok:
                reasons[reason] = reasons.get(reason, 0) + 1
        observed_at = self._clock()
        return {
            "name": self._name,
            "status": self.status().name,
            "window": len(self._outcomes),
            "window_max": self._outcomes.maxlen,
            "recent_successes": successes,
            "recent_failures": failures,
            "failure_reasons": dict(sorted(reasons.items())),
            "recorded_total": self._recorded_total,
            "observed_at": observed_at.isoformat(),
        }