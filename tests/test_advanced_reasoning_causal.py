"""Track D — CausalReasoner tests (Batch 2).

Covers causal chain analysis, root-cause analysis, counterfactual / what-if
evaluation, path explanations, read-only protocol discipline, and edge
cases (empty results, no provider, raising provider, max depth).
"""

from atlas.advanced_reasoning.causal import CausalReasoner
from tests._advanced_reasoning_fakes import (
    FakeCausalGraphProvider,
    RaisingCausalGraphProvider,
    causal_path,
)


class TestCausalChainAnalysis:
    def test_analyze_returns_paths_sorted_by_confidence_desc(self):
        provider = FakeCausalGraphProvider(
            paths={
                ("a", "b"): (
                    causal_path("p1", confidence=0.5),
                    causal_path("p2", confidence=0.9),
                )
            }
        )
        reasoner = CausalReasoner(graph_provider=provider)
        paths = reasoner.analyze("a", "b")
        assert [p.path_id for p in paths] == ["p2", "p1"]

    def test_analyze_empty_result(self):
        reasoner = CausalReasoner(graph_provider=FakeCausalGraphProvider())
        assert reasoner.analyze("a", "b") == ()

    def test_analyze_without_provider(self):
        reasoner = CausalReasoner()
        assert reasoner.analyze("a", "b") == ()

    def test_analyze_raising_provider_falls_back(self):
        reasoner = CausalReasoner(graph_provider=RaisingCausalGraphProvider())
        assert reasoner.analyze("a", "b") == ()

    def test_analyze_forwards_max_depth(self):
        provider = FakeCausalGraphProvider()
        reasoner = CausalReasoner(graph_provider=provider)
        reasoner.analyze("a", "b", max_depth=3)
        assert provider.causal_paths_calls == [("a", "b", 3)]

    def test_analyze_never_mutates_provider(self):
        paths = {("a", "b"): (causal_path("p1", confidence=0.7),)}
        related = {"a": ("b",)}
        provider = FakeCausalGraphProvider(paths=paths, related=related)
        reasoner = CausalReasoner(graph_provider=provider)
        reasoner.analyze("a", "b")
        assert provider.paths == paths
        assert provider.related == related
        assert len(provider.causal_paths_calls) == 1
        assert provider.related_entities_calls == []


class TestRootCauseAnalysis:
    def test_root_causes_finds_incoming_paths(self):
        p1 = causal_path("p1", source="a", target="b", confidence=0.8)
        provider = FakeCausalGraphProvider(
            paths={("a", "b"): (p1,)},
            related={"b": ("a",)},
        )
        reasoner = CausalReasoner(graph_provider=provider)
        paths = reasoner.root_causes("b")
        assert paths == (p1,)
        assert provider.related_entities_calls == [("b", 5)]
        assert provider.causal_paths_calls == [("a", "b", 5)]

    def test_root_causes_no_related_entities(self):
        reasoner = CausalReasoner(graph_provider=FakeCausalGraphProvider())
        assert reasoner.root_causes("b") == ()

    def test_root_causes_without_provider(self):
        reasoner = CausalReasoner()
        assert reasoner.root_causes("b") == ()


class TestCounterfactual:
    def _provider(self):
        p1 = causal_path(
            "p1",
            source="a",
            target="b",
            entity_ids=("a", "middle", "b"),
            relation_types=("causes",),
            confidence=0.9,
        )
        p2 = causal_path(
            "p2",
            source="a",
            target="c",
            entity_ids=("a", "c"),
            relation_types=("causes",),
            confidence=0.7,
        )
        return FakeCausalGraphProvider(
            paths={("a", "b"): (p1,), ("a", "c"): (p2,)},
            related={"a": ("b", "c")},
        )

    def test_blocking_assumption_removes_path(self):
        reasoner = CausalReasoner(graph_provider=self._provider())
        result = reasoner.counterfactual("a", "middle removed")
        assert result.changed is True
        assert [p.path_id for p in result.paths_before] == ["p1", "p2"]
        assert [p.path_id for p in result.paths_after] == ["p2"]
        assert "removes 1" in result.effect_summary

    def test_non_matching_assumption_has_no_effect(self):
        reasoner = CausalReasoner(graph_provider=self._provider())
        result = reasoner.counterfactual("a", "the noise")
        assert result.changed is False
        assert result.paths_before == result.paths_after

    def test_what_if_is_alias_of_counterfactual(self):
        reasoner = CausalReasoner(graph_provider=self._provider())
        what_if = reasoner.what_if("a", "middle causes changes")
        counterfactual = reasoner.counterfactual("a", "middle causes changes")
        assert what_if == counterfactual

    def test_counterfactual_without_provider(self):
        reasoner = CausalReasoner()
        result = reasoner.counterfactual("a", "middle causes changes")
        assert result.changed is False
        assert result.paths_before == ()
        assert result.paths_after == ()

    def test_never_mutates_provider_on_counterfactual(self):
        provider = self._provider()
        reasoner = CausalReasoner(graph_provider=provider)
        reasoner.counterfactual("a", "middle causes changes")
        assert provider.causal_paths_calls == [("a", "b", 5), ("a", "c", 5)]
        assert provider.related_entities_calls == [("a", 5)]


class TestExplanation:
    def test_explain_with_relations(self):
        p = causal_path(
            "p1",
            source="a",
            target="c",
            entity_ids=("a", "b", "c"),
            relation_types=("causes", "enables"),
            confidence=0.7,
        )
        assert (
            CausalReasoner.explain(p)
            == "a leads to c via a [causes] -> b [enables] (confidence 0.70)"
        )

    def test_explain_without_relations(self):
        p = causal_path(
            "p1",
            source="a",
            target="c",
            entity_ids=("a", "b", "c"),
            confidence=0.7,
        )
        assert (
            CausalReasoner.explain(p)
            == "a leads to c via b, c (confidence 0.70)"
        )

    def test_explain_without_entities(self):
        p = causal_path("p1", source="a", target="b")
        assert CausalReasoner.explain(p) == "a influences b"

    def test_explain_all(self):
        paths = (
            causal_path("p1", source="a", target="b"),
            causal_path("p2", source="x", target="y"),
        )
        explanations = CausalReasoner.explain_all(paths)
        assert len(explanations) == 2
        assert explanations[0] == CausalReasoner.explain(paths[0])
        assert explanations[1] == CausalReasoner.explain(paths[1])


class TestDeterminism:
    def test_analyze_is_deterministic(self):
        provider = FakeCausalGraphProvider(
            paths={
                ("a", "b"): (
                    causal_path("p1", confidence=0.5),
                    causal_path("p2", confidence=0.9),
                )
            }
        )
        reasoner = CausalReasoner(graph_provider=provider)
        first = reasoner.analyze("a", "b")
        second = reasoner.analyze("a", "b")
        assert first == second
