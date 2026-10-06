"""Development capability adjudication — the capability-name source and rule.

Pins the bounded deterministic correction to ``atlas.evolution.development_gap``
plus the kernel wiring:

  * the capability vocabulary for DEVELOPMENT-GAP adjudication is the EXISTING
    operational capability catalogue (id + declared aliases), which the unified
    capability model already recognises as ``CapabilityKind.OPERATIONAL`` — not
    the EXECUTION registry's internal handler names;
  * a capability match must rest on a DISTINGUISHING token, so a generic word
    ("capability", "conversation", "service", ...) can never by itself make a
    short request read as ALREADY_SUPPORTED.

Every test is a regression for one promise of that change. Nothing here executes,
promotes, or mutates anything.
"""

from __future__ import annotations

import pkgutil

import pytest

import atlas.storage as storage_pkg
from atlas.evolution import development_gap as dg
from atlas.evolution.development_gap import (
    GENERIC_CAPABILITY_TOKENS,
    DevelopmentGapKind,
    _is_equivalence_evidence,
    assess_development_gap,
)

REQUEST_IMPROVE_INVESTIGATION = "Improve the investigation capability."
REQUEST_INVESTIGATE_CONVERSATION = "Investigate the conversation service."
REQUEST_DOCUMENTED_REGRESSION = "Export the conversation history as markdown."
REQUEST_ABSENT = "Add quantum entanglement scheduling support."


def _patch_stores(monkeypatch, tmp_path):
    db = tmp_path / "kernel.db"
    for info in pkgutil.iter_modules(storage_pkg.__path__):
        try:
            module = __import__(f"atlas.storage.{info.name}", fromlist=["*"])
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and hasattr(obj, "DEFAULT_DB_PATH"):
                monkeypatch.setattr(obj, "DEFAULT_DB_PATH", db)


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    _patch_stores(monkeypatch, tmp_path)
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    try:
        yield atlas
    finally:
        atlas.shutdown()


def _git_head() -> str:
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(root),
        capture_output=True,
        text=True,
    ).stdout.strip()


# ---------------------------------------------------------------------------
# 1. The authoritative capability-name source
# ---------------------------------------------------------------------------


class TestCapabilityNameSource:
    def test_wiring_uses_the_operational_capability_catalogue(self, kernel):
        names = kernel._development_capability_names()  # noqa: SLF001
        assert names, "the operational capability vocabulary must not be empty"
        # A user-facing capability and its declared alias are both present.
        assert "investigate" in names
        assert "investigation" in names
        # The operational vocabulary is used, not the execution registry.
        assert "plan" in names and "verify" in names and "report" in names

    def test_wiring_is_deterministic_and_duplicate_free(self, kernel):
        first = kernel._development_capability_names()  # noqa: SLF001
        second = kernel._development_capability_names()  # noqa: SLF001
        assert first == second
        assert len(first) == len(set(first))

    def test_wiring_is_a_projection_of_the_existing_catalogue(self, kernel):
        from atlas.self_knowledge.operational_capabilities import (
            all_operational_capabilities,
        )

        expected: list[str] = []
        for capability in all_operational_capabilities():
            for surface in (capability.id, *capability.aliases):
                if surface and surface not in expected:
                    expected.append(surface)
        assert kernel._development_capability_names() == tuple(expected)  # noqa: SLF001

    def test_the_execution_registry_is_no_longer_the_source(self, kernel):
        execution = set(kernel._registered_capability_names())  # noqa: SLF001
        development = set(kernel._development_capability_names())  # noqa: SLF001
        # The old source contained generic words and omitted every user-facing
        # capability; the new source is the operational vocabulary.
        assert "conversation" not in development
        assert "investigate" not in execution


# ---------------------------------------------------------------------------
# 2. The equivalence rule — a distinguishing token is required
# ---------------------------------------------------------------------------


class TestEquivalenceRule:
    def test_a_generic_token_alone_is_not_evidence(self):
        assert _is_equivalence_evidence({"capability"}, 1) is False
        assert _is_equivalence_evidence({"conversation"}, 1) is False
        assert _is_equivalence_evidence({"service"}, 2) is False

    def test_a_distinguishing_token_is_evidence(self):
        assert _is_equivalence_evidence({"investigation"}, 3) is True
        assert _is_equivalence_evidence({"research"}, 3) is True

    def test_generic_tokens_never_rescue_an_otherwise_weak_overlap(self):
        assert _is_equivalence_evidence({"capability", "service"}, 2) is False

    def test_mixed_overlap_is_evidence_when_a_distinguishing_token_is_present(self):
        assert _is_equivalence_evidence({"capability", "investigation"}, 3) is True

    def test_the_substantial_share_rule_is_unchanged(self):
        # Four request tokens need two shared tokens; one is not enough.
        assert _is_equivalence_evidence({"research"}, 4) is False
        assert _is_equivalence_evidence({"research", "query"}, 4) is True

    def test_the_generic_set_is_closed_and_contains_no_capability(self):
        for word in ("capability", "conversation", "service", "system", "analysis",
                     "support", "task", "model", "chat", "operation"):
            assert word in GENERIC_CAPABILITY_TOKENS
        for capability in ("investigate", "plan", "verify", "report", "research"):
            assert capability not in GENERIC_CAPABILITY_TOKENS


# ---------------------------------------------------------------------------
# 3. The four required real cases (through the real kernel wiring)
# ---------------------------------------------------------------------------


class TestRequiredCases:
    def _assess(self, kernel, request):
        return assess_development_gap(
            request,
            capability_names=kernel._development_capability_names(),  # noqa: SLF001
            knowledge_retriever=None,
        )

    def test_case_1_existing_capability_with_improvement_intent(self, kernel):
        gap = self._assess(kernel, REQUEST_IMPROVE_INVESTIGATION)
        assert gap.kind is DevelopmentGapKind.ALREADY_SUPPORTED
        # The evidence identifies the ACTUAL investigate capability — never the
        # generic word "capability" and never an unrelated internal name.
        assert set(gap.matched) & {"investigate", "investigation"}
        assert "capability" not in gap.matched
        assert "capability_detail" not in gap.matched

    def test_case_2_real_operational_capability(self, kernel):
        gap = self._assess(kernel, REQUEST_INVESTIGATE_CONVERSATION)
        assert gap.kind is DevelopmentGapKind.ALREADY_SUPPORTED
        assert "investigate" in gap.matched
        # Not justified by the generic word "conversation".
        assert "conversation" not in gap.matched
        assert "open_conversation" not in gap.matched

    def test_case_3_generic_short_request_is_not_already_supported(self, kernel):
        for request in (
            "Check the conversation service.",
            "Improve the service system.",
            "Handle the capability task.",
        ):
            gap = self._assess(kernel, request)
            assert gap.kind is not DevelopmentGapKind.ALREADY_SUPPORTED, request
            assert gap.matched == (), request

    def test_case_4_documented_regression_is_protected(self, kernel):
        gap = self._assess(kernel, REQUEST_DOCUMENTED_REGRESSION)
        assert gap.kind is DevelopmentGapKind.MISSING_KNOWLEDGE
        assert gap.matched == ()

    def test_case_5_absent_capability_keeps_the_knowledge_distinction(self, kernel):
        names = kernel._development_capability_names()  # noqa: SLF001
        without = assess_development_gap(REQUEST_ABSENT, capability_names=names)
        assert without.kind is DevelopmentGapKind.MISSING_KNOWLEDGE

        class _Retriever:
            def retrieve(self, query):
                return []

        with_empty_store = assess_development_gap(
            REQUEST_ABSENT, capability_names=names, knowledge_retriever=_Retriever()
        )
        assert with_empty_store.kind is DevelopmentGapKind.MISSING_KNOWLEDGE
        # MISSING_CAPABILITY still requires the subject to be known.
        assert with_empty_store.kind is not DevelopmentGapKind.MISSING_CAPABILITY

    def test_improvement_intent_recognises_other_real_capabilities(self, kernel):
        for request, expected in (
            ("Improve the plan capability.", "plan"),
            ("Improve the verify capability.", "verify"),
            ("Improve the report capability.", "report"),
        ):
            gap = self._assess(kernel, request)
            assert gap.kind is DevelopmentGapKind.ALREADY_SUPPORTED, request
            assert expected in gap.matched, request


# ---------------------------------------------------------------------------
# 4. Existing pinned behaviour must not move
# ---------------------------------------------------------------------------


class TestExistingBehaviourPreserved:
    def test_short_invocation_shaped_overlap_is_still_supported(self):
        gap = assess_development_gap(
            "run the research pipeline", capability_names=["research.query"]
        )
        assert gap.kind is DevelopmentGapKind.ALREADY_SUPPORTED
        assert gap.matched == ("research.query",)

    def test_genuine_multi_token_name_is_still_supported(self):
        gap = assess_development_gap(
            "export the conversation history as markdown",
            capability_names=["conversation_history_export"],
        )
        assert gap.kind is DevelopmentGapKind.ALREADY_SUPPORTED

    def test_incidental_long_request_is_still_not_supported(self):
        gap = assess_development_gap(
            "Add a capability that lets me export the conversation history "
            "as markdown.",
            capability_names=["conversation"],
        )
        assert gap.kind is not DevelopmentGapKind.ALREADY_SUPPORTED

    def test_underscored_and_spaced_forms_still_agree(self):
        gap = assess_development_gap("memory search", capability_names=["memory_search"])
        assert gap.kind is DevelopmentGapKind.ALREADY_SUPPORTED

    def test_malformed_input_is_still_unclear(self):
        for bad in ("", "   ", None, 42, [], {}):
            assert assess_development_gap(bad).kind is DevelopmentGapKind.UNCLEAR


# ---------------------------------------------------------------------------
# 5. The real driver + determinism + governance
# ---------------------------------------------------------------------------


class TestRealDriver:
    def test_improvement_request_terminates_already_supported(self, kernel):
        head = _git_head()
        result = kernel.run_development_driver(REQUEST_IMPROVE_INVESTIGATION)
        assert result.terminal.value == "already_supported"
        assert result.proposal_id == ""
        assert result.authorization_id == ""
        # No development work of any kind was started.
        assert kernel.pending_promotion_reviews() == []
        assert _git_head() == head

    def test_already_supported_request_creates_no_development_state(self, kernel):
        kernel.run_development_driver(REQUEST_INVESTIGATE_CONVERSATION)
        assert kernel.pending_promotion_reviews() == []

    def test_classification_is_deterministic(self, kernel):
        names = kernel._development_capability_names()  # noqa: SLF001
        first = assess_development_gap(REQUEST_IMPROVE_INVESTIGATION,
                                       capability_names=names)
        second = assess_development_gap(REQUEST_IMPROVE_INVESTIGATION,
                                        capability_names=names)
        assert first == second
        assert first.matched == second.matched
        assert first.evidence == second.evidence

    def test_terminal_is_stable_across_a_rebuilt_kernel(self, kernel, tmp_path,
                                                        monkeypatch):
        first = kernel.run_development_driver(REQUEST_IMPROVE_INVESTIGATION)
        _patch_stores(monkeypatch, tmp_path)
        from atlas.kernel.atlas import Atlas

        rebuilt = Atlas()
        rebuilt.start()
        try:
            second = rebuilt.run_development_driver(REQUEST_IMPROVE_INVESTIGATION)
        finally:
            rebuilt.shutdown()
        assert first.terminal == second.terminal
        assert first.gap.kind == second.gap.kind
        assert first.gap.matched == second.gap.matched

    def test_the_adjudicator_remains_model_free(self):
        """The classifier has no model, network or storage dependency."""
        import inspect

        source = inspect.getsource(dg)
        for forbidden in ("openai", "anthropic", "requests", "http", "socket"):
            assert forbidden not in source.lower()
