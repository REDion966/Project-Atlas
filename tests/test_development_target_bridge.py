"""DAY 2 — the natural-language → ``target_components`` bridge.

The conversational development path produced a ``DevelopmentNeed`` with an EMPTY
``target_components``, so localization and the authoring context fell back to the
BM25 top hit. ``Atlas._development_target_components`` now derives the target from
the request's own words using the EXISTING repository map and tokenizer.

The tests below are deliberately GENERAL: they assert the rule (name tokens must
all appear; at least two tokens; exactly one match required; fail closed) rather
than any one probe sentence.
"""

from __future__ import annotations

import pathlib

import pytest

from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.model_assisted_supplier import ModelAssistedChangeSupplier

#: Requests that name a real module, with the module each must resolve to.
NAMED = [
    ("the development gap module",
     "I want you to improve the development gap module while preserving its "
     "existing interface and behavior.",
     "atlas.evolution.development_gap"),
    ("the development gap module (investigation)",
     "Investigate the development gap module.",
     "atlas.evolution.development_gap"),
    ("the conversation service",
     "Improve the conversation service.",
     "atlas.conversation.conversation_service"),
    ("the repository map",
     "Fix the failing test for the repository map while preserving the interface.",
     "atlas.research.repository_map"),
    ("the promotion gate",
     "Improve the promotion gate but preserve compatibility.",
     "atlas.evolution.promotion_gate"),
]

#: Requests that must NOT produce a target (never a guess).
UNRESOLVED = [
    "Improve this.",
    "Make it better.",
    "Improve the capability.",
    "Change the implementation, but do not change the public interface or "
    "existing behavior.",
    "Change the existing helper so that it rejects an empty value while "
    "preserving its current public interface.",
    "Make the memory service faster.",  # two real modules share the name tokens
    "",
    "   ",
]


@pytest.fixture(scope="module")
def kernel():
    import pkgutil
    import tempfile

    import atlas.storage as storage_pkg

    tmp = pathlib.Path(tempfile.mkdtemp())
    db = tmp / "day2.db"
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


# ---------------------------------------------------------------------------
# 1. The rule
# ---------------------------------------------------------------------------


class TestTargetBridge:
    @pytest.mark.parametrize("label,text,expected", NAMED)
    def test_a_named_module_is_resolved(self, kernel, label, text, expected):
        assert kernel._development_target_components(text) == (expected,)

    @pytest.mark.parametrize("text", UNRESOLVED)
    def test_no_target_is_ever_guessed(self, kernel, text):
        assert kernel._development_target_components(text) == ()

    def test_a_generic_word_alone_never_selects_a_module(self, kernel):
        for generic in ("service", "module", "models", "capability", "development"):
            assert kernel._development_target_components(f"Improve the {generic}.") == ()

    def test_test_modules_are_never_selected(self, kernel):
        modules = kernel.repository_map.modules
        for _label, text, expected in NAMED:
            for match in kernel._development_target_components(text):
                assert not match.startswith("tests.")
                assert match in {m.module for m in modules}

    def test_the_result_is_bounded_to_one_module(self, kernel):
        assert len(kernel._development_target_components(NAMED[0][1])) <= 1

    def test_the_bridge_is_deterministic(self, kernel):
        for _label, text, _expected in NAMED:
            first = kernel._development_target_components(text)
            assert first == kernel._development_target_components(text)

    def test_non_text_is_safe(self, kernel):
        assert kernel._development_target_components(None) == ()
        assert kernel._development_target_components(42) == ()

    def test_the_rule_needs_all_name_tokens(self, kernel):
        # "gap" alone is one token of a two-token name -> not enough.
        assert kernel._development_target_components("Improve the gap.") == ()
        # Both tokens present -> resolves.
        assert kernel._development_target_components("improve development gap") == (
            "atlas.evolution.development_gap",
        )


# ---------------------------------------------------------------------------
# 2. Integration: the need and the authoring context
# ---------------------------------------------------------------------------


class TestBridgeIntegration:
    def test_the_driver_carries_the_target_onto_the_need(self, kernel):
        """`metadata["target_components"]` is the EXISTING contract the driver reads."""
        from atlas.evolution.development_driver import DevelopmentDriver
        from atlas.evolution.development_gap import assess_development_gap

        request = NAMED[0][1]
        target = kernel._development_target_components(request)
        assert target
        need = DevelopmentDriver._build_need(
            request,
            assess_development_gap(request, capability_names=()),
            {"target_components": target},
        )
        assert need.target_components == target

    def test_authoring_context_anchors_to_the_declared_target(self, kernel):
        supplier = ModelAssistedChangeSupplier(
            authoring_model=lambda p: "{}",
            repository_map=kernel.repository_map,
            architecture_model=kernel.architecture_model(),
        )
        for _label, text, expected in NAMED[:3]:
            need = DevelopmentNeed(title=text, summary="preserve the interface",
                                   target_components=(expected,))
            context = supplier._build_authoring_context(need)
            first = context.splitlines()[1]
            assert first.startswith(f"- 1. {expected} ")
            assert "declared boundary for" in context

    def test_understanding_and_bridging_authorize_nothing(self, kernel):
        before = kernel.pending_promotion_reviews()
        for _label, text, _expected in NAMED:
            kernel._development_target_components(text)
        assert kernel.pending_promotion_reviews() == before

    def test_the_bridge_adds_no_terminal_state(self, kernel):
        """An unsupported change still terminates at the EXISTING fail-closed boundary."""
        result = kernel.run_development_driver(
            NAMED[0][1],
            metadata={"target_components": kernel._development_target_components(NAMED[0][1])},
        )
        assert result.terminal.value == "author_unavailable"
        assert result.proposal_id == ""
        assert kernel.pending_promotion_reviews() == []


# ---------------------------------------------------------------------------
# 3. Determinism and governance
# ---------------------------------------------------------------------------


class TestDeterminismAndGovernance:
    def test_repeated_conversational_runs_agree(self, kernel):
        for _label, text, expected in NAMED:
            first = kernel._development_target_components(text)
            second = kernel._development_target_components(text)
            assert first == second == (expected,)

    def test_ambiguous_requests_never_reach_authoring(self, kernel):
        before = len(kernel.pending_promotion_reviews())
        for text in UNRESOLVED:
            target = kernel._development_target_components(text)
            assert target == ()
            result = kernel.run_development_driver(text, metadata=None)
            assert result.proposal_id == ""
        assert len(kernel.pending_promotion_reviews()) == before

    def test_investigation_requests_stay_read_only(self, kernel):
        reply = kernel.chat("Investigate the development gap module. Don't change anything.")
        assert "## Investigation" in (reply.content or "")
        assert kernel.pending_promotion_reviews() == []
