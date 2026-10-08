"""Command 3 — kernel integration of the OPTIONAL semantic-similarity specialist.

Deterministic: the embedding transport is always injected, never the network.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tests.safe_kernel_config import (  # noqa: E402
    SAFE_CONFIG_TOML,
    bound_configuration,
)

ENABLED_CONFIG_TOML = SAFE_CONFIG_TOML + """
[specialists]
enabled = false
embeddings_enabled = true
embeddings_model = "test-embed"
embeddings_provider_id = "test.embeddings"
"""

_DIMENSION = 8


def _signal_transport(request):
    """A deterministic fake runtime: axis 0 = 'relevance', axis 1 = 'kernel'."""
    vectors = []
    for text in request.get("texts", ()):
        lowered = text.lower()
        vectors.append(
            [
                1.0 if "relevance" in lowered else 0.0,
                0.2 if "kernel" in lowered else 0.0,
            ]
            + [0.0] * (_DIMENSION - 2)
        )
    return {"embeddings": vectors}


def _build_atlas(config_text: str):
    import tempfile

    import atlas.kernel.atlas as kernel_mod
    from atlas.kernel.atlas import Atlas

    directory = pathlib.Path(tempfile.mkdtemp())
    (directory / "config.toml").write_text(config_text, encoding="utf-8")
    original = kernel_mod.Configuration
    kernel_mod.Configuration = bound_configuration(directory / "config.toml")
    try:
        atlas = Atlas()
        atlas.start()
    finally:
        kernel_mod.Configuration = original
    return atlas


@pytest.fixture(scope="module")
def deterministic_kernel():
    """The DEFAULT posture: no embedding specialist configured."""
    return _build_atlas(SAFE_CONFIG_TOML)


@pytest.fixture(scope="module")
def semantic_kernel():
    """The OPT-IN posture: embeddings enabled over an injected fake runtime."""
    import atlas.specialist_transport as transport_mod

    original = transport_mod.ollama_embedding_transport
    transport_mod.ollama_embedding_transport = (
        lambda **kwargs: _signal_transport
    )
    try:
        atlas = _build_atlas(ENABLED_CONFIG_TOML)
    finally:
        transport_mod.ollama_embedding_transport = original
    return atlas


class TestDeterministicDefault:
    def test_no_specialist_is_wired_by_default(self, deterministic_kernel):
        assert deterministic_kernel._embedding_model is None
        assert deterministic_kernel.semantic_similarity_available() is False

    def test_search_returns_atlas_own_order_unchanged(self, deterministic_kernel):
        result = deterministic_kernel.semantic_module_search(
            "why is knowledge stored twice", limit=5
        )
        assert result["available"] is False
        assert result["applied"] is False
        assert result["order"] == result["deterministic_order"]

    def test_the_deterministic_path_is_untouched(self, deterministic_kernel):
        result = deterministic_kernel.semantic_module_search("ranking", limit=5)
        assert result["scores"] == []
        assert result["provider_id"] == ""
        assert result["model_id"] == ""


class TestOptionalSpecialist:
    def test_the_specialist_is_wired_when_opted_in(self, semantic_kernel):
        assert semantic_kernel.semantic_similarity_available() is True

    def test_the_specialist_may_only_reorder_candidates(self, semantic_kernel):
        result = semantic_kernel.semantic_module_search(
            "relevance ranking of repository modules", limit=6
        )
        assert sorted(result["order"]) == sorted(result["deterministic_order"])
        assert len(result["order"]) == len(result["deterministic_order"])

    def test_the_decision_is_reported_and_auditable(self, semantic_kernel):
        result = semantic_kernel.semantic_module_search("relevance", limit=6)
        assert "applied" in result
        assert result["reason"]
        assert "deterministic_order" in result

    def test_the_surface_carries_no_authority(self, semantic_kernel):
        result = semantic_kernel.semantic_module_search("relevance", limit=6)
        for forbidden in (
            "authorized",
            "approved",
            "executed",
            "promoted",
            "apply",
            "promote",
        ):
            assert forbidden not in result

    def test_the_result_is_deterministic(self, semantic_kernel):
        first = semantic_kernel.semantic_module_search("relevance", limit=6)
        second = semantic_kernel.semantic_module_search("relevance", limit=6)
        assert first["order"] == second["order"]
        assert first["scores"] == second["scores"]

    def test_an_empty_query_is_refused(self, semantic_kernel):
        result = semantic_kernel.semantic_module_search("", limit=6)
        assert result["applied"] is False


class TestRepositoryUnchanged:
    def test_the_semantic_surface_never_touches_the_repository(self, semantic_kernel):
        import hashlib

        repo = pathlib.Path(__file__).resolve().parents[1]
        target = repo / "atlas" / "research" / "repository_map.py"
        before = hashlib.sha256(target.read_bytes()).hexdigest()
        semantic_kernel.semantic_module_search("repository map symbols", limit=5)
        after = hashlib.sha256(target.read_bytes()).hexdigest()
        assert before == after
