"""Phase 9.3 — Change design independence: evidence contract.

Investigation result: Atlas already designs concrete intended changes itself via
the existing ``DeterministicChangeSupplier`` / ``ScaffoldChangeSupplier`` /
``CompositeChangeSupplier`` — no external coding agent is involved.
"""

from __future__ import annotations

from atlas.evolution.development_cycle import (
    DeterministicChangeSupplier,
    DevelopmentNeed,
    SuppliedChanges,
)
from atlas.evolution.development_scaffold_supplier import (
    CompositeChangeSupplier,
    ScaffoldChangeSupplier,
)


def _scaffold_need():
    return DevelopmentNeed(
        title="t",
        metadata={
            "scaffold": {
                "module": "atlas/example/widget_handlers.py",
                "capability_name": "example.widget",
            }
        },
    )


class TestPhase93ChangeDesignIndependence:
    def test_deterministic_supplier_designs_from_supplied_content(self):
        need = DevelopmentNeed(
            title="t",
            metadata={"code_changes": [{"path": "atlas/x.py", "content": "VALUE = 1\n"}]},
        )
        supplied = DeterministicChangeSupplier().supply_changes(need)
        assert isinstance(supplied, SuppliedChanges)
        assert supplied.origin == "deterministic"
        assert supplied.code_changes == (("atlas/x.py", "VALUE = 1\n"),)

    def test_scaffold_supplier_designs_a_capability_change(self):
        supplied = ScaffoldChangeSupplier().supply_changes(_scaffold_need())
        assert supplied.origin == "deterministic-scaffold"
        assert supplied.code_changes
        assert supplied.test_files

    def test_composite_prefers_supplied_then_scaffold(self):
        composite = CompositeChangeSupplier(
            [DeterministicChangeSupplier(), ScaffoldChangeSupplier()]
        )
        supplied_need = DevelopmentNeed(
            title="t",
            metadata={"code_changes": [{"path": "atlas/x.py", "content": "VALUE = 1\n"}]},
        )
        assert composite.supply_changes(supplied_need).origin == "deterministic"
        assert composite.supply_changes(_scaffold_need()).origin == "deterministic-scaffold"

    def test_design_fails_closed_without_any_authoring_input(self):
        composite = CompositeChangeSupplier(
            [DeterministicChangeSupplier(), ScaffoldChangeSupplier()]
        )
        assert composite.supply_changes(DevelopmentNeed(title="t")) is None
