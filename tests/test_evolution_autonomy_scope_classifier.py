"""
Atlas Evolution Autonomy — Scope Classifier Tests — Phase 16.1

Verifies the closed, immutable scope map: deterministic scope →
components translation, exact-set classification with NO payload-based
inference, protected-scope refusal, and constitutional invariants
(IDENTITY/CODE never translatable into a state change).

Pure logic. No infra. No AI.
"""

import unittest

from atlas.evolution.autonomy.models import EvolutionRequest
from atlas.evolution.autonomy.scope_classifier import (
    SCOPE_COMPONENTS,
    STATE_SCOPES,
    classify_components,
    classify_request,
    components_for_scope,
    is_state_scope,
)
from atlas.evolution.governance.models import ScopeType


class TestClosedMap(unittest.TestCase):
    """The scope→components map is closed and immutable."""

    def test_map_is_immutable(self):
        with self.assertRaises(TypeError):
            SCOPE_COMPONENTS[ScopeType.CONFIG] = ("x",)  # type: ignore[index]

    def test_exact_entries_per_spec_d2(self):
        self.assertEqual(
            set(SCOPE_COMPONENTS[ScopeType.CONFIG]),
            {"config", "autonomy:config"},
        )
        self.assertEqual(
            set(SCOPE_COMPONENTS[ScopeType.MEMORY]),
            {"memory", "autonomy:memory"},
        )
        self.assertEqual(
            set(SCOPE_COMPONENTS[ScopeType.KNOWLEDGE]),
            {"knowledge", "autonomy:knowledge"},
        )
        self.assertEqual(
            set(SCOPE_COMPONENTS[ScopeType.CAPABILITY]),
            {"capability", "autonomy:capability"},
        )
        self.assertEqual(
            set(SCOPE_COMPONENTS[ScopeType.UNKNOWN]),
            {"governance:unknown"},
        )

    def test_protected_scopes_not_in_map(self):
        # IDENTITY and CODE must never be translatable components.
        self.assertNotIn(ScopeType.IDENTITY, SCOPE_COMPONENTS)
        self.assertNotIn(ScopeType.CODE, SCOPE_COMPONENTS)


class TestComponentsForScope(unittest.TestCase):
    """components_for_scope is deterministic per scope."""

    def test_config(self):
        self.assertEqual(
            set(components_for_scope(ScopeType.CONFIG)),
            {"config", "autonomy:config"},
        )

    def test_memory(self):
        self.assertEqual(
            set(components_for_scope(ScopeType.MEMORY)),
            {"memory", "autonomy:memory"},
        )

    def test_knowledge(self):
        self.assertEqual(
            set(components_for_scope(ScopeType.KNOWLEDGE)),
            {"knowledge", "autonomy:knowledge"},
        )

    def test_capability(self):
        self.assertEqual(
            set(components_for_scope(ScopeType.CAPABILITY)),
            {"capability", "autonomy:capability"},
        )

    def test_unknown(self):
        self.assertEqual(components_for_scope(ScopeType.UNKNOWN), ["governance:unknown"])

    def test_always_returns_new_list(self):
        first = components_for_scope(ScopeType.CONFIG)
        first.append("mutated")  # mutating the result must not poison the map
        second = components_for_scope(ScopeType.CONFIG)
        self.assertNotIn("mutated", second)

    def test_deterministic(self):
        self.assertEqual(
            components_for_scope(ScopeType.MEMORY),
            components_for_scope(ScopeType.MEMORY),
        )


class TestClassifyComponents(unittest.TestCase):
    """Exact-set classification only — no payload/free-form inference."""

    def test_classifies_closed_entries(self):
        self.assertEqual(
            classify_components(["config", "autonomy:config"]),
            ScopeType.CONFIG,
        )
        self.assertEqual(
            classify_components(["memory", "autonomy:memory"]),
            ScopeType.MEMORY,
        )
        self.assertEqual(
            classify_components(["knowledge", "autonomy:knowledge"]),
            ScopeType.KNOWLEDGE,
        )
        self.assertEqual(
            classify_components(["capability", "autonomy:capability"]),
            ScopeType.CAPABILITY,
        )

    def test_case_insensitive_set_match(self):
        self.assertEqual(
            classify_components(["CONFIG", "Autonomy:Config"]),
            ScopeType.CONFIG,
        )

    def test_unsorted_input_still_matches(self):
        self.assertEqual(
            classify_components(["autonomy:memory", "memory"]),
            ScopeType.MEMORY,
        )

    def test_no_free_form_keyword_inference(self):
        # A payload-derived list containing a single keyword must NOT be
        # classified as that scope — only exact closed entries match.
        self.assertEqual(classify_components(["config"]), ScopeType.UNKNOWN)
        self.assertEqual(classify_components(["memory"]), ScopeType.UNKNOWN)
        self.assertEqual(classify_components(["knowledge"]), ScopeType.UNKNOWN)
        self.assertEqual(classify_components(["capability"]), ScopeType.UNKNOWN)

    def test_extra_components_break_match(self):
        self.assertEqual(
            classify_components(["config", "autonomy:config", "sneaky"]),
            ScopeType.UNKNOWN,
        )

    def test_empty_components_are_unknown(self):
        self.assertEqual(classify_components([]), ScopeType.UNKNOWN)

    def test_identity_code_cannot_be_classified(self):
        # Even if a caller attempts protected components, they never map.
        self.assertEqual(classify_components(["identity"]), ScopeType.UNKNOWN)
        self.assertEqual(classify_components(["code"]), ScopeType.UNKNOWN)


class TestStateScopes(unittest.TestCase):
    """The closed state-scope set excludes constitutional protections."""

    def test_state_scopes(self):
        self.assertEqual(
            STATE_SCOPES,
            frozenset({
                ScopeType.CONFIG,
                ScopeType.MEMORY,
                ScopeType.KNOWLEDGE,
                ScopeType.CAPABILITY,
            }),
        )

    def test_is_state_scope(self):
        for scope in (
            ScopeType.CONFIG,
            ScopeType.MEMORY,
            ScopeType.KNOWLEDGE,
            ScopeType.CAPABILITY,
        ):
            self.assertTrue(is_state_scope(scope), scope.name)

    def test_protected_scopes_are_not_state_scopes(self):
        self.assertFalse(is_state_scope(ScopeType.IDENTITY))
        self.assertFalse(is_state_scope(ScopeType.CODE))
        self.assertFalse(is_state_scope(ScopeType.UNKNOWN))


class TestClassifyRequest(unittest.TestCase):
    """classify_request reads the declared target_scope only."""

    @staticmethod
    def _request(scope):
        return EvolutionRequest(
            request_id="AUTORQ-X",
            source="cli",
            target_scope=scope,
        )

    def test_declared_scope_wins(self):
        for scope in STATE_SCOPES:
            with self.subTest(scope=scope.name):
                self.assertEqual(classify_request(self._request(scope)), scope)

    def test_missing_scope_is_unknown(self):
        class NoScope:
            pass

        self.assertEqual(classify_request(NoScope()), ScopeType.UNKNOWN)

    def test_protected_scope_is_unknown(self):
        # A request cannot target identity/code in Phase 16; if one
        # somehow existed, classification fails CLOSED to UNKNOWN.
        req = EvolutionRequest(
            request_id="AUTORQ-Y",
            source="cli",
            target_scope=ScopeType.IDENTITY,
        )
        self.assertEqual(classify_request(req), ScopeType.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
