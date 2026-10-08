"""Command 2 (W4/A3) — the held-out author/repair verification boundary."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from atlas.evolution.change_author_router import (  # noqa: E402
    verification_expectations,
)
from atlas.evolution.held_out_context import (  # noqa: E402
    FAILURE_CATEGORIES,
    HELD_OUT_TESTS_KEY,
    REDACTION,
    SAFE_METADATA_KEY,
    HeldOutBoundary,
    abstract_failure_category,
    boundary_of,
    held_out_paths,
    safe_context,
    safe_metadata,
    safe_verification_tests,
)

HELD_OUT_PATH = "tests/test_target.py"
HELD_OUT_SOURCE = (
    "def test_expected_value():\n"
    "    assert compute() == 4242\n"
    "\n"
    "\n"
    "def test_expected_edge():\n"
    "    assert compute(0) == 0\n"
)
SAFE_PATH = "pkg/core.py"
SAFE_SOURCE = "def compute(value=1):\n    return value\n"


def _failed_status():
    from atlas.evolution.development_models import DevelopmentOutcomeStatus

    return DevelopmentOutcomeStatus.FAILED


class _Outcome:
    def __init__(self, test_outcome="failed"):
        self.test_outcome = test_outcome


def _boundary():
    return boundary_of(
        metadata={HELD_OUT_TESTS_KEY: [HELD_OUT_PATH]},
        sources={HELD_OUT_PATH: HELD_OUT_SOURCE},
    )


class TestHeldOutClassification:
    def test_plan_marks_its_selected_tests_held_out(self):
        expectation = verification_expectations("pkg/core", ["tests.test_target"])
        assert expectation.held_out is True
        assert expectation.to_dict()["held_out"] is True

    def test_an_empty_verification_set_holds_nothing_out(self):
        expectation = verification_expectations("pkg/core", [])
        assert expectation.held_out is False

    def test_paths_come_only_from_explicit_classification(self):
        assert held_out_paths(None, {}) == frozenset()
        assert held_out_paths(None, {HELD_OUT_TESTS_KEY: [HELD_OUT_PATH]}) == frozenset(
            {HELD_OUT_PATH}
        )

    def test_dotted_and_path_forms_both_exclude(self):
        boundary = _boundary()
        assert boundary.excludes(HELD_OUT_PATH)
        assert boundary.excludes("tests.test_target")

    def test_boundary_is_inert_without_classification(self):
        assert not HeldOutBoundary().active


class TestAuthoringContextBoundary:
    def test_held_out_source_is_absent_from_the_context(self):
        context = safe_context(
            {SAFE_PATH: SAFE_SOURCE, HELD_OUT_PATH: HELD_OUT_SOURCE}, _boundary()
        )
        assert HELD_OUT_PATH not in context
        assert "4242" not in "".join(context.values())

    def test_held_out_assertions_cannot_leak_through_a_surviving_value(self):
        context = safe_context(
            {
                SAFE_PATH: SAFE_SOURCE,
                "pkg/notes.py": "# expected:\n" + HELD_OUT_SOURCE,
            },
            _boundary(),
        )
        assert "assert compute() == 4242" not in context["pkg/notes.py"]
        assert REDACTION in context["pkg/notes.py"]

    def test_held_out_source_is_redacted_from_free_text(self):
        message = f"E   AssertionError\n{HELD_OUT_SOURCE}\n"
        assert "4242" not in _boundary().redact(message)

    def test_no_held_out_paths_are_given_to_the_author(self):
        boundary = _boundary()
        assert HELD_OUT_PATH not in safe_verification_tests(
            [HELD_OUT_PATH, "tests/test_safe.py"], boundary
        )

    def test_only_explicitly_safe_metadata_crosses(self):
        boundary = _boundary()
        assert safe_metadata({"raw": "secret"}, boundary) == {}
        safe = safe_metadata(
            {SAFE_METADATA_KEY: {"target": SAFE_PATH}}, boundary
        )
        assert safe == {"target": SAFE_PATH}

    def test_malformed_context_is_filtered_to_empty(self):
        assert safe_context(None, _boundary()) == {}
        assert safe_context({1: 2}, _boundary()) == {}


class TestBoundedFailureCategory:
    def test_categories_are_closed_and_bounded(self):
        assert abstract_failure_category(_Outcome("failed")) == "assertion_failure"
        assert abstract_failure_category(_Outcome("error")) == "execution_error"
        assert abstract_failure_category(_Outcome("timeout")) == "timeout"
        assert abstract_failure_category(_Outcome("guard_failed")) == "change_refused"
        assert abstract_failure_category(_Outcome("")) == "unknown"
        assert abstract_failure_category(None) == "unknown"
        assert abstract_failure_category(_Outcome("failed")) in FAILURE_CATEGORIES

    def test_the_category_never_contains_test_content(self):
        assert "4242" not in abstract_failure_category(_Outcome("failed"))


class TestRepairPathBoundary:
    def test_repair_boundary_covers_the_workload_test_files(self):
        from atlas.evolution.development_repair import _held_out_boundary

        class _Workload:
            test_files = {HELD_OUT_PATH: HELD_OUT_SOURCE}

        boundary = _held_out_boundary(_Workload())
        assert boundary.excludes(HELD_OUT_PATH)
        assert boundary.active

    def test_repair_boundary_is_inert_without_tests(self):
        from atlas.evolution.development_repair import _held_out_boundary

        class _Workload:
            test_files = {}

        assert not _held_out_boundary(_Workload()).active

    def test_failure_summary_is_redacted(self):
        from atlas.evolution.development_repair import RepairChangeSupplier

        class _Proposal:
            title = "t"

        class _Failed:
            message = HELD_OUT_SOURCE
            test_outcome = "failed"
            outcome = _failed_status()
            changed_files = (SAFE_PATH,)
            rollback_occurred = False
            verification_passed = False

        need = RepairChangeSupplier._build_need(
            _Proposal(), _Failed(), target=SAFE_PATH, boundary=_boundary()
        )
        assert "4242" not in need.summary
        assert need.summary

    def test_the_author_receives_no_held_out_content(self):
        """The real repair seam must not hand the author what judges it."""
        from atlas.evolution.development_repair import RepairChangeSupplier

        seen: dict = {}

        class _Author:
            def propose(self, need, **kwargs):
                seen.update(kwargs)
                seen["need"] = need
                return None

        supplier = RepairChangeSupplier(repair_author=_Author())

        class _Failed:
            message = HELD_OUT_SOURCE
            test_outcome = "failed"
            outcome = _failed_status()
            changed_files = (SAFE_PATH,)
            rollback_occurred = False
            verification_passed = False
            metadata = {"verification_baseline": True}

        class _Proposal:
            title = "t"

        class _Workload:
            code_changes = ({"path": SAFE_PATH, "content": SAFE_SOURCE},)
            test_files = {HELD_OUT_PATH: HELD_OUT_SOURCE}
            verify_target = HELD_OUT_PATH

        supplier._author_specialist_correction(
            _Proposal(), _Failed(), _Workload(), _held_out_boundary_helper(_Workload())
        )
        assert seen, "the corrective author must have been consulted"
        context = seen.get("context") or {}
        assert HELD_OUT_PATH not in context
        assert "4242" not in str(context) + str(seen.get("verification_tests"))
        assert "4242" not in seen["need"].summary
        assert seen.get("verification_tests") == ()
        assert seen["plan"]["failure_category"] == "assertion_failure"


def _held_out_boundary_helper(workload):
    from atlas.evolution.development_repair import _held_out_boundary

    return _held_out_boundary(workload)
