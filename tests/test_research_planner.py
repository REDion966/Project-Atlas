"""Phase 17.3 — Research Planner: tests.

Covers deterministic decomposition, sub-query generation, source-kind
selection, verification strategy, max depth, and statelessness/determinism
for atlas/research/planner.py.

Note: ``ResearchPlan.created_at`` is a model-level timestamp (defaults to
``datetime.now()`` like every Atlas model timestamp). Planner determinism
is asserted over the planner-produced fields, which the planner fully
controls.
"""

import pytest

from atlas.evolution.models import ResearchQuery
from atlas.research.models import SourceKind
from atlas.research.planner import ResearchPlanner


def make_query(query_id: str, question: str) -> ResearchQuery:
    return ResearchQuery(query_id=query_id, question=question)


def planned_fields(plan):
    """The planner-controlled fields of a ResearchPlan."""
    return (
        plan.plan_id,
        plan.query_id,
        plan.question,
        plan.sub_queries,
        plan.target_sources,
        plan.verification_strategy,
        plan.max_depth,
    )


class TestPlannerDecomposition:
    def test_plan_builds_sub_queries(self):
        planner = ResearchPlanner()
        plan = planner.plan(make_query("RQ-1", "How does Atlas handle storage?"))
        assert plan.plan_id == "plan::RQ-1"
        assert plan.query_id == "RQ-1"
        assert plan.question == "How does Atlas handle storage?"
        assert len(plan.sub_queries) >= 1
        assert plan.sub_queries[0] == "How does Atlas handle storage? | aspect: storage"

    def test_plan_uses_query_question_verbatim(self):
        planner = ResearchPlanner()
        plan = planner.plan(make_query("RQ-2", "What is the evolution governance model?"))
        assert plan.question == "What is the evolution governance model?"
        assert plan.sub_queries[0].startswith("What is the evolution governance model?")

    def test_empty_question_yields_empty_plan(self):
        planner = ResearchPlanner()
        plan = planner.plan(make_query("RQ-3", "   "))
        assert plan.sub_queries == ()
        assert plan.max_depth == 1
        assert plan.verification_strategy == "none"


class TestPlannerSourceSelection:
    def test_workspace_uri_selects_workspace(self):
        planner = ResearchPlanner()
        plan = planner.plan(
            make_query("RQ-W", "Read workspace://docs/atlas.md and summarize the design")
        )
        assert plan.target_sources == (SourceKind.WORKSPACE,)

    def test_code_uri_selects_codebase(self):
        planner = ResearchPlanner()
        plan = planner.plan(
            make_query("RQ-C", "Explain what code://atlas/planner.py does")
        )
        assert plan.target_sources == (SourceKind.CODEBASE,)

    def test_python_extension_selects_codebase(self):
        planner = ResearchPlanner()
        plan = planner.plan(make_query("RQ-P", "Analyze atlas/research/models.py structure"))
        assert plan.target_sources == (SourceKind.CODEBASE,)

    def test_md_extension_selects_document(self):
        planner = ResearchPlanner()
        plan = planner.plan(make_query("RQ-M", "Summarize the content of docs/README.md"))
        assert plan.target_sources == (SourceKind.DOCUMENT,)

    def test_plain_question_defaults_to_document(self):
        planner = ResearchPlanner()
        plan = planner.plan(make_query("RQ-D", "What is the best approach?"))
        assert plan.target_sources == (SourceKind.DOCUMENT,)


class TestPlannerVerificationStrategy:
    def test_single_aspect_uses_internal_consistency(self):
        planner = ResearchPlanner()
        plan = planner.plan(make_query("RQ-1", "How does Atlas handle storage?"))
        assert plan.verification_strategy == "internal_consistency"

    def test_core_subject_empty_uses_none(self):
        planner = ResearchPlanner()
        plan = planner.plan(make_query("RQ-2", ""))
        assert plan.verification_strategy == "none"


class TestPlannerMaxDepth:
    def test_short_question_depth_one(self):
        planner = ResearchPlanner()
        plan = planner.plan(make_query("RQ-1", "What is storage?"))
        assert plan.max_depth == 1

    def test_medium_question_depth_two(self):
        planner = ResearchPlanner()
        question = (
            "How should Atlas store and retrieve structured experiences across "
            "multiple sessions without losing provenance?"
        )
        plan = planner.plan(make_query("RQ-2", question))
        assert 8 < len(question.split()) <= 24
        assert plan.max_depth == 2

    def test_long_question_depth_three(self):
        planner = ResearchPlanner()
        question = (
            "How should Atlas combine document sources, workspace resources and "
            "codebase files into a single normalized representation that supports "
            "citation tracking, claim verification and confidence scoring across "
            "many different research queries?"
        )
        plan = planner.plan(make_query("RQ-3", question))
        assert len(question.split()) > 24
        assert plan.max_depth == 3


class TestPlannerDeterminism:
    def test_identical_queries_produce_identical_plans(self):
        planner = ResearchPlanner()
        first = planner.plan(make_query("RQ-1", "How does Atlas handle storage?"))
        second = planner.plan(make_query("RQ-1", "How does Atlas handle storage?"))
        assert planned_fields(first) == planned_fields(second)

    def test_plan_fields_are_stable_across_calls(self):
        planner = ResearchPlanner()
        first = planner.plan(make_query("RQ-X", "Explain the architecture governance model"))
        for _ in range(5):
            other = planner.plan(make_query("RQ-X", "Explain the architecture governance model"))
            assert planned_fields(other) == planned_fields(first)

    def test_plan_is_stateless(self):
        planner = ResearchPlanner()
        first = planner.plan(make_query("RQ-A", "How does memory work?"))
        _unrelated = planner.plan(make_query("RQ-B", "Analyze atlas/research/planner.py"))
        second = planner.plan(make_query("RQ-A", "How does memory work?"))
        assert planned_fields(first) == planned_fields(second)


class TestPlannerCoreSubject:
    def test_core_subject_picks_last_significant_word(self):
        planner = ResearchPlanner()
        assert planner.core_subject("How does Atlas handle storage?") == "storage"

    def test_core_subject_ignores_stopwords_at_end(self):
        planner = ResearchPlanner()
        assert planner.core_subject("what is the architecture?") == "architecture"

    def test_core_subject_empty_for_blank(self):
        planner = ResearchPlanner()
        assert planner.core_subject("") == ""

    def test_core_subject_single_word(self):
        planner = ResearchPlanner()
        assert planner.core_subject("storage") == "storage"


class TestPlannerAspectMapping:
    def test_known_subject_maps_to_aspect(self):
        planner = ResearchPlanner()
        decomposition = planner.decompose(
            make_query("RQ-1", "How does Atlas handle governance?")
        )
        assert planner.aspects("", decomposition.core_subject) == ("governance",)

    def test_unknown_subject_maps_to_overview(self):
        planner = ResearchPlanner()
        decomposition = planner.decompose(
            make_query("RQ-2", "What is a hummingbird?")
        )
        assert planner.aspects("", decomposition.core_subject) == ("overview",)

    def test_sub_query_ids_are_deterministic(self):
        planner = ResearchPlanner()
        plan = planner.plan(make_query("RQ-9", "How does Atlas handle storage?"))
        assert plan.sub_queries[0] == "How does Atlas handle storage? | aspect: storage"


class TestPlannerInputContract:
    def test_accepts_existing_evolution_research_query(self):
        """The planner consumes the existing atlas.evolution.models.ResearchQuery."""
        query = ResearchQuery(query_id="RQ-1", question="What is storage?")
        plan = ResearchPlanner().plan(query)
        assert plan.query_id == "RQ-1"
        assert plan.question == "What is storage?"
