"""Contract-propagation coverage for the governed development pipeline.

Every seam below caused a real, hand-diagnosed failure during development. These
tests assert the DOWNSTREAM CONSUMER actually receives and uses the upstream
artifact — not merely that the upstream object exists.

No production behaviour is changed here: this file makes the existing contracts
explicit and hard to silently disconnect.
"""

from __future__ import annotations

import pathlib

import pytest

from atlas.evolution.change_author_router import plan_development_change
from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.development_localization import DevelopmentLocalizer
from atlas.evolution.development_models import SandboxWorkload
from atlas.evolution.self_development_loop import (
    SelfDevelopmentLoop,
    metadata_change_supplier,
)
from atlas.evolution.structural_editor import (
    STRUCTURAL_KEY,
    StructuralChangeSupplier,
)
from atlas.evolution.supplied_edit_intake import supplied_structural_edit
from atlas.research.repository_map import RepositoryMapBuilder

ROOT = pathlib.Path(__file__).resolve().parents[1]

MODULE_REQUEST = "Improve the development gap module."

EDIT_REQUEST = (
    "Update the explicitly named helper `_indent_of` in "
    "atlas/evolution/structural_editor.py while preserving its existing "
    "interface:\n\n"
    "```python\n"
    "def _indent_of(line: str) -> str:\n"
    '    """Return the leading whitespace of ``line``."""\n'
    "    return line[: len(line) - len(line.lstrip(\" \\t\"))]\n"
    "```\n"
)


class _FakeWorkspace:
    """Minimal workspace exposing only the containment probe the loop uses."""

    def __init__(self, present):
        self._present = set(present)

    def exists(self, path):
        return str(path) in self._present


@pytest.fixture(scope="module")
def repository_map():
    return RepositoryMapBuilder(ROOT).build()


@pytest.fixture(scope="module")
def localizer(repository_map):
    return DevelopmentLocalizer(repository_map)


# ---------------------------------------------------------------------------
# 1. localization -> ChangePlan
# ---------------------------------------------------------------------------


class TestLocalizationToChangePlan:
    def test_plan_target_comes_from_the_localization(self, localizer):
        localization = localizer.localize(MODULE_REQUEST)
        assert localization.resolved

        plan = plan_development_change(
            DevelopmentNeed(title=MODULE_REQUEST, summary=MODULE_REQUEST), localization
        )
        # the plan CONSUMES the localization, not merely the request text
        assert plan.target == localization.target
        assert plan.target_kind == localization.target_kind
        assert plan.localization_status == localization.status.value
        assert plan.provenance == localization.evidence
        assert plan.localized is True

    def test_unresolved_localization_claims_no_target(self, localizer):
        request = "Improve the zzz nonexistent widget subsystem."
        localization = localizer.localize(request)
        plan = plan_development_change(
            DevelopmentNeed(title=request, summary=request), localization
        )
        assert plan.localized is False
        assert plan.target == ""
        assert plan.actionable is False


# ---------------------------------------------------------------------------
# 2. ChangePlan -> VerificationExpectation
# ---------------------------------------------------------------------------


class TestChangePlanToVerificationExpectation:
    def test_expectations_are_derived_from_the_plan_target(self, localizer):
        localization = localizer.localize(MODULE_REQUEST)
        plan = plan_development_change(
            DevelopmentNeed(title=MODULE_REQUEST, summary=MODULE_REQUEST), localization
        )
        verification = plan.verification
        assert verification is not None
        assert verification.verification_target == plan.target
        assert verification.tests, "a resolved plan must project real tests"
        assert verification.provenance

    def test_expectations_are_not_authorization(self, localizer):
        localization = localizer.localize(MODULE_REQUEST)
        plan = plan_development_change(
            DevelopmentNeed(title=MODULE_REQUEST, summary=MODULE_REQUEST), localization
        )
        assert plan.verification.executed is False
        assert plan.verification.authorized is False
        assert plan.actionable is False


# ---------------------------------------------------------------------------
# 3. VerificationExpectation -> SandboxWorkload.test_files
# ---------------------------------------------------------------------------


class TestExpectationsToWorkload:
    def test_plan_tests_reach_the_sandbox_workload(self, repository_map):
        localization = DevelopmentLocalizer(repository_map).localize(MODULE_REQUEST)
        plan = plan_development_change(
            DevelopmentNeed(title=MODULE_REQUEST, summary=MODULE_REQUEST), localization
        )
        selected = list(plan.verification.tests)
        assert selected

        proposal = type(
            "P",
            (),
            {
                "metadata": {
                    "code_changes": [{"path": "atlas/__init__.py", "content": "# x\n"}],
                    "test_files": {path: "" for path in selected},
                }
            },
        )()
        workload = metadata_change_supplier(proposal)
        assert workload is not None
        # the workload CONSUMES the expectation: same set, no invention
        assert set(workload.test_files) == set(selected)


# ---------------------------------------------------------------------------
# 4. supplied edit -> StructuralChangeSupplier
# ---------------------------------------------------------------------------


class TestSuppliedEditToAuthoring:
    def test_supplied_symbol_reaches_the_structural_author(self, localizer):
        localization = localizer.localize(EDIT_REQUEST)
        edit = supplied_structural_edit(EDIT_REQUEST, localization)
        assert edit.ok is True, edit.reason

        need = DevelopmentNeed(
            title=EDIT_REQUEST,
            summary=EDIT_REQUEST,
            metadata={STRUCTURAL_KEY: [edit.entry]},
        )
        supplied = StructuralChangeSupplier().supply_changes(need)
        assert supplied is not None
        assert supplied.code_changes
        path, content = supplied.code_changes[0]
        assert path == "atlas/evolution/structural_editor.py"
        assert "_indent_of" in content

    def test_supplied_tests_and_context_reach_the_author(self, localizer):
        localization = localizer.localize(EDIT_REQUEST)
        edit = supplied_structural_edit(EDIT_REQUEST, localization)
        need = DevelopmentNeed(
            title=EDIT_REQUEST,
            summary=EDIT_REQUEST,
            metadata={
                STRUCTURAL_KEY: [edit.entry],
                "test_files": {"tests/test_development_change_plan.py": ""},
                "repository_context": {"atlas/__init__.py": ""},
            },
        )
        supplied = StructuralChangeSupplier().supply_changes(need)
        assert supplied is not None
        assert dict(supplied.test_files) == {
            "tests/test_development_change_plan.py": ""
        }
        assert dict(supplied.repository_context) == {"atlas/__init__.py": ""}


# ---------------------------------------------------------------------------
# 5. workload -> proposal metadata (the reverse edge)
# ---------------------------------------------------------------------------


class TestWorkloadToProposalMetadata:
    def test_workload_metadata_round_trips_through_the_supplier(self):
        from atlas.evolution.development_cycle import SuppliedChanges

        supplied = SuppliedChanges(
            code_changes=(("atlas/__init__.py", "# x\n"),),
            test_files=(("tests/a.py", "TA"),),
            repository_context=(("atlas/b.py", "TB"),),
        )
        proposal = type(
            "P",
            (),
            {
                "metadata": {
                    "code_changes": [
                        {"path": p, "content": c} for p, c in supplied.code_changes
                    ],
                    "test_files": dict(supplied.test_files),
                    "repository_context": dict(supplied.repository_context),
                }
            },
        )()
        workload = metadata_change_supplier(proposal)
        assert workload is not None
        assert dict(workload.test_files) == {"tests/a.py": "TA"}
        assert dict(workload.repository_context) == {"atlas/b.py": "TB"}


# ---------------------------------------------------------------------------
# 6. plan -> authoritative verification target (the scope invariant)
# ---------------------------------------------------------------------------


class TestAuthoritativeVerificationTarget:
    def test_plan_selected_tests_become_the_pytest_target(self):
        workload = SandboxWorkload(
            code_changes=(),
            test_files={"tests/one.py": "", "tests/two.py": ""},
        )
        workspace = _FakeWorkspace({"tests/one.py", "tests/two.py"})
        assert SelfDevelopmentLoop._plan_verify_target(workload, workspace) == (
            "tests/one.py"
        )

    def test_target_prefers_the_plan_order_deterministically(self):
        workload = SandboxWorkload(
            code_changes=(),
            test_files={"tests/late.py": "", "tests/early.py": ""},
        )
        workspace = _FakeWorkspace({"tests/late.py", "tests/early.py"})
        first = SelfDevelopmentLoop._plan_verify_target(workload, workspace)
        again = SelfDevelopmentLoop._plan_verify_target(workload, workspace)
        assert first == again == "tests/late.py"

    def test_absent_plan_tests_yield_no_widening_target(self):
        """A workload with no plan-derived tests must NOT name a broader target.

        It returns "" so the existing change-derived default is the fallback —
        an empty result here must never become a whole-repository sweep.
        """
        workload = SandboxWorkload(code_changes=(), test_files={})
        workspace = _FakeWorkspace({"tests/anything.py"})
        assert SelfDevelopmentLoop._plan_verify_target(workload, workspace) == ""

    def test_plan_tests_absent_from_the_sandbox_do_not_widen(self):
        workload = SandboxWorkload(
            code_changes=(), test_files={"tests/not_materialised.py": ""}
        )
        workspace = _FakeWorkspace({"tests/some_other.py"})
        assert SelfDevelopmentLoop._plan_verify_target(workload, workspace) == ""
