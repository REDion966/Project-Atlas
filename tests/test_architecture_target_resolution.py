"""Architectural TARGET RESOLUTION — capability-level validation.

Validates the CAPABILITY, not individual sentences: a natural-language surface
form is deterministically mapped onto a canonical Atlas architectural identity,
or Atlas honestly reports that it cannot.

The capability is derived, read-only data over the authoritative registries
exposed by ``ArchitectureModel``. It must never invent an identity, never
guess between two equally valid ones, and never turn an unknown target into a
known one.

Model independence: everything below is stdlib-only and contacts no provider.
"""

from __future__ import annotations

import sys

import pytest

sys.path.insert(0, r"F:\Project Atlas")

from atlas.conversation.reference_resolution import ReferenceResolutionStatus
from atlas.self_knowledge.architecture_resolver import (
    SUPPORTED_IDENTITY_TYPES,
    ArchitectureTargetResolver,
)

A_COMPONENT = "conversation_service"
A_CAPABILITY = "conversation"
CROSS_TYPE = "research"


@pytest.fixture(scope="module")
def resolver():
    """A resolver over the real Atlas registries (real model, no mocks)."""
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    try:
        # The repository map must exist for module/package identities.
        _ = atlas.repository_map
        model = atlas._architecture_model_snapshot()
        yield ArchitectureTargetResolver(model)
    finally:
        atlas.shutdown()


@pytest.fixture(scope="module")
def fresh_resolver():
    """An independently constructed resolver (fresh instance determinism)."""
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    try:
        _ = atlas.repository_map
        yield ArchitectureTargetResolver(atlas._architecture_model_snapshot())
    finally:
        atlas.shutdown()


# ---------------------------------------------------------------------------
# A-J. Surface-form coverage
# ---------------------------------------------------------------------------


class TestSurfaceForms:
    def test_canonical_id(self, resolver):
        result = resolver.resolve(A_COMPONENT)
        assert result.is_resolved
        assert result.canonical_id == A_COMPONENT
        assert result.identity_type == "component"

    def test_spaced_form(self, resolver):
        assert resolver.resolve("conversation service").is_resolved

    def test_pascal_case(self, resolver):
        result = resolver.resolve("ConversationService")
        assert result.is_resolved
        assert result.canonical_id == A_COMPONENT

    def test_kebab_case(self, resolver):
        assert resolver.resolve("conversation-service").is_resolved

    def test_case_variants(self, resolver):
        assert resolver.resolve("CONVERSATION SERVICE").is_resolved
        assert resolver.resolve("Conversation Service").is_resolved

    def test_dotted_path_resolves_to_the_module(self, resolver):
        result = resolver.resolve("atlas.conversation.conversation_service")
        assert result.is_resolved
        assert result.identity_type == "module"

    def test_article_prefixed_form(self, resolver):
        result = resolver.resolve("the conversation service")
        assert result.is_resolved
        assert result.canonical_id == A_COMPONENT

    def test_multi_word_longest_match_prefers_the_specific_identity(self, resolver):
        """The longer, more specific surface wins over a shorter substring."""
        result = resolver.resolve("atlas.conversation.conversation_service")
        assert result.canonical_id == "atlas.conversation.conversation_service"
        assert result.identity_type == "module"

    def test_overlapping_aliases_do_not_manufacture_ambiguity(self, resolver):
        """Several surface forms for ONE identity are not ambiguity."""
        for surface in (
            A_COMPONENT,
            "conversation service",
            "the conversation service",
            "ConversationService",
            "conversation-service",
        ):
            result = resolver.resolve(surface)
            assert result.is_resolved, surface
            assert result.canonical_id == A_COMPONENT, surface

    def test_word_boundaries_are_respected(self, resolver):
        """A partial word must not match an identity."""
        assert resolver.resolve("conversationservic").is_unresolved or (
            resolver.resolve("conversationservic").is_ambiguous
        )


# ---------------------------------------------------------------------------
# K-M. The settled ambiguity policy
# ---------------------------------------------------------------------------


class TestAmbiguityPolicy:
    def test_cross_type_collision_without_expected_type_is_ambiguous(self, resolver):
        result = resolver.resolve(CROSS_TYPE)
        assert result.is_ambiguous
        assert result.canonical_id == ""
        kinds = {c.identity_type for c in result.candidates}
        assert kinds == {"component", "capability"}

    def test_expected_component_resolves_the_component(self, resolver):
        result = resolver.resolve(CROSS_TYPE, expected_type="component")
        assert result.is_resolved
        assert result.canonical_id == CROSS_TYPE
        assert result.identity_type == "component"

    def test_expected_capability_resolves_the_capability(self, resolver):
        result = resolver.resolve(CROSS_TYPE, expected_type="capability")
        assert result.is_resolved
        assert result.canonical_id == CROSS_TYPE
        assert result.identity_type == "capability"

    def test_ambiguous_never_selects_one_identity(self, resolver):
        """The whole point of AMBIGUOUS: nothing is silently chosen."""
        result = resolver.resolve(CROSS_TYPE)
        assert result.canonical_id == ""
        assert result.identity_type == ""
        assert len(result.candidates) >= 2

    def test_a_tool_is_a_capability_not_a_separate_namespace(self, resolver):
        """A tool exposed as a tool must not read as ambiguous."""
        result = resolver.resolve("echo")
        assert result.is_resolved
        assert result.identity_type == "capability"
        assert "tool" not in SUPPORTED_IDENTITY_TYPES


# ---------------------------------------------------------------------------
# O-Q. Fail-closed behaviour
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_nonexistent_target_is_unresolved(self, resolver):
        result = resolver.resolve("zzz nonexistent widget")
        assert result.is_unresolved
        assert result.canonical_id == ""

    def test_malformed_input_is_unresolved(self, resolver):
        for bad in ("", "   ", "...", "!!!"):
            result = resolver.resolve(bad)
            assert result.is_unresolved, bad

    def test_non_string_input_is_unresolved(self, resolver):
        assert resolver.resolve(None).is_unresolved
        assert resolver.resolve(12345).is_unresolved

    def test_unknown_expected_type_is_unresolved_and_never_coerced(self, resolver):
        result = resolver.resolve(CROSS_TYPE, expected_type="not-a-kind")
        assert result.is_unresolved
        assert result.canonical_id == ""
        assert "unsupported_expected_type" in result.evidence

    def test_semantic_paraphrase_is_out_of_scope_and_unresolved(self, resolver):
        """Deliberately NOT solved by this capability."""
        result = resolver.resolve("the thing that handles conversations")
        assert result.is_unresolved


# ---------------------------------------------------------------------------
# R-T. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_repeated_resolution_is_identical(self, resolver):
        first = resolver.resolve(CROSS_TYPE)
        for _ in range(4):
            again = resolver.resolve(CROSS_TYPE)
            assert again.status is first.status
            assert again.candidates == first.candidates

    def test_fresh_resolver_produces_identical_results(self, resolver, fresh_resolver):
        for surface in (A_COMPONENT, CROSS_TYPE, "zzz widget", "the conversation service"):
            a = resolver.resolve(surface)
            b = fresh_resolver.resolve(surface)
            assert a.status is b.status, surface
            assert a.canonical_id == b.canonical_id, surface
            assert a.candidates == b.candidates, surface

    def test_index_is_deterministic_across_instances(self, resolver, fresh_resolver):
        assert resolver.identities() == fresh_resolver.identities()


# ---------------------------------------------------------------------------
# U-V. Index / registry consistency and authority
# ---------------------------------------------------------------------------


class TestIndexConsistency:
    def test_index_holds_no_invented_identities(self, resolver):
        """Every indexed identity must exist in an authoritative registry."""
        model_ids = {
            ("component", c.name) for c in resolver_model_components(resolver)
        } | {
            ("capability", c.name) for c in resolver_model_capabilities(resolver)
        } | {
            ("module", m)
            for m in resolver_model_modules(resolver)
        } | {
            ("package", m)
            for m in resolver_model_modules(resolver)
            if m in resolver_packages(resolver)
        }
        for identity in resolver.identities():
            key = (identity.identity_type, identity.canonical_id)
            assert key in model_ids, f"invented identity: {key}"

    def test_resolved_canonical_id_is_authoritative(self, resolver):
        for surface in (A_COMPONENT, "the conversation service", CROSS_TYPE):
            result = resolver.resolve(surface, expected_type="component")
            if result.is_resolved:
                assert resolver.is_authoritative_id(
                    result.canonical_id, result.identity_type
                ), surface

    def test_identity_count_is_bounded_and_non_empty(self, resolver):
        assert resolver.identity_count > 0
        assert resolver.entry_count >= resolver.identity_count

    def test_resolution_result_is_json_safe(self, resolver):
        import json

        payload = resolver.resolve(CROSS_TYPE).to_dict()
        assert json.loads(json.dumps(payload))["status"] == "ambiguous"


# ---------------------------------------------------------------------------
# Helpers: reach the authoritative model the resolver was built from
# ---------------------------------------------------------------------------


def _model():
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    _ = atlas.repository_map
    return atlas


def resolver_model_components(resolver):
    return resolver_model(resolver).components


def resolver_model_capabilities(resolver):
    return resolver_model(resolver).capabilities


def resolver_model_modules(resolver):
    model = resolver_model(resolver)
    rm = model.repository_map
    return [i.module for i in (rm.modules if rm else ())]


def resolver_packages(resolver):
    model = resolver_model(resolver)
    rm = model.repository_map
    return {i.module for i in (rm.modules if rm else ()) if getattr(i, "is_package", False)}


_MODELS: dict[int, object] = {}


def resolver_model(resolver):
    """Rebuild the same model shape the module fixtures used (read-only)."""
    key = id(resolver)
    if key not in _MODELS:
        from atlas.kernel.atlas import Atlas
        from atlas.self_knowledge.architecture_model import build_architecture_model
        from atlas.lifecycle.component_registry import ComponentRegistry

        atlas = Atlas()
        atlas.start()
        try:
            _ = atlas.repository_map
            _MODELS[key] = build_architecture_model(
                component_registry=atlas._component_registry,
                capability_model=atlas.capability_model(),
                repository_map=atlas.repository_map,
            )
        finally:
            atlas.shutdown()
    return _MODELS[key]
