"""Phase 9.4 — Atlas-owned change generation: evidence contract.

Investigation result: Atlas generates its own concrete change (a capability-
handler module + a self-verifying test) deterministically from an authorized
development plan via ``ScaffoldChangeSupplier`` — no external code-generation
service and no LLM. The change is represented as an explicit, reviewable,
bounded ``CodeChangeSet``.

Honest limitation: generation is bounded to the supported deterministic change
classes; arbitrary open-ended synthesis is not implemented (and must not be
solved by an external model).
"""

from __future__ import annotations

import pytest

from atlas.evolution.autonomy.code_sandbox import CodeChangeSet
from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier


def _supplied(module="atlas/example/widget_handlers.py", capability="example.widget"):
    return ScaffoldChangeSupplier().supply_changes(
        DevelopmentNeed(
            title="t",
            metadata={"scaffold": {"module": module, "capability_name": capability}},
        )
    )


class TestPhase94ChangeGeneration:
    def test_generated_change_forms_a_valid_code_change_set(self):
        supplied = _supplied()
        change_set = CodeChangeSet.from_payload(
            {"code_changes": [{"path": p, "content": c} for p, c in supplied.code_changes]}
        )
        assert change_set.changes
        assert change_set.changes[0].path == "atlas/example/widget_handlers.py"
        assert 'CAPABILITY_NAME = "example.widget"' in change_set.changes[0].content

    def test_generation_is_deterministic(self):
        assert _supplied().code_changes == _supplied().code_changes
        assert _supplied().test_files == _supplied().test_files

    def test_generation_refuses_architecture_sensitive_targets(self):
        with pytest.raises(ValueError):
            _supplied(module="atlas/kernel/evil.py", capability="x.y")

    def test_generated_change_is_bounded_and_reviewable(self):
        supplied = _supplied()
        assert supplied.origin == "deterministic-scaffold"
        assert supplied.confidence == 1.0
        assert supplied.notes
        assert len(supplied.code_changes) == 1  # bounded
