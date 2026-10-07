"""Resolved localization -> bounded ChangePlan (evidence, never permission).

Verifies the planning boundary: a RESOLVED localization produces a bounded,
evidence-bearing plan; an AMBIGUOUS or UNRESOLVED localization produces no
authoritative plan; and non-development turns never produce a development plan.

The plan authorizes nothing — it carries no patch, reaches no governed handler,
and leaves the authoring route derived from the need's own metadata evidence.
"""

from __future__ import annotations

import pathlib

import pytest

from atlas.evolution.change_author_router import (
    AuthorRoute,
    ChangePlan,
    plan_development_change,
)
from atlas.evolution.development_cycle import DevelopmentNeed


@pytest.fixture(scope="module")
def kernel():
    import pkgutil
    import tempfile

    import atlas.storage as storage_pkg

    tmp = pathlib.Path(tempfile.mkdtemp())
    db = tmp / "plan.db"
    saved = []
    for info in pkgutil.iter_modules(storage_pkg.__path__):
        try:
            module = __import__(f"atlas.storage.{info.name}", fromlist=["*"])
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and hasattr(obj, "DEFAULT_DB_PATH"):
                saved.append((obj, obj.DEFAULT_DB_PATH))
                obj.DEFAULT_DB_PATH = db
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    try:
        yield atlas
    finally:
        atlas.shutdown()
        for obj, original in saved:
            obj.DEFAULT_DB_PATH = original


PRESERVING = (
    "I want to improve the development gap module while preserving its "
    "existing interface and behavior."
)


def _localization(kernel, text):
    from atlas.evolution.development_localization import DevelopmentLocalizer

    return DevelopmentLocalizer(kernel.repository_map).localize(text)


def _need(text):
    return DevelopmentNeed(title=text, summary=text)


# ---------------------------------------------------------------------------
# 1. Resolved localization -> bounded plan
# ---------------------------------------------------------------------------


class TestResolvedLocalization:
    def test_module_target_produces_a_bounded_plan(self, kernel):
        plan = plan_development_change(_need(PRESERVING), _localization(kernel, PRESERVING))
        assert isinstance(plan, ChangePlan)
        assert plan.localized is True
        assert plan.target == "atlas.evolution.development_gap"
        assert plan.target_kind == "module"

    def test_stated_constraints_survive_into_the_plan(self, kernel):
        plan = plan_development_change(_need(PRESERVING), _localization(kernel, PRESERVING))
        assert plan.constraints, "the request's own constraints must survive"
        assert any("preserv" in c or "interface" in c for c in plan.constraints)

    def test_relevant_tests_and_context_survive_bounded(self, kernel):
        plan = plan_development_change(_need(PRESERVING), _localization(kernel, PRESERVING))
        assert plan.context["modules"] == ["atlas.evolution.development_gap"]
        assert plan.context["tests"], "relevant tests must survive"
        assert plan.context["dependents"], "reverse-dependency evidence must survive"
        assert len(plan.context["symbols"]) <= 24

    def test_provenance_survives_into_the_plan(self, kernel):
        plan = plan_development_change(_need(PRESERVING), _localization(kernel, PRESERVING))
        assert plan.provenance, "the plan must say WHY the target was selected"

    def test_symbol_target_produces_a_symbol_level_plan(self, kernel):
        text = "Update atlas.research.repository_map.RepositoryMap.tests_for_module."
        plan = plan_development_change(_need(text), _localization(kernel, text))
        assert plan.localized is True
        assert plan.target_kind == "symbol"
        assert plan.symbol.endswith("tests_for_module")

    def test_file_path_target_localizes(self, kernel):
        text = "Change atlas/evolution/development_gap.py to reject empty input."
        plan = plan_development_change(_need(text), _localization(kernel, text))
        assert plan.localized and plan.target == "atlas.evolution.development_gap"

    def test_the_plan_is_bounded_not_a_repository_dump(self, kernel):
        plan = plan_development_change(_need(PRESERVING), _localization(kernel, PRESERVING))
        assert len(plan.context["modules"]) <= 6
        assert len(plan.context["tests"]) <= 8
        assert len(plan.context["dependents"]) <= 12

    def test_the_plan_contains_no_invented_implementation(self, kernel):
        payload = plan_development_change(
            _need(PRESERVING), _localization(kernel, PRESERVING)
        ).to_dict()
        # No patch, no source, no strategy: evidence and scope only.
        for forbidden in ("code_changes", "patch", "diff", "content", "strategy"):
            assert forbidden not in payload

    def test_a_resolved_localization_does_not_make_a_plan_actionable(self, kernel):
        plan = plan_development_change(_need(PRESERVING), _localization(kernel, PRESERVING))
        # Planning is not authorization: with no authoring evidence the route
        # stays UNAVAILABLE even though the target resolved with evidence.
        assert plan.route is AuthorRoute.UNAVAILABLE
        assert plan.actionable is False


# ---------------------------------------------------------------------------
# 2. Non-resolved localization -> no authoritative plan
# ---------------------------------------------------------------------------


class TestNonResolvedLocalization:
    def test_ambiguous_localization_claims_no_target(self, kernel):
        text = "Update the helper that validates empty input."
        plan = plan_development_change(_need(text), _localization(kernel, text))
        assert plan.localized is False
        assert plan.target == ""
        assert plan.actionable is False
        assert plan.localization_status in ("ambiguous", "unresolved")

    def test_unresolved_localization_claims_no_target(self, kernel):
        text = "Improve the zzz nonexistent widget subsystem."
        plan = plan_development_change(_need(text), _localization(kernel, text))
        assert plan.localized is False and plan.target == ""
        assert plan.actionable is False

    def test_missing_localization_is_safe(self):
        plan = plan_development_change(_need("Improve the development gap module."), None)
        assert plan.localized is False and plan.target == ""
        assert plan.localization_status == "unresolved"

    def test_ranking_alone_never_produces_a_plan_target(self, kernel):
        text = "Fix the function that resolves typed targets."
        plan = plan_development_change(_need(text), _localization(kernel, text))
        assert plan.localized is False


# ---------------------------------------------------------------------------
# 3. Kernel seam: only development requests are planned
# ---------------------------------------------------------------------------


class TestKernelPlanningBoundary:
    def test_development_request_produces_a_plan(self, kernel):
        payload = kernel.development_change_plan(PRESERVING)
        assert payload["localized"] is True
        assert payload["target"] == "atlas.evolution.development_gap"
        assert payload["context"]["tests"]
        assert payload["actionable"] is False

    def test_repository_impact_request_is_not_planned(self, kernel):
        request = "What would be affected if I change atlas/memory/manager.py?"
        assert kernel.development_change_plan(request) == {}
        assert kernel._conversation._intake(request).task_type.value == (
            "repository_impact_request"
        )

    def test_investigation_request_is_not_planned(self, kernel):
        request = "Investigate the development gap helper."
        assert kernel.development_change_plan(request) == {}
        assert kernel._conversation._intake(request).task_type.value == (
            "investigation_request"
        )

    def test_conversation_and_fail_closed_are_not_planned(self, kernel):
        assert kernel.development_change_plan("Hello there.") == {}
        assert kernel.development_change_plan("Change it.") == {}

    def test_planning_authorizes_nothing(self, kernel):
        before = len(kernel.pending_promotion_reviews())
        kernel.development_change_plan(PRESERVING)
        assert len(kernel.pending_promotion_reviews()) == before


# ---------------------------------------------------------------------------
# 4. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_repeated_planning_is_byte_identical(self, kernel):
        first = kernel.development_change_plan(PRESERVING)
        second = kernel.development_change_plan(PRESERVING)
        assert first == second
        assert first["provenance"] == second["provenance"]
        assert first["context"] == second["context"]

    def test_variant_request_produces_the_same_bounded_plan(self, kernel):
        variant = (
            "I want to improve the development gap module and preserve its "
            "existing public interface."
        )
        a = kernel.development_change_plan(PRESERVING)
        b = kernel.development_change_plan(variant)
        assert a["target"] == b["target"]
        assert a["target_kind"] == b["target_kind"]
        assert a["context"]["modules"] == b["context"]["modules"]

    def test_plan_json_is_stable(self, kernel):
        plan = kernel.development_change_plan(PRESERVING)
        assert sorted(plan) == sorted(kernel.development_change_plan(PRESERVING))


# ---------------------------------------------------------------------------
# 5. Verification expectations (evidence for a LATER change, not authorization)
# ---------------------------------------------------------------------------


class TestVerificationExpectations:
    def test_resolved_module_has_verification_expectations(self, kernel):
        plan = kernel.development_change_plan(PRESERVING)
        verification = plan["verification"]
        assert verification["verification_target"] == "atlas.evolution.development_gap"
        assert verification["tests"], "the repository-derived tests must survive"
        assert verification["provenance"]

    def test_expectations_are_not_authorization(self, kernel):
        verification = kernel.development_change_plan(PRESERVING)["verification"]
        assert verification["executed"] is False
        assert verification["authorized"] is False
        assert verification["baseline"] == "not_executed"
        assert kernel.development_change_plan(PRESERVING)["actionable"] is False

    def test_relevant_tests_are_bounded_and_deterministic(self, kernel):
        verification = kernel.development_change_plan(PRESERVING)["verification"]
        assert len(verification["tests"]) <= 8
        assert list(verification["tests"]) == sorted(set(verification["tests"]))
        assert verification["tests"] == (
            kernel.development_change_plan(PRESERVING)["verification"]["tests"]
        )

    def test_expectation_tests_come_from_the_repository(self, kernel):
        plan = kernel.development_change_plan(PRESERVING)
        known = {module.path for module in kernel.repository_map.modules}
        assert set(plan["verification"]["tests"]) <= known
        assert plan["verification"]["verification_target"] in {
            module.module for module in kernel.repository_map.modules
        }

    def test_file_path_target_also_yields_expectations(self, kernel):
        text = "Change atlas/evolution/development_gap.py to reject empty input."
        plan = kernel.development_change_plan(text)
        assert plan["localized"] is True
        assert plan["verification"]["verification_target"] == "atlas.evolution.development_gap"

    def test_symbol_target_keeps_the_module_verification_target(self, kernel):
        text = "Update atlas.research.repository_map.RepositoryMap.tests_for_module."
        plan = kernel.development_change_plan(text)
        assert plan["target_kind"] == "symbol"
        assert plan["verification"]["verification_target"] == "atlas.research.repository_map"

    def test_ambiguous_or_unresolved_has_no_expectations(self, kernel):
        for text in (
            "Update the helper that validates empty input.",
            "Improve the zzz nonexistent widget subsystem.",
            "Change it.",
        ):
            plan = kernel.development_change_plan(text)
            assert plan in ({},) or (plan["verification"] is None), text
            if plan:
                assert plan["localized"] is False

    def test_non_development_requests_produce_no_plan_or_expectations(self, kernel):
        for text in (
            "Investigate the development gap helper.",
            "What would be affected if I change atlas/memory/manager.py?",
            "Hello there.",
        ):
            assert kernel.development_change_plan(text) == {}, text

    def test_missing_evidence_declares_goals_unavailable_rather_than_guessing(self):
        from atlas.evolution.change_author_router import verification_expectations

        empty = verification_expectations("atlas.some.where", ())
        assert empty.tests == ()
        assert "unavailable" in empty.expectation
        assert empty.executed is False and empty.authorized is False

    def test_expectations_never_carry_a_patch(self, kernel):
        verification = kernel.development_change_plan(PRESERVING)["verification"]
        for forbidden in ("patch", "diff", "content", "source", "code"):
            assert forbidden not in verification

    def test_expectations_do_not_run_anything(self, kernel):
        before = len(kernel.pending_promotion_reviews())
        kernel.development_change_plan(PRESERVING)
        assert len(kernel.pending_promotion_reviews()) == before
