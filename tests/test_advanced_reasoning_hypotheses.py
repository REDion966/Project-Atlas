"""Track D — HypothesisGenerator tests (Batch 2).

Covers template families, deterministic ranking, evidence scoring,
confidence calculation, hypothesis comparison, explanation generation,
optional model enhancement (fail-soft), and edge cases.
"""

import hashlib

from atlas.advanced_reasoning.hypotheses import HypothesisGenerator
from atlas.advanced_reasoning.models import Hypothesis, HypothesisSupport
from tests._advanced_reasoning_fakes import (
    FakeEvidenceProvider,
    FakeHypothesisModel,
    RaisingHypothesisModel,
)


def _digest(text: str) -> str:
    """Match the generator's internal digest for the duplicate-id test."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class TestTemplateGeneration:
    def test_generates_all_families(self):
        generator = HypothesisGenerator()
        hypothesis_set = generator.generate("the sky is blue")
        assert hypothesis_set.count == 4
        kinds = {h.kind for h in hypothesis_set.hypotheses}
        assert kinds == {"direct", "inverse", "alternative_cause", "mediating_cause"}

    def test_direct_family_default_ranking(self):
        generator = HypothesisGenerator()
        hypothesis_set = generator.generate("the sky is blue")
        # direct prior (0.5) > others (0.4) when no evidence.
        top = hypothesis_set.top_hypothesis
        assert top is not None
        assert top.kind == "direct"
        assert hypothesis_set.top_hypothesis_id == top.hypothesis_id

    def test_no_evidence_marks_contradicted(self):
        generator = HypothesisGenerator()
        hypothesis_set = generator.generate("the sky is blue")
        assert all(h.support == HypothesisSupport.CONTRADICTED for h in hypothesis_set.hypotheses)


class TestEvidenceScoring:
    def test_strong_evidence_scores_supported(self):
        provider = FakeEvidenceProvider(
            rows={"Directly: the sky is blue": ("ev1", "ev2", "ev3")}
        )
        generator = HypothesisGenerator(evidence_provider=provider)
        hypothesis_set = generator.generate("the sky is blue")
        direct = next(h for h in hypothesis_set.hypotheses if h.kind == "direct")
        assert direct.support == HypothesisSupport.SUPPORTED
        assert direct.evidence_refs == ("ev1", "ev2", "ev3")
        # score = 0.6 * 0.9 + 0.4 * 0.5 = 0.74
        assert direct.score == 0.74

    def test_evidence_raises_top_hypothesis_score(self):
        provider = FakeEvidenceProvider(
            rows={"Directly: the sky is blue": ("ev1", "ev2", "ev3")}
        )
        generator = HypothesisGenerator(evidence_provider=provider)
        hypothesis_set = generator.generate("the sky is blue")
        direct = next(h for h in hypothesis_set.hypotheses if h.kind == "direct")
        inverse = next(h for h in hypothesis_set.hypotheses if h.kind == "inverse")
        assert direct.score > inverse.score
        top = hypothesis_set.top_hypothesis
        assert top is not None
        assert top.kind == "direct"

    def test_weak_evidence_marks_unverified(self):
        provider = FakeEvidenceProvider(
            rows={"Directly: the sky is blue": ("ev1",)}
        )
        generator = HypothesisGenerator(evidence_provider=provider)
        hypothesis_set = generator.generate("the sky is blue")
        direct = next(h for h in hypothesis_set.hypotheses if h.kind == "direct")
        assert direct.support == HypothesisSupport.UNVERIFIED
        assert direct.evidence_refs == ("ev1",)
        # score = 0.6 * 0.5 + 0.4 * 0.5 = 0.5
        assert direct.score == 0.5


class TestRankingAndLimit:
    def test_limit_caps_hypotheses(self):
        generator = HypothesisGenerator()
        hypothesis_set = generator.generate("the sky is blue", limit=2)
        assert hypothesis_set.count == 2

    def test_scores_descending(self):
        provider = FakeEvidenceProvider(
            rows={
                "Directly: the sky is blue": ("ev1", "ev2", "ev3"),
                "Inverse: not the sky is blue": ("ev4", "ev5", "ev6"),
            }
        )
        generator = HypothesisGenerator(evidence_provider=provider)
        hypothesis_set = generator.generate("the sky is blue")
        scores = [h.score for h in hypothesis_set.hypotheses]
        assert scores == sorted(scores, reverse=True)

    def test_ranked_hypotheses_have_unique_ids(self):
        generator = HypothesisGenerator()
        hypothesis_set = generator.generate("the sky is blue")
        ids = {h.hypothesis_id for h in hypothesis_set.hypotheses}
        assert len(ids) == hypothesis_set.count


class TestComparisonAndExplanation:
    def test_compare_above(self):
        first = Hypothesis(hypothesis_id="h1", claim="a", score=0.8)
        second = Hypothesis(hypothesis_id="h2", claim="b", score=0.4)
        sentence = HypothesisGenerator.compare(first, second)
        assert "h1 (0.80) is ranked above h2 (0.40)" in sentence

    def test_compare_below(self):
        first = Hypothesis(hypothesis_id="h1", claim="a", score=0.4)
        second = Hypothesis(hypothesis_id="h2", claim="b", score=0.8)
        sentence = HypothesisGenerator.compare(first, second)
        assert "h2 (0.80) is ranked above h1 (0.40)" in sentence

    def test_compare_equal(self):
        first = Hypothesis(hypothesis_id="h1", claim="a", score=0.5)
        second = Hypothesis(hypothesis_id="h2", claim="b", score=0.5)
        sentence = HypothesisGenerator.compare(first, second)
        assert "are equally ranked" in sentence

    def test_explain_includes_score_and_support(self):
        hypothesis = Hypothesis(
            hypothesis_id="h1",
            claim="the sky is blue",
            kind="direct",
            support=HypothesisSupport.SUPPORTED,
            score=0.74,
            evidence_refs=("ev1", "ev2"),
        )
        explanation = HypothesisGenerator.explain(hypothesis)
        assert "0.74" in explanation
        assert "supported" in explanation
        assert "2 refs" in explanation


class TestModelEnhancement:
    def test_model_hypotheses_merged_and_rescored(self):
        model = FakeHypothesisModel(
            hypotheses=(
                Hypothesis(hypothesis_id="m1", claim="model hypothesis"),
            )
        )
        generator = HypothesisGenerator(hypothesis_model=model)
        hypothesis_set = generator.generate("the sky is blue")
        ids = {h.hypothesis_id for h in hypothesis_set.hypotheses}
        assert "m1" in ids
        assert len(ids) == hypothesis_set.count == 5

    def test_raising_model_is_ignored(self):
        generator = HypothesisGenerator(hypothesis_model=RaisingHypothesisModel())
        hypothesis_set = generator.generate("the sky is blue")
        assert hypothesis_set.count == 4

    def test_duplicate_model_id_dropped(self):
        template = f"hyp:{_digest('the sky is blue')}:direct"
        model = FakeHypothesisModel(
            hypotheses=(
                Hypothesis(hypothesis_id=template, claim="dup"),
            )
        )
        generator = HypothesisGenerator(hypothesis_model=model)
        hypothesis_set = generator.generate("the sky is blue")
        assert hypothesis_set.count == 4


class TestEdgeCases:
    def test_empty_claim_returns_empty_set(self):
        generator = HypothesisGenerator()
        hypothesis_set = generator.generate("   ")
        assert hypothesis_set.count == 0
        assert hypothesis_set.top_hypothesis is None
        assert hypothesis_set.top_hypothesis_id == ""

    def test_set_id_override(self):
        generator = HypothesisGenerator()
        hypothesis_set = generator.generate("the sky is blue", set_id="custom")
        assert hypothesis_set.set_id == "custom"

    def test_deterministic_output(self):
        generator = HypothesisGenerator()
        first = generator.generate("the sky is blue")
        second = generator.generate("the sky is blue")
        assert first.hypotheses == second.hypotheses
        assert first.top_hypothesis_id == second.top_hypothesis_id
