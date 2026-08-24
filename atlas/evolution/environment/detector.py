"""Atlas Post-Core F1 — Deterministic Environment Change Detector.

Compares a previous observation snapshot with a current snapshot and produces
normalized ``EnvironmentChange`` records.

The comparison is fully deterministic: states are canonicalized to a stable
JSON string (``json.dumps(sort_keys=True)``) before comparison, so dict
ordering and value types never affect the result. Detection ordering is
stable by entity key.

Pure logic. No infrastructure. No AI.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from atlas.evolution.environment.models import (
    EnvironmentChange,
    EnvironmentChangeType,
    EnvironmentEntity,
    EnvironmentState,
)


def canonicalize(state: Mapping[str, Any]) -> str:
    """Return a stable, order-independent serialization of a state mapping.

    ``default=str`` keeps non-JSON primitives (e.g. enums) comparable without
    raising, while tuples/dicts/lists are recursively sorted by key.
    """
    return json.dumps(state, sort_keys=True, default=str, separators=(",", ":"))


class EnvironmentChangeDetector:
    """Compare two snapshots and emit deterministic change records."""

    def compare(
        self,
        previous: Mapping[str, EnvironmentState],
        current: Mapping[str, EnvironmentState],
    ) -> list[EnvironmentChange]:
        """Compare ``previous`` and ``current`` snapshots keyed by entity key.

        Args:
            previous: Last-known state mapping (entity.key → EnvironmentState).
            current: Newly observed state mapping (entity.key → EnvironmentState).

        Returns:
            A list of ``EnvironmentChange`` records, sorted by entity key.
            Every entity present in either snapshot is reported (ADDED,
            REMOVED, CHANGED, or UNCHANGED).

        Raises:
            TypeError: If a value is not an ``EnvironmentState``.
        """
        previous_keys: set[str] = set(previous)
        current_keys: set[str] = set(current)

        changes: list[EnvironmentChange] = []

        for entity_key in sorted(previous_keys | current_keys):
            prior = previous.get(entity_key)
            now = current.get(entity_key)

            if prior is not None and not isinstance(prior, EnvironmentState):
                raise TypeError(
                    f"Snapshot value for '{entity_key}' is not EnvironmentState"
                )
            if now is not None and not isinstance(now, EnvironmentState):
                raise TypeError(
                    f"Snapshot value for '{entity_key}' is not EnvironmentState"
                )

            changes.append(self._classify(entity_key, prior, now))

        return changes

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify(
        entity_key: str,
        prior: EnvironmentState | None,
        now: EnvironmentState | None,
    ) -> EnvironmentChange:
        if prior is None and now is not None:
            return EnvironmentChange(
                entity=now.entity,
                change_type=EnvironmentChangeType.ADDED,
                previous=None,
                current=dict(now.state),
                observed_at=now.observed_at,
                source=now.source,
                reliability=now.reliability,
                metadata={"provider": now.source},
            )

        if prior is not None and now is None:
            return EnvironmentChange(
                entity=prior.entity,
                change_type=EnvironmentChangeType.REMOVED,
                previous=dict(prior.state),
                current=None,
                observed_at=prior.observed_at,
                source=prior.source,
                reliability=prior.reliability,
                metadata={"provider": prior.source},
            )

        assert prior is not None and now is not None  # both sides present

        if canonicalize(prior.state) == canonicalize(now.state):
            return EnvironmentChange(
                entity=now.entity,
                change_type=EnvironmentChangeType.UNCHANGED,
                previous=dict(prior.state),
                current=dict(now.state),
                observed_at=now.observed_at,
                source=now.source,
                reliability=now.reliability,
                metadata={"provider": now.source, "unchanged": True},
            )

        return EnvironmentChange(
            entity=now.entity,
            change_type=EnvironmentChangeType.CHANGED,
            previous=dict(prior.state),
            current=dict(now.state),
            observed_at=now.observed_at,
            source=now.source,
            reliability=now.reliability,
            metadata={
                "provider": now.source,
                "changed_fields": EnvironmentChangeDetector._diff_fields(
                    prior.state, now.state,
                ),
            },
        )

    @staticmethod
    def _diff_fields(
        earlier: Mapping[str, Any],
        later: Mapping[str, Any],
    ) -> list[str]:
        """Return sorted keys whose canonical value changed (or appearance)."""
        changed: set[str] = set()
        for key in set(earlier) | set(later):
            if canonicalize({key: earlier.get(key)}) != canonicalize({key: later.get(key)}):
                changed.add(key)
        return sorted(changed)