"""Atlas Kernel — Phase 16 Autonomy Persistence Wiring Helpers.

Private helper functions used by ``Atlas._init_evolution_pipeline()`` to
wire the Phase 16 autonomy persistence infrastructure:

  ``AutonomySQLiteStorage`` → ``ScheduleStore``
  ``ApplicationEngine``     → production state adapters

These are kernel-private helpers; they are not part of the public API.
The ``AutonomyPolicy`` used for the ``ScheduleStore`` is always the
default disabled policy.  Autonomous execution remains disabled; this
wiring only makes the persistence infrastructure available for future
request lifecycle management.

The ``ApplicationEngine`` is wired with production ``StateReader`` /
``StateWriter`` adapters: readers for CONFIG/MEMORY/KNOWLEDGE/CAPABILITY
and writers for MEMORY/KNOWLEDGE only (CONFIG and CAPABILITY are
intentionally reader-only — staged-config and callable-handler governance
must not be bypassed).  Constructing the engine creates no execution path:
``apply()`` is only reachable through the governed pipeline.

No autonomy is enabled.  No ingest bridges are modified.  No governance
rules are changed.
"""

from __future__ import annotations

from typing import Any

from atlas.config.configuration import Configuration
from atlas.evolution.autonomy.adapters import (
    CapabilityStateAdapter,
    ConfigStateAdapter,
    KnowledgeStateAdapter,
    MemoryStateAdapter,
)
from atlas.evolution.autonomy.application_engine import ApplicationEngine
from atlas.evolution.autonomy.applier_registry import ApplierRegistry
from atlas.evolution.autonomy.dispatcher import EvolutionAutonomyDispatcher
from atlas.evolution.autonomy.governed_ingest_sink import GovernanceIngestSink
from atlas.evolution.autonomy.models import AutonomyPolicy
from atlas.evolution.autonomy.rollback_manager import RollbackManager
from atlas.evolution.autonomy.verification_service import VerificationService
from atlas.evolution.autonomy.version_manager import VersionManager
from atlas.evolution.autonomy.risk_assessor import EvolutionRiskAssessor
from atlas.evolution.autonomy.schedule_store import ScheduleStore
from atlas.evolution.autonomy.validator import EvolutionValidator
from atlas.evolution.governance.models import ScopeType
from atlas.events.event_bus import EventBus
from atlas.knowledge.knowledge_manager import KnowledgeManager
from atlas.memory.service.memory_manager_service import MemoryManagerService
from atlas.reasoning.execution.registry import CapabilityRegistry
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


def init_autonomy_application_engine(
    storage: AutonomySQLiteStorage,
    knowledge_manager: KnowledgeManager,
    memory_service: MemoryManagerService,
    configuration: Configuration,
    capability_registry: CapabilityRegistry,
) -> ApplicationEngine:
    """Create and return the kernel-owned Phase 16 ApplicationEngine.

    The engine is constructed with production adapters over the real
    kernel services:

    - readers: CONFIG, MEMORY, KNOWLEDGE, CAPABILITY
    - writers: MEMORY, KNOWLEDGE only (CONFIG/CAPABILITY remain
      reader-only; live config and capability registration are governed
      by staged-config / registry semantics that must not be bypassed)

    ``snapshot_storage`` is the SAME ``AutonomySQLiteStorage`` instance
    created by :func:`init_autonomy_persistence` — no second database is
    created.  ``registry`` is ``ApplierRegistry.default()``.

    The engine is kernel-private (track-private precedent) and is NOT
    registered in the ServiceContainer.  Merely constructing it creates
    no execution path: ``apply()`` is only reachable through the governed
    pipeline.

    Called by ``Atlas._init_evolution_pipeline()`` after
    :func:`init_autonomy_persistence`.
    """
    if storage is None:
        raise ValueError("AutonomySQLiteStorage is required")
    if knowledge_manager is None:
        raise ValueError("KnowledgeManager is required")
    if memory_service is None:
        raise ValueError("MemoryManagerService is required")
    if configuration is None:
        raise ValueError("Configuration is required")
    if capability_registry is None:
        raise ValueError("CapabilityRegistry is required")

    memory_adapter = MemoryStateAdapter(memory_service)
    knowledge_adapter = KnowledgeStateAdapter(knowledge_manager)
    config_adapter = ConfigStateAdapter(configuration)
    capability_adapter = CapabilityStateAdapter(capability_registry)

    readers: dict[ScopeType, Any] = {
        ScopeType.CONFIG: config_adapter,
        ScopeType.MEMORY: memory_adapter,
        ScopeType.KNOWLEDGE: knowledge_adapter,
        ScopeType.CAPABILITY: capability_adapter,
    }
    writers: dict[ScopeType, Any] = {
        ScopeType.MEMORY: memory_adapter,
        ScopeType.KNOWLEDGE: knowledge_adapter,
    }

    return ApplicationEngine(
        registry=ApplierRegistry.default(),
        snapshot_storage=storage,
        readers=readers,
        writers=writers,
    )


def init_governed_ingest_sink(
    schedule_store: ScheduleStore,
) -> GovernanceIngestSink:
    """Create and return the kernel-owned governed ingest sink.

    The sink persists bridge-produced ``EvolutionRequest`` objects as DRAFTED
    records in the existing ``ScheduleStore``. It performs structural safety
    checks only — it never validates, authorizes, or applies anything.
    One instance is shared by all four track ingest bridges.

    Called by ``Atlas._init_evolution_pipeline()`` after ``ScheduleStore``
    exists; the resulting kernel-private instance is then injected into the
    four existing ingest bridges. Not registered in ServiceContainer.
    """
    if schedule_store is None:
        raise ValueError("ScheduleStore is required")
    return GovernanceIngestSink(schedule_store=schedule_store)

def init_autonomy_dispatcher(
    schedule_store: ScheduleStore,
    execution_gateway: Any,
    application_engine: Any | None = None,
    storage: Any | None = None,
    audit_callback: Any | None = None,
    state_version_provider: Any | None = None,
) -> EvolutionAutonomyDispatcher:
    """Create and return the kernel-owned governed lifecycle dispatcher.

    The dispatcher consumes DRAFTED requests from ``schedule_store``, advances
    them through Validator → RiskAssessor → PENDING_AUTHORIZATION (a hard
    production terminus — no authorization is ever minted here), and applies
    pre-authorized SCHEDULED requests ONLY through ``execution_gateway``.

    When ``application_engine`` and ``storage`` (the shared
    ``AutonomySQLiteStorage``) are provided, Batch 15 also wires the existing
    post-application lifecycle services — VerificationService, RollbackManager
    and VersionManager — so a request reaches a verified, versioned,
    outcome-recorded terminal state instead of a bare status splice.

    ``execution_gateway`` already carries the ApplicationEngine and the
    AutonomyRequestAdapter injected by the kernel; the dispatcher never holds
    or imports the engine (Phase 16 D15).

    Args:
        schedule_store: the kernel-owned ScheduleStore (same instance reused
            by the governed ingest sink).
        execution_gateway: the wired EvolutionExecutionGateway exposing
            ``execute_request``.
        application_engine: the wired ApplicationEngine whose registry/readers/
            writers are reused by VerificationService and RollbackManager.
        storage: the shared ``AutonomySQLiteStorage`` (request/snapshot/outcome/
            version persistence).
        audit_callback: optional audit record consumer (kernel-provided).
        state_version_provider: optional current-state-version callable used
            by ScheduleStore atomic claiming. Defaults to ``""``.

    Called by ``Atlas._init_evolution_pipeline()`` after the gateway and
    application engine exist. Kernel-private; not registered in ServiceContainer.
    """
    if schedule_store is None:
        raise ValueError("ScheduleStore is required")
    if execution_gateway is None:
        raise ValueError("EvolutionExecutionGateway is required")

    verification_service = None
    rollback_manager = None
    version_manager = None
    outcome_store = None

    if application_engine is not None and storage is not None:
        version_manager = VersionManager(storage=storage)
        readers = getattr(application_engine, "readers", None) or {}
        writers = getattr(application_engine, "writers", None) or {}
        registry = getattr(application_engine, "registry", None)
        verification_service = VerificationService(
            registry=registry,
            readers=readers,
            snapshot_store=storage,
        )
        rollback_manager = RollbackManager(
            request_store=storage,
            snapshot_store=storage,
            outcome_store=storage,
            version_manager=version_manager,
            writers=writers,
        )
        outcome_store = storage

    return EvolutionAutonomyDispatcher(
        schedule_store=schedule_store,
        validator=EvolutionValidator(),
        risk_assessor=EvolutionRiskAssessor(),
        execution_gateway=execution_gateway,
        verification_service=verification_service,
        rollback_manager=rollback_manager,
        version_manager=version_manager,
        outcome_store=outcome_store,
        audit_callback=audit_callback,
        state_version_provider=state_version_provider,
    )