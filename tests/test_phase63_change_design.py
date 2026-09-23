"""Phase 6.3 — Change design: evidence contract.

Investigation result: Atlas already represents a proposed change before
implementation, so no autonomous code-generation framework was introduced.

* ``SuppliedChanges`` — the bounded, draft change design
  (code_changes, test_files, origin, confidence, notes).
* ``DeterministicChangeSupplier`` — reads explicitly supplied design content.
* ``ScaffoldChangeSupplier`` — deterministically authors ONE supported change
  class (a capability-handler factory module + a sandbox self-verifying test)
  from a structured spec; refuses architecture-sensitive targets.

A design is data only: it is never applied to the repository by authoring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.evolution.development_cycle import (
    DeterministicChangeSupplier,
    DevelopmentNeed,
    SuppliedChanges,
)
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier

_REPO_ROOT = Path(__file__).resolve().parents[1]


class TestPhase63ChangeDesign:
    def test_deterministic_supplier_reads_supplied_changes(self):
        need = DevelopmentNeed(
            title="t",
            metadata={
                "code_changes": [{"path": "atlas/x.py", "content": "VALUE = 1\n"}],
                "test_files": {"tests/test_x.py": "def test_a():\n    assert True\n"},
            },
        )
        supplied = DeterministicChangeSupplier().supply_changes(need)
        assert isinstance(supplied, SuppliedChanges)
        assert supplied.code_changes == (("atlas/x.py", "VALUE = 1\n"),)
        assert supplied.test_files == (
            ("tests/test_x.py", "def test_a():\n    assert True\n"),
        )
        assert supplied.origin == "deterministic"

    def test_supplier_returns_none_without_a_design(self):
        assert DeterministicChangeSupplier().supply_changes(
            DevelopmentNeed(title="t")
        ) is None

    def test_scaffold_authors_a_capability_module_and_test(self):
        need = DevelopmentNeed(
            title="t",
            metadata={
                "scaffold": {
                    "module": "atlas/example/widget_handlers.py",
                    "capability_name": "example.widget",
                }
            },
        )
        supplied = ScaffoldChangeSupplier().supply_changes(need)
        assert supplied is not None
        assert supplied.origin == "deterministic-scaffold"
        assert supplied.code_changes[0][0] == "atlas/example/widget_handlers.py"
        assert 'CAPABILITY_NAME = "example.widget"' in supplied.code_changes[0][1]
        assert supplied.test_files[0][0].startswith("tests/")

    def test_scaffold_refuses_architecture_sensitive_target(self):
        need = DevelopmentNeed(
            title="t",
            metadata={
                "scaffold": {
                    "module": "atlas/kernel/evil.py",
                    "capability_name": "x.y",
                }
            },
        )
        with pytest.raises(ValueError):
            ScaffoldChangeSupplier().supply_changes(need)

    def test_design_is_draft_and_not_applied_to_the_repository(self):
        need = DevelopmentNeed(
            title="t",
            metadata={
                "scaffold": {
                    "module": "atlas/example/widget_handlers.py",
                    "capability_name": "example.widget",
                }
            },
        )
        supplied = ScaffoldChangeSupplier().supply_changes(need)
        assert supplied is not None
        # The design is a data artifact; authoring never writes to the real repo.
        assert not (_REPO_ROOT / "atlas/example/widget_handlers.py").exists()
