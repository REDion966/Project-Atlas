"""Command 3 — the bounded semantic re-ranking consumer boundary.

The invariant under test: a specialist may only RE-ORDER Atlas's own candidate
set. It can never add or remove a candidate.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from atlas.evolution.semantic_ranking import (  # noqa: E402
    DEFAULT_SEMANTIC_MARGIN,
    REASON_AGREES,
    REASON_APPLIED,
    REASON_BELOW_MARGIN,
    REASON_NO_CANDIDATES,
    REASON_NO_QUERY,
    REASON_NO_SIGNAL,
    REASON_NO_SPECIALIST,
    SemanticCandidate,
    rerank_candidates,
)
from atlas.semantic_similarity import (  # noqa: E402
    NullEmbeddingModel,
    SpecialistEmbeddingModel,
)

CANDIDATES = [
    SemanticCandidate("atlas.research.relevance", "relevance lexical overlap tokens"),
    SemanticCandidate("atlas.evolution.development_repair", "repair corrective workload"),
    SemanticCandidate("atlas.kernel.atlas", "kernel composition root"),
]

#: A deterministic fake runtime: a vector whose FIRST axis is a fixed keyword
#: signal, so "similarity" is fully controllable without a network.
_KEYWORDS = ("repair", "kernel", "relevance")


def _fake_transport(request):
    vectors = []
    for text in request["texts"]:
        lowered = text.lower()
        signals = [1.0 if word in lowered else 0.0 for word in _KEYWORDS]
        vectors.append(signals + [0.0] * (8 - len(signals)))
    return {"embeddings": vectors}


def _model() -> SpecialistEmbeddingModel:
    return SpecialistEmbeddingModel(transport=_fake_transport, model_id="fake")


class TestInvariantPermutation:
    def test_order_is_always_a_permutation_of_the_input(self):
        for query in ("", "repair", "nothing at all"):
            for model in (None, NullEmbeddingModel(), _model()):
                ranking = rerank_candidates(CANDIDATES, query, model)
                assert sorted(ranking.order) == sorted(c.key for c in CANDIDATES)

    def test_candidates_are_never_added_or_removed(self):
        ranking = rerank_candidates(CANDIDATES, "repair", _model())
        assert len(ranking.order) == len(CANDIDATES)
        assert set(ranking.order) == {c.key for c in CANDIDATES}

    def test_deterministic_order_is_always_recorded(self):
        ranking = rerank_candidates(CANDIDATES, "repair", _model())
        assert ranking.deterministic_order == tuple(c.key for c in CANDIDATES)


class TestRefusals:
    def test_no_candidates_yields_an_empty_unchanged_ranking(self):
        ranking = rerank_candidates([], "repair", _model())
        assert ranking.order == ()
        assert ranking.applied is False
        assert ranking.reason == REASON_NO_CANDIDATES

    def test_no_query_is_refused(self):
        ranking = rerank_candidates(CANDIDATES, "", _model())
        assert ranking.applied is False
        assert ranking.reason == REASON_NO_QUERY

    def test_no_specialist_leaves_the_order_untouched(self):
        for model in (None, NullEmbeddingModel()):
            ranking = rerank_candidates(CANDIDATES, "repair", model)
            assert ranking.order == tuple(c.key for c in CANDIDATES)
            assert ranking.applied is False
            assert ranking.reason == REASON_NO_SPECIALIST

    def test_broken_specialist_is_no_signal(self):
        class _Boom:
            available = True

            def embed(self, texts):
                raise RuntimeError("down")

        ranking = rerank_candidates(CANDIDATES, "repair", _Boom())
        assert ranking.applied is False
        assert ranking.reason == REASON_NO_SIGNAL

    def test_malformed_reply_is_no_signal(self):
        model = SpecialistEmbeddingModel(transport=lambda request: {"embeddings": [[1.0]]})
        ranking = rerank_candidates(CANDIDATES, "repair", model)
        assert ranking.applied is False
        assert ranking.reason == REASON_NO_SIGNAL

    def test_a_non_result_object_is_no_signal(self):
        class _Junk:
            available = True

            def embed(self, texts):
                return {"embeddings": [[1.0] * 8]}

        ranking = rerank_candidates(CANDIDATES, "repair", _Junk())
        assert ranking.applied is False
        assert ranking.reason == REASON_NO_SIGNAL


class TestUncertaintyPreservation:
    def test_agreement_leaves_the_order_untouched(self):
        # The deterministic top IS the semantic best: nothing to change.
        ranking = rerank_candidates(CANDIDATES, "relevance", _model())
        assert ranking.applied is False
        assert ranking.reason == REASON_AGREES
        assert ranking.order == tuple(c.key for c in CANDIDATES)

    def test_a_lead_inside_the_margin_is_refused(self):
        ranking = rerank_candidates(CANDIDATES, "repair", _model(), margin=10.0)
        assert ranking.applied is False
        assert ranking.reason == REASON_BELOW_MARGIN
        assert ranking.order == tuple(c.key for c in CANDIDATES)

    def test_a_zero_margin_still_requires_a_different_winner(self):
        ranking = rerank_candidates(CANDIDATES, "relevance", _model(), margin=0.0)
        assert ranking.applied is False
        assert ranking.reason == REASON_AGREES

    def test_the_lead_is_reported(self):
        ranking = rerank_candidates(CANDIDATES, "repair", _model())
        assert ranking.lead > 0.0
        assert ranking.margin == DEFAULT_SEMANTIC_MARGIN


class TestApplied:
    def test_a_clear_semantic_lead_reorders_the_candidates(self):
        ranking = rerank_candidates(CANDIDATES, "repair", _model())
        assert ranking.applied is True
        assert ranking.reason == REASON_APPLIED
        assert ranking.order[0] == "atlas.evolution.development_repair"

    def test_the_reorder_is_auditable(self):
        ranking = rerank_candidates(CANDIDATES, "repair", _model())
        payload = ranking.to_dict()
        assert payload["applied"] is True
        assert payload["deterministic_order"] == [c.key for c in CANDIDATES]
        assert payload["provider_id"]
        assert payload["dimension"] == 8
        assert payload["scores"]

    def test_the_reorder_carries_no_authority_field(self):
        payload = rerank_candidates(CANDIDATES, "repair", _model()).to_dict()
        for forbidden in ("authorized", "approved", "executed", "promoted", "apply"):
            assert forbidden not in payload

    def test_identical_input_is_deterministic(self):
        first = rerank_candidates(CANDIDATES, "repair", _model()).to_dict()
        second = rerank_candidates(CANDIDATES, "repair", _model()).to_dict()
        assert first == second

    def test_ties_never_reorder_by_themselves(self):
        # Every vector is identical, so every score ties: the ORIGINAL order wins.
        model = SpecialistEmbeddingModel(
            transport=lambda request: {"embeddings": [[1.0] * 8] * len(request["texts"])}
        )
        ranking = rerank_candidates(CANDIDATES, "anything", model, margin=0.0)
        assert ranking.applied is False
        assert ranking.order == tuple(c.key for c in CANDIDATES)


class TestBoundsAndInputs:
    def test_the_candidate_set_is_bounded(self):
        many = [SemanticCandidate(f"m{index}", "text") for index in range(200)]
        model = SpecialistEmbeddingModel(
            transport=lambda request: {"embeddings": [[1.0] * 8] * len(request["texts"])}
        )
        ranking = rerank_candidates(many, "query", model)
        assert len(ranking.order) <= 24

    def test_plain_strings_and_pairs_are_accepted(self):
        ranking = rerank_candidates(["alpha", "beta"], "alpha", _model())
        assert sorted(ranking.order) == ["alpha", "beta"]

    def test_a_malformed_margin_falls_back_to_the_default(self):
        ranking = rerank_candidates(CANDIDATES, "repair", _model(), margin="wide")
        assert ranking.margin == DEFAULT_SEMANTIC_MARGIN

    def test_reranking_never_raises(self):
        for candidates in (None, 5, "text", [None], [[1, 2, 3]]):
            ranking = rerank_candidates(candidates, "q", _model())
            assert isinstance(ranking.order, tuple)
