"""Atlas Kernel — Phase 16 Autonomy Persistence Wiring Helpers.

Private helper functions used by ``Atlas._init_evolution_pipeline()`` to
wire the Phase 16 autonomy persistence infrastructure:

  ``AutonomySQLiteStorage`` → ``ScheduleStore``

These are kernel-private helpers; they are not part of the public API.
The ``AutonomyPolicy`` used for the ``ScheduleStore`` is always the
default disabled policy.  Autonomous execution remains disabled; this
wiring only makes the persistence infrastructure available for future
request lifecycle management.

No autonomy is enabled.  No ingest bridges are modified.  No governance
rules are changed.  No application engine is wired.
"""

from __future__ import annotations

from typing import Any

from atlas.evolution.autonomy.models import AutonomyPolicy
from atlas.evolution.autonomy.schedule_store import ScheduleStore
from atlas.events.event_bus import EventBus
from atlas.storage.autonomy_storage import AutonomySQLiteStorage


def init_autonomy_persistence(
    event_bus: EventBus,
) -> tuple[AutonomySQLiteStorage | None, ScheduleStore | None]:
    """Create, initialize, and return the Phase 16 autonomy persistence pair.

    Returns a ``(storage, schedule_store)`` tuple.  Either element may be
    ``None`` if the storage adapter fails to initialize (graceful
    degradation, same pattern as other storage adapters).

    The ``ScheduleStore`` receives a default **disabled** ``AutonomyPolicy``.
    Autonomous execution remains disabled; this wiring only makes the
    persistence infrastructure available.

    Called by ``Atlas._init_evolution_pipeline()``.
    """
    storage = AutonomySQLiteStorage()
    storage.initialize()

    if storage.is_available():
        event_bus.publish(
            "autonomy.storage.initialized",
            {"db_path": str(storage._db_path)},
        )
        store = ScheduleStore(
            storage=storage,
            policy=AutonomyPolicy(),  # disabled by default — no autonomy
        )
    else:
        event_bus.publish(
            "autonomy.storage.unavailable",
            {"mode": "memory_only"},
        )
        store = None

    return storage, store


def shutdown_autonomy_persistence(
    storage: AutonomySQLiteStorage | None,
) -> None:
    """Close the autonomy storage connection cleanly.

    Called by ``Atlas.shutdown()``.
    """
    if storage is not None:
        try:
            storage.close()
        except Exception:
            pass
