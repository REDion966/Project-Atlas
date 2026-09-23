"""Phase 13 test support (not collected: no ``test_`` prefix).

Shared, honest builders for Phase 13 continuity tests:

* :func:`record_outcome` writes an ``evolution_outcome`` record in exactly the
  shape Phase 11 persists (same metadata keys);
* :func:`sqlite_memory` wires the EXISTING durable storage adapter;
* :func:`run_cycle` runs a real bounded Phase-11 cycle.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.development_cycle import SuppliedChanges
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import EvolutionRecord
from atlas.evolution.self_evolution import SelfEvolutionLoop
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry


def candidate(subject: str, *, verdict: DiscoveryVerdict = DiscoveryVerdict.ACTIONABLE_GAP):
    """Return a Phase-10 ``(candidate, assessment)`` pair for ``subject``."""
    evidence = (f"capability_model:{subject}",)
    discovery = CapabilityDiscoveryCandidate(
        candidate_id=f"disc:{subject}",
        kind=DiscoverySignalKind.UNAVAILABLE_CAPABILITY,
        subject=subject,
        sources=("capability_model",),
        evidence=evidence,
    )
    assessment = DiscoveryAssessment(
        candidate_id=f"disc:{subject}",
        subject=subject,
        verdict=verdict,
        rationale="evidence-backed",
        evidence=evidence,
        research_question=f"what is required to {subject}",
    )
    return discovery, assessment


def outcome_record_id(cycle_id: str, subject: str, proposal_id: str, kind: str) -> str:
    """Reproduce the Phase-11 durable outcome record identity."""
    seed = f"{cycle_id}:{subject}:{proposal_id}:{kind}"
    return f"EVO-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


def record_outcome(
    memory: Any,
    *,
    cycle_id: str,
    subject: str,
    terminal: str,
    outcome_kind: str,
    proposal_id: str = "",
    record_id: str = "",
    related: Iterable[str] = (),
) -> EvolutionRecord:
    """Persist one ``evolution_outcome`` record in the Phase-11 shape."""
    record = EvolutionRecord(
        record_id=record_id
        or outcome_record_id(cycle_id, subject, proposal_id, outcome_kind),
        event_type="evolution_outcome",
        description=(
            f"Self-evolution cycle {cycle_id} terminated as '{terminal}' "
            f"({outcome_kind})."
        ),
        related_ids=[i for i in (proposal_id, *related) if i],
        metadata={
            "cycle_id": cycle_id,
            "terminal": terminal,
            "outcome_kind": outcome_kind,
            "subject": subject,
        },
    )
    memory.store_record(record)
    return record


def sqlite_memory(tmp_path: Path, name: str = "phase13_evolution.db"):
    """Return ``(memory, storage)`` backed by the EXISTING SQLite adapter."""
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    storage = SQLiteEvolutionStorage(db_path=tmp_path / name)
    storage.initialize()
    memory = EvolutionMemory(storage=storage)
    return memory, storage


def run_cycle(
    memory: Any,
    tmp_path: Path,
    *,
    subject: str,
    capability: str,
    module: str,
    owner_approved: bool = True,
    promotion_authorized: bool = True,
    supplier: Any = None,
    repo_root: Path | None = None,
):
    """Run ONE real bounded Phase-11 evolution cycle."""
    loop = SelfEvolutionLoop(
        change_supplier=supplier,
        evolution_memory=memory,
        component_registry=ComponentRegistry(),
        capability_registry=CapabilityRegistry(),
        repo_root=repo_root if repo_root is not None else tmp_path,
    )
    return loop.run(
        *candidate(subject),
        target_module=module,
        capability_name=capability,
        capability_names=(),
        owner_approved=owner_approved,
        promotion_authorized=promotion_authorized,
    )


class FailingSupplier:
    """Deterministic supplier whose sandbox test always fails."""

    def __init__(self, module: str = "atlas/example/failing_handlers.py") -> None:
        self._module = module

    @property
    def module(self) -> str:
        return self._module

    def supply_changes(self, need: Any) -> SuppliedChanges:  # noqa: ARG002
        stem = Path(self._module).stem
        return SuppliedChanges(
            code_changes=((self._module, "VALUE = 1\n"),),
            test_files=((f"tests/test_{stem}.py", "def test_x():\n    assert False\n"),),
            origin="test",
        )
