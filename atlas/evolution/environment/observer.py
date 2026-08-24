"""Atlas Post-Core F1 — Environment Observer.

The ``EnvironmentObserver`` is the orchestration seam of the F1 foundation.
One cycle:

  1. Run every registered ``EnvironmentProvider.observe()`` (fail-closed).
  2. Normalize + deduplicate entity states (deterministic identity key).
  3. Sanitize state values (secret/credential filtering).
  4. Compare against the last-known snapshot (deterministic detector).
  5. Update the last-known snapshot (dedup across cycles).
  6. Emit ``environment.changed`` on the EXISTING EventBus (when configured).
  7. Record observations into the EXISTING SelfObservationEngine (when
     configured) via its ``record_observation`` surface.

Nothing here approves, mutates, executes proposals, or touches the real
repository. ``observe_cycle()`` is a scheduler-compatible no-arg callable.

Pure infrastructure. No governance. No AI. No kernel access.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Mapping

from atlas.evolution.environment.detector import EnvironmentChangeDetector
from atlas.evolution.environment.models import (
    EnvironmentChangeType,
    EnvironmentObservationResult,
    EnvironmentProviderFailure,
    EnvironmentState,
)
from atlas.evolution.environment.providers import EnvironmentProvider

#: Event name published on the existing EventBus for environment changes.
ENVIRONMENT_CHANGED_EVENT: str = "environment.changed"

#: Upper bound on recorded provider failures per cycle (bounded results).
MAX_FAILURES_PER_CYCLE: int = 100

#: Credential markers matched against WORD TOKENS of a state key (never
#: substring matching). ``max_tokens`` is therefore NOT considered secret
#: (its token is ``TOKENS``, not ``TOKEN``).
_SECRET_MARKERS: frozenset[str] = frozenset({
    "KEY", "SECRET", "PASSWORD", "PASSWD", "TOKEN", "CREDENTIAL",
    "AUTHORIZATION", "AUTH", "PRIVATE", "BEARER",
})

#: CamelCase splitter (handles ``apiKey``, ``AccessToken``, ``authSecret``).
_CAMEL_SPLIT = re.compile(
    r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+"
)


def _text_tokens(key: str) -> set[str]:
    """Return uppercased word tokens of a key (separator + camelCase split)."""
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", str(key))
    tokens: set[str] = set()
    for part in normalized.split("_"):
        if not part:
            continue
        for token in _CAMEL_SPLIT.findall(part):
            tokens.add(token.upper())
    return tokens


def _is_secret_key(key: str) -> bool:
    """True when a state/metadata key looks credential-bearing.

    Matching is per word token, so ``max_tokens`` / ``maxTokens`` are NOT
    treated as secrets while ``api_key`` / ``Authorization`` are.
    """
    return bool(_text_tokens(key) & _SECRET_MARKERS)


def sanitize_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return a secret-free, JSON-safe copy of a state mapping.

    Only keys that do not look like credentials are kept; values are reduced
    to their primitive form (str/int/float/bool/None). Nested mappings are
    sanitized recursively with bounded depth.
    """
    return _sanitize_value(state, depth=0)


def _sanitize_value(value: Any, depth: int) -> Any:
    if depth > 4:
        return None
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _is_secret_key(key):
                continue
            out[str(key)] = _sanitize_value(item, depth + 1)
        return out
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item, depth + 1) for item in list(value)[:256]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    # Enums and other objects -> name/string fallback (never raw object).
    name = getattr(value, "name", None)
    return name if name is not None else str(value)


class EnvironmentObserver:
    """Runs environment providers and produces normalized change records.

    Args:
        providers: Optional initial list of ``EnvironmentProvider`` instances.
        event_bus: Optional EXISTING EventBus (or any object exposing
            ``publish(name, payload)``). No new event bus is created.
        observation_engine: Optional EXISTING ``SelfObservationEngine`` (or any
            object exposing ``record_observation(observation)``).
        detector: Optional change detector; defaults to a fresh
            ``EnvironmentChangeDetector``.
        now: Optional clock callable (tests); defaults to ``datetime.now``.
    """

    def __init__(
        self,
        providers: list[EnvironmentProvider] | None = None,
        event_bus: Any | None = None,
        observation_engine: Any | None = None,
        detector: EnvironmentChangeDetector | None = None,
        now: Any | None = None,
    ) -> None:
        self._providers: list[EnvironmentProvider] = list(providers or [])
        self._event_bus = event_bus
        self._observation_engine = observation_engine
        self._detector = detector or EnvironmentChangeDetector()
        self._now = now or datetime.now

        self._last_known: dict[str, EnvironmentState] = {}
        self._cycle_number = 0
        self._last_result: EnvironmentObservationResult | None = None

    # ------------------------------------------------------------------
    # Provider management
    # ------------------------------------------------------------------

    @property
    def provider_names(self) -> list[str]:
        """Sorted names of registered providers."""
        return sorted(p.provider_name() for p in self._providers)

    @property
    def cycle_number(self) -> int:
        """Number of completed observation cycles (0 before first run)."""
        return self._cycle_number

    @property
    def last_result(self) -> EnvironmentObservationResult | None:
        """Most recent cycle result, or None if never run."""
        return self._last_result

    def register(self, provider: EnvironmentProvider) -> None:
        """Register an additional environment provider.

        Raises:
            ValueError: If a provider with the same ``provider_name`` is
                already registered.
        """
        name = provider.provider_name()
        if any(p.provider_name() == name for p in self._providers):
            raise ValueError(f"Provider '{name}' is already registered.")
        self._providers.append(provider)

    # ------------------------------------------------------------------
    # Observation cycle (scheduler-compatible)
    # ------------------------------------------------------------------

    def observe_cycle(self) -> EnvironmentObservationResult:
        """Run one bounded observation cycle; returns a structured result.

        Scheduler-compatible no-arg callable: a future scheduler (or an
        explicit caller) may invoke this directly. It never raises for a
        provider failure and never mutates anything.
        """
        self._cycle_number += 1
        cycle_id = f"ENV-{self._cycle_number:04d}"
        ran_at = self._now()

        failures: list[EnvironmentProviderFailure] = []
        current: dict[str, EnvironmentState] = {}

        for provider in self._providers:
            try:
                states = provider.observe()
            except Exception as exc:  # fail-closed, bounded
                failures.append(EnvironmentProviderFailure(
                    provider_name=provider.provider_name(),
                    error=_bounded_error(exc),
                    occurred_at=ran_at,
                ))
                continue
            for state in states or []:
                if not isinstance(state, EnvironmentState):
                    failures.append(EnvironmentProviderFailure(
                        provider_name=provider.provider_name(),
                        error=(
                            "provider returned a non-EnvironmentState value: "
                            f"{type(state).__name__}"
                        ),
                        occurred_at=ran_at,
                    ))
                    continue
                self._merge_state(current, state)

        if len(failures) > MAX_FAILURES_PER_CYCLE:
            failures = failures[:MAX_FAILURES_PER_CYCLE]

        changes = self._detector.compare(self._last_known, current)
        self._last_known = current

        result = EnvironmentObservationResult(
            cycle_id=cycle_id,
            ran_at=ran_at,
            changes=tuple(changes),
            failures=tuple(failures),
            provider_count=len(self._providers),
            observed_count=len(current),
            success=not failures,
        )
        self._last_result = result

        self._emit_event(result)
        self._record_observations(result)
        return result

    def observe(self) -> EnvironmentObservationResult:
        """Alias of ``observe_cycle`` for convenience."""
        return self.observe_cycle()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_state(
        current: dict[str, EnvironmentState],
        state: EnvironmentState,
    ) -> None:
        """Insert a sanitized state; first provider wins on duplicate key."""
        key = state.key
        if key in current:
            return
        current[key] = EnvironmentState(
            entity=state.entity,
            state=sanitize_state(state.state),
            source=state.source or "unknown",
            observed_at=state.observed_at,
            reliability=state.reliability,
            metadata=sanitize_state(state.metadata),
        )

    def _emit_event(self, result: EnvironmentObservationResult) -> None:
        """Publish non-UNCHANGED changes on the existing EventBus."""
        if self._event_bus is None:
            return
        significant = [
            c.to_dict()
            for c in result.changes
            if c.change_type != EnvironmentChangeType.UNCHANGED
        ]
        if not significant:
            return
        payload = {
            "cycle_id": result.cycle_id,
            "ran_at": result.ran_at.isoformat(),
            "changes": significant,
            "success": result.success,
        }
        try:
            publish = getattr(self._event_bus, "publish", None)
            if publish is not None:
                publish(ENVIRONMENT_CHANGED_EVENT, payload)
        except Exception:  # observation events must never break the cycle
            pass

    def _record_observations(self, result: EnvironmentObservationResult) -> None:
        """Bridge changes into the existing observation engine (best-effort)."""
        engine = self._observation_engine
        if engine is None:
            return
        record = getattr(engine, "record_observation", None)
        if record is None:
            return
        for change in result.changes:
            if change.change_type == EnvironmentChangeType.UNCHANGED:
                continue
            observation = self._build_observation(change)
            try:
                record(observation)
            except Exception:
                continue

    def _build_observation(self, change: Any) -> Any:
        """Build an existing ``Observation`` record from an environment change.

        The import is deferred so the F1 package stays importable even if the
        learning/evolution layer changes; the observer is intentionally duck
        typed against the existing ``SelfObservationEngine`` surface.
        """
        from atlas.evolution.models import Observation, ObservationCategory

        return Observation(
            category=ObservationCategory.SYSTEM_HEALTH,
            metric_name=f"environment:{change.entity.key}",
            value=dict(change.current or change.previous or {}),
            unit="state",
            description=(
                f"Environment {change.change_type.name} "
                f"{change.entity.key} via {change.source or 'unknown'}."
            ),
            timestamp=change.observed_at,
            source="environment_observer",
            metadata={"change_type": change.change_type.name},
        )


def _bounded_error(exc: Exception, limit: int = 200) -> str:
    """Bounded, secret-free error message for a provider failure."""
    text = str(exc).strip() or type(exc).__name__
    return text[:limit]