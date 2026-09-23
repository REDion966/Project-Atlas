"""Phase 9.6 — Self-directed test selection: evidence contract.

Investigation result: Atlas already selects its own relevant tests
deterministically (``select_relevant_tests``) and can carry an explicit
``verify_target`` in the ``SandboxWorkload``; no test-generation model is used.
"""

from __future__ import annotations

from atlas.evolution.development_models import SandboxWorkload
from atlas.evolution.development_test_selection import select_relevant_tests


class TestPhase96TestSelection:
    def test_selects_relevant_tests_by_convention(self):
        selected = select_relevant_tests(
            ["atlas/evolution/development_verification.py"],
            ["tests/test_development_verification.py", "tests/test_other.py"],
        )
        assert selected == ("tests/test_development_verification.py",)

    def test_no_relevant_test_is_an_honest_empty(self):
        # Atlas must not fabricate a test: no match yields no test.
        assert select_relevant_tests(["atlas/x.py"], ["tests/test_unrelated.py"]) == ()

    def test_selection_is_deterministic_and_bounded(self):
        available = ["tests/test_x.py", "tests/test_x_extra.py", "tests/test_other.py"]
        first = select_relevant_tests(["x.py"], available, max_tests=2)
        assert select_relevant_tests(["x.py"], available, max_tests=2) == first
        assert len(first) <= 2

    def test_workload_can_pin_an_explicit_verify_target(self):
        workload = SandboxWorkload(
            code_changes=({"path": "atlas/x.py", "content": "VALUE = 1\n"},),
            test_files={"tests/test_x.py": "def test_ok():\n    assert True\n"},
            verify_target="tests/test_x.py",
        )
        assert workload.verify_target == "tests/test_x.py"
