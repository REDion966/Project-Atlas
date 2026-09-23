"""Phase 6.5 — Test generation/selection: evidence contract.

Investigation result: the Development Engine already selects relevant tests
deterministically and can deterministically author a bounded test for the ONE
supported scaffold change class; no LLM-based test generator was introduced.

* ``atlas/evolution/development_test_selection.py::select_relevant_tests`` —
  deterministic, bounded change→test selection by the repo naming convention;
  used by ``SelfDevelopmentLoop`` to choose the sandbox VERIFY target.
* ``ScaffoldChangeSupplier`` — authors a sandbox self-verifying test for the
  scaffolded capability (deterministic generation, not arbitrary).
* ``SandboxWorkload`` — carries ``test_files`` and an optional ``verify_target``.
"""

from __future__ import annotations

from atlas.evolution.development_models import SandboxWorkload
from atlas.evolution.development_test_selection import select_relevant_tests


class TestPhase65TestSelection:
    def test_selects_tests_by_naming_convention(self):
        selected = select_relevant_tests(
            ["atlas/evolution/development_verification.py"],
            ["tests/test_development_verification.py", "tests/test_other.py"],
        )
        assert selected == ("tests/test_development_verification.py",)

    def test_honest_empty_when_nothing_matches(self):
        assert select_relevant_tests(["atlas/x.py"], ["tests/test_unrelated.py"]) == ()

    def test_selection_is_bounded_and_deterministic(self):
        available = ["tests/test_x.py", "tests/test_x_extra.py", "tests/test_other.py"]
        first = select_relevant_tests(["x.py"], available, max_tests=1)
        assert len(first) == 1
        assert select_relevant_tests(["x.py"], available, max_tests=1) == first

    def test_malformed_input_never_raises(self):
        assert select_relevant_tests([], ["tests/test_x.py"]) == ()
        assert select_relevant_tests(["x.py"], [None, 1, ""]) == ()

    def test_workload_represents_tests_and_verify_target(self):
        workload = SandboxWorkload(
            code_changes=({"path": "atlas/x.py", "content": "VALUE = 1\n"},),
            test_files={"tests/test_x.py": "def test_a():\n    assert True\n"},
            verify_target="tests/test_x.py",
        )
        assert workload.verify_target == "tests/test_x.py"
        assert "tests/test_x.py" in workload.test_files

    def test_scaffold_generates_a_self_verifying_test(self):
        from atlas.evolution.development_cycle import DevelopmentNeed
        from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier

        supplied = ScaffoldChangeSupplier().supply_changes(
            DevelopmentNeed(
                title="t",
                metadata={
                    "scaffold": {
                        "module": "atlas/example/widget_handlers.py",
                        "capability_name": "example.widget",
                    }
                },
            )
        )
        assert supplied is not None
        (path, content), = supplied.test_files
        assert path.startswith("tests/")
        assert "def test_" in content
