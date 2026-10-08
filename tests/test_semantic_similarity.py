"""Command 3 — the Atlas-owned semantic-similarity specialist contract.

Deterministic, no network: every test injects a transport.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from atlas.semantic_similarity import (  # noqa: E402
    MAX_TEXTS,
    MAX_TEXT_CHARS,
    MAX_VECTOR_DIM,
    MIN_VECTOR_DIM,
    EmbeddingResult,
    EmbeddingVector,
    NullEmbeddingModel,
    SpecialistEmbeddingModel,
    bound_texts,
    build_embedding_request,
    cosine_similarity,
    parse_embedding_response,
)
from atlas.specialists import (  # noqa: E402
    SEMANTIC_SIMILARITY,
    SPECIALIST_CAPABILITIES,
    BoundedSpecialistTask,
)


def _vec(*values: float) -> EmbeddingVector:
    return EmbeddingVector(values=tuple(float(v) for v in values))


def _dims(count: int, dimension: int = 8) -> list[list[float]]:
    return [[float(index + offset) for offset in range(dimension)] for index in range(count)]


class TestAtlasContract:
    def test_capability_is_in_the_closed_vocabulary(self):
        assert SEMANTIC_SIMILARITY in SPECIALIST_CAPABILITIES
        task = BoundedSpecialistTask(capability=SEMANTIC_SIMILARITY, request="x")
        assert task.capability == SEMANTIC_SIMILARITY

    def test_unknown_capability_is_still_refused(self):
        with pytest.raises(ValueError):
            BoundedSpecialistTask(capability="semantic.magic", request="x")


class TestBoundingInput:
    def test_bounds_text_count_and_length(self):
        texts, truncated = bound_texts(["x" * (MAX_TEXT_CHARS + 50)])
        assert len(texts[0]) == MAX_TEXT_CHARS
        assert truncated

    def test_caps_the_number_of_texts(self):
        texts, truncated = bound_texts([f"t{index}" for index in range(MAX_TEXTS + 5)])
        assert len(texts) == MAX_TEXTS
        assert truncated

    def test_rejects_malformed_input(self):
        for bad in (None, "a string", 5, [1, 2], [""], ["ok", "   "], []):
            assert bound_texts(bad) == ((), False)

    def test_strips_whitespace_deterministically(self):
        assert bound_texts(["  hello  "])[0] == ("hello",)

    def test_request_is_vendor_neutral_and_bounded(self):
        assert build_embedding_request(["a", "b"]) == {"texts": ["a", "b"]}
        assert build_embedding_request(None) == {"texts": []}


class TestParsingUntrustedOutput:
    def test_accepts_a_well_formed_reply(self):
        result = parse_embedding_response(
            {"embeddings": _dims(3)},
            expected_texts=("a", "b", "c"),
            provider_id="p",
            model_id="m",
        )
        assert isinstance(result, EmbeddingResult)
        assert result.vector_count == 3
        assert result.dimension == 8
        assert result.vector_for(0) is not None
        assert result.vector_for(9) is None

    def test_rejects_malformed_replies(self):
        expected = ("a", "b")
        bad_inputs = [
            None,
            "not a dict",
            {},
            {"embeddings": None},
            {"embeddings": []},
            {"embeddings": "nope"},
            {"embeddings": [[1.0]]},  # count mismatch
            {"embeddings": _dims(3)},  # count mismatch
            {"embeddings": [[0.0] * 8, ["x"] * 8]},  # non-numeric
            {"embeddings": [[0.0] * 8, [0.0] * 4]},  # inconsistent dimension
            {"embeddings": [[0.0] * (MIN_VECTOR_DIM - 1), [0.0] * (MIN_VECTOR_DIM - 1)]},
            {"embeddings": [[0.0] * (MAX_VECTOR_DIM + 1), [0.0] * (MAX_VECTOR_DIM + 1)]},
            {"embeddings": [[], []]},
        ]
        for bad in bad_inputs:
            assert parse_embedding_response(bad, expected_texts=expected) is None

    def test_rejects_non_finite_values(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            reply = {"embeddings": [[value] * 8, [0.0] * 8]}
            assert parse_embedding_response(reply, expected_texts=("a", "b")) is None

    def test_rejects_booleans_as_numbers(self):
        reply = {"embeddings": [[True] * 8, [0.0] * 8]}
        assert parse_embedding_response(reply, expected_texts=("a", "b")) is None

    def test_result_is_bounded_in_projection(self):
        result = parse_embedding_response({"embeddings": _dims(2)}, expected_texts=("a", "b"))
        payload = result.to_dict()
        assert "values" not in payload
        assert payload["dimension"] == 8


class TestCosine:
    def test_identical_vectors_are_maximally_similar(self):
        assert cosine_similarity(_vec(1, 2, 3), _vec(1, 2, 3)) == pytest.approx(1.0)

    def test_orthogonal_vectors_have_no_similarity(self):
        assert cosine_similarity(_vec(1, 0), _vec(0, 1)) == pytest.approx(0.0)

    def test_opposite_vectors_are_clamped(self):
        assert cosine_similarity(_vec(1, 0), _vec(-1, 0)) == pytest.approx(-1.0)

    def test_undefined_similarity_is_none_not_zero(self):
        assert cosine_similarity(_vec(0, 0), _vec(1, 1)) is None
        assert cosine_similarity(_vec(1, 0), _vec(1, 0, 0)) is None
        assert cosine_similarity(_vec(1, 0), None) is None
        assert cosine_similarity("a", "b") is None
        assert cosine_similarity(EmbeddingVector(()), EmbeddingVector(())) is None


class TestSpecialistEmbeddingModel:
    def test_unavailable_without_a_transport(self):
        model = SpecialistEmbeddingModel()
        assert model.available is False
        assert model.embed(["a"]) is None

    def test_disabled_model_is_inert(self):
        model = SpecialistEmbeddingModel(
            transport=lambda request: {"embeddings": _dims(1)}, available=False
        )
        assert model.available is False
        assert model.embed(["a"]) is None

    def test_raising_transport_fails_closed(self):
        def _boom(request):
            raise OSError("runtime down")

        model = SpecialistEmbeddingModel(transport=_boom)
        assert model.embed(["a"]) is None

    def test_malformed_reply_fails_closed(self):
        model = SpecialistEmbeddingModel(transport=lambda request: {"nonsense": 1})
        assert model.embed(["a"]) is None

    def test_malformed_input_never_reaches_the_transport(self):
        calls = []
        model = SpecialistEmbeddingModel(
            transport=lambda request: calls.append(request) or {}
        )
        assert model.embed(None) is None
        assert model.embed([""]) is None
        assert calls == []

    def test_valid_reply_is_validated_and_returns_a_result(self):
        captured = []

        def _transport(request):
            captured.append(request)
            return {"embeddings": _dims(len(request["texts"]))}

        model = SpecialistEmbeddingModel(
            transport=_transport, provider_id="test.provider", model_id="test.model"
        )
        result = model.embed(["alpha", "beta"])
        assert result is not None
        assert result.provider_id == "test.provider"
        assert result.model_id == "test.model"
        assert captured[0] == {"texts": ["alpha", "beta"]}

    def test_identical_input_is_deterministic(self):
        model = SpecialistEmbeddingModel(transport=lambda r: {"embeddings": _dims(len(r["texts"]))})
        assert model.embed(["a", "b"]).to_dict() == model.embed(["a", "b"]).to_dict()

    def test_similarity_convenience_is_none_when_unavailable(self):
        assert SpecialistEmbeddingModel().similarity("a", "b") is None

    def test_similarity_convenience_uses_the_validated_vectors(self):
        model = SpecialistEmbeddingModel(
            transport=lambda r: {"embeddings": [[1.0] + [0.0] * 7, [1.0] + [0.0] * 7]}
        )
        assert model.similarity("a", "b") == pytest.approx(1.0)


class TestNullModel:
    def test_null_model_is_explicitly_unavailable(self):
        model = NullEmbeddingModel()
        assert model.available is False
        assert model.embed(["a"]) is None
        assert model.provider_id == ""

    def test_null_model_satisfies_the_protocol(self):
        from atlas.semantic_similarity import EmbeddingModel

        assert isinstance(NullEmbeddingModel(), EmbeddingModel)
