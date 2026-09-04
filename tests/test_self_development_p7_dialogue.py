"""P7.3 — Development need dialogue/confirmation contract tests.

Covers explanation, confirmation semantics, denial, ambiguous/stale handling,
explicit-development exclusion, advisory gating, provenance, F9 boundary, and
dependency direction. Preserves P7.1 and P7.2 tests.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from atlas.conversation.development_need_detector import (
    AdvisorySignal,
    DetectedDevelopmentNeed,
    DevelopmentNeedDetector,
    DevelopmentSignalKind,
)
from atlas.conversation.development_need_dialogue import (
    ConfirmationStatus,
    DevelopmentNeedDialogue,
    ExplicitDevelopmentIntent,
)

_ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def dialogue():
    return DevelopmentNeedDialogue()


@pytest.fixture
def detector():
    return DevelopmentNeedDetector()


def _need(signal_kind, *, capability="", reason="", evidence=(), principal_id="", authority="", session_id=""):
    return DetectedDevelopmentNeed(
        signal_kind=signal_kind,
        reason=reason or f"Test {signal_kind} reason.",
        evidence=evidence,
        capability=capability,
        principal_id=principal_id,
        authority=authority,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# Explanation
# ---------------------------------------------------------------------------


class TestExplanation:
    def test_detected_need_produces_explanation(self, dialogue):
        need = _need(DevelopmentSignalKind.CAPABILITY_GAP, capability="quantum_stabilizer")
        msg = dialogue.explain(need)
        assert msg.role == "assistant"
        assert msg.content
        assert "quantum_stabilizer" in msg.content

    def test_explanation_includes_evidence(self, dialogue):
        need = _need(
            DevelopmentSignalKind.UNRESOLVED_ACTION,
            evidence=("missing tool: stabilizer",),
        )
        msg = dialogue.explain(need)
        assert "missing tool: stabilizer" in msg.content

    def test_explanation_asks_for_confirmation(self, dialogue):
        need = _need(DevelopmentSignalKind.CAPABILITY_GAP, capability="x")
        msg = dialogue.explain(need)
        assert "yes or no" in msg.content.lower()

    def test_explanation_tags_awaiting_confirmation_metadata(self, dialogue):
        need = _need(DevelopmentSignalKind.CAPABILITY_GAP, capability="x")
        msg = dialogue.explain(need)
        assert msg.metadata["development_need_dialogue"]["status"] == "awaiting_confirmation"
        assert msg.metadata["development_need_dialogue"]["signal_kind"] == "capability_gap"

    def test_explanation_for_each_signal_kind(self, dialogue):
        for kind in DevelopmentSignalKind:
            need = _need(kind, capability="thing")
            msg = dialogue.explain(need)
            assert msg.content, f"empty explanation for {kind}"


# ---------------------------------------------------------------------------
# Confirmation semantics
# ---------------------------------------------------------------------------


class TestConfirmationSemantics:
    @pytest.mark.parametrize(
        "reply",
        ["yes", "YES", "Yes", "yeah", "yep", "sure", "ok", "okay", "absolutely",
         "definitely", "go ahead", "please do", "by all means", "confirmed",
         "sounds good", "roger", "aye", "fine", "proceed"],
    )
    def test_explicit_affirmative_confirms(self, dialogue, reply):
        need = _need(DevelopmentSignalKind.CAPABILITY_GAP, capability="x")
        assert dialogue.interpret_confirmation(reply, need) == ConfirmationStatus.CONFIRMED

    @pytest.mark.parametrize(
        "reply",
        ["no", "No", "nope", "nah", "never mind", "not now", "maybe later",
         "i decline", "do not", "dont", "pass", "skip", "stop", "decline",
         "reject", "deny", "no thanks"],
    )
    def test_explicit_negative_denies(self, dialogue, reply):
        need = _need(DevelopmentSignalKind.CAPABILITY_GAP, capability="x")
        assert dialogue.interpret_confirmation(reply, need) == ConfirmationStatus.DENIED

    def test_confirmation_preserves_provenance(self, dialogue):
        need = _need(
            DevelopmentSignalKind.CAPABILITY_GAP,
            capability="x",
            principal_id="alice",
            authority="user",
            session_id="sess-1",
        )
        intent = dialogue.build_intent(need)
        assert intent.principal_id == "alice"
        assert intent.authority == "user"
        assert intent.session_id == "sess-1"


# ---------------------------------------------------------------------------
# Denial behavior
# ---------------------------------------------------------------------------


class TestDenialBehavior:
    def test_denial_does_not_create_intent(self, dialogue):
        need = _need(DevelopmentSignalKind.CAPABILITY_GAP, capability="x")
        status = dialogue.interpret_confirmation("no", need)
        assert status == ConfirmationStatus.DENIED
        # No intent is produced on denial.
        msg = dialogue.denied_response()
        assert msg.role == "assistant"
        assert "won't propose" in msg.content.lower()

    def test_denial_response_metadata(self, dialogue):
        msg = dialogue.denied_response()
        assert msg.metadata["development_need_dialogue"]["status"] == "denied"


# ---------------------------------------------------------------------------
# Ambiguous / stale context
# ---------------------------------------------------------------------------


class TestAmbiguousAndStale:
    @pytest.mark.parametrize(
        "reply",
        ["", "   ", "maybe", "I don't know", "tell me more", "hmm", "possibly",
         "what do you think", "the weather is nice"],
    )
    def test_ambiguous_or_unrelated_is_ambiguous(self, dialogue, reply):
        need = _need(DevelopmentSignalKind.CAPABILITY_GAP, capability="x")
        assert dialogue.interpret_confirmation(reply, need) == ConfirmationStatus.AMBIGUOUS

    def test_mixed_affirmative_negative_is_ambiguous(self, dialogue):
        need = _need(DevelopmentSignalKind.CAPABILITY_GAP, capability="x")
        assert dialogue.interpret_confirmation("yes but actually no", need) == ConfirmationStatus.AMBIGUOUS
        assert dialogue.interpret_confirmation("no, wait, yes", need) == ConfirmationStatus.AMBIGUOUS

    def test_no_pending_context_fails_closed(self, dialogue):
        assert dialogue.interpret_confirmation("yes", None) == ConfirmationStatus.NO_PENDING_CONTEXT
        # Even a clear "yes" must not confirm without pending context.
        assert dialogue.interpret_confirmation("absolutely", None) == ConfirmationStatus.NO_PENDING_CONTEXT

    def test_ambiguous_yields_clarification_reask(self, dialogue):
        msg = dialogue.clarification_response()
        assert "yes or no" in msg.content.lower()
        assert msg.metadata["development_need_dialogue"]["status"] == "re_asking"


# ---------------------------------------------------------------------------
# Explicit development behavior
# ---------------------------------------------------------------------------


class TestExplicitDevelopmentExcluded:
    def test_explicit_development_request_not_rerouted_by_detector(self, detector):
        # Explicit dev requests already use the B3 path; the detector returns None.
        need = detector.detect(
            _explicit_dev_spec(),
            resolution=False,
            missing_capability="x",
        )
        assert need is None

    def test_explicit_development_request_ignores_resolution_signal(self, detector):
        need = detector.detect(_explicit_dev_spec(), resolution=False)
        assert need is None


def _explicit_dev_spec():
    from atlas.conversation.task_intake import TaskIntake
    return TaskIntake().intake(
        "add a new capability to Atlas for scheduling so that tasks run on time"
    )


# ---------------------------------------------------------------------------
# Advisory behavior
# ---------------------------------------------------------------------------


class TestAdvisoryBehavior:
    def test_advisory_opportunity_requires_confirmation(self, dialogue):
        need = _need(DevelopmentSignalKind.ADVISORY_OPPORTUNITY, reason="stale authz detected")
        # Detection alone must not become a request: explanation asks for confirmation.
        msg = dialogue.explain(need)
        assert "yes or no" in msg.content.lower()
        # Without explicit confirmation, no intent.
        assert dialogue.interpret_confirmation("maybe", need) == ConfirmationStatus.AMBIGUOUS

    def test_advisory_confirmed_produces_intent(self, dialogue):
        need = _need(
            DevelopmentSignalKind.ADVISORY_OPPORTUNITY,
            reason="stale authz detected",
            evidence=("authz:stale",),
            principal_id="owner",
            authority="owner",
        )
        assert dialogue.interpret_confirmation("yes", need) == ConfirmationStatus.CONFIRMED
        intent = dialogue.build_intent(need)
        assert intent.signal_kind == "advisory_opportunity"
        assert "authz:stale" in intent.evidence

    def test_advisory_never_auto_becomes_proposal(self, dialogue):
        """Advisory detection must not carry proposal/approval/execution state."""
        need = _need(DevelopmentSignalKind.ADVISORY_OPPORTUNITY, reason="x")
        intent = dialogue.build_intent(need)
        assert not hasattr(intent, "proposal_id")
        assert not hasattr(intent, "approval_id")
        assert not hasattr(intent, "status")


# ---------------------------------------------------------------------------
# Intent hand-off
# ---------------------------------------------------------------------------


class TestIntentHandoff:
    def test_build_intent_title_and_rationale(self, dialogue):
        need = _need(
            DevelopmentSignalKind.CAPABILITY_GAP,
            capability="quantum_stabilizer",
            reason="could not resolve",
        )
        intent = dialogue.build_intent(need)
        assert isinstance(intent, ExplicitDevelopmentIntent)
        assert "quantum_stabilizer" in intent.title
        assert "could not resolve" in intent.rationale
        assert intent.capability == "quantum_stabilizer"

    def test_intent_is_json_safe(self, dialogue):
        import json
        need = _need(DevelopmentSignalKind.CAPABILITY_GAP, capability="x", evidence=("e1", "e2"))
        json.dumps(dialogue.build_intent(need).to_dict())

    def test_confirmed_response_mentions_approval_process(self, dialogue):
        need = _need(DevelopmentSignalKind.CAPABILITY_GAP, capability="x")
        msg = dialogue.confirmed_response(need)
        assert "approval" in msg.content.lower()
        assert msg.metadata["development_need_dialogue"]["status"] == "confirmed"


# ---------------------------------------------------------------------------
# Determinism / no side effects / no duplicate requests
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_explain_is_deterministic(self, dialogue):
        need = _need(DevelopmentSignalKind.CAPABILITY_GAP, capability="x")
        assert dialogue.explain(need).content == dialogue.explain(need).content

    def test_interpret_is_deterministic(self, dialogue):
        need = _need(DevelopmentSignalKind.CAPABILITY_GAP, capability="x")
        a = dialogue.interpret_confirmation("yes", need)
        b = dialogue.interpret_confirmation("yes", need)
        assert a == b

    def test_repeated_invocation_no_duplicate_intents(self, dialogue):
        need = _need(DevelopmentSignalKind.CAPABILITY_GAP, capability="x")
        first = dialogue.build_intent(need)
        second = dialogue.build_intent(need)
        assert first == second  # equal (immutable), no accumulation


# ---------------------------------------------------------------------------
# F9 boundary + dependency direction
# ---------------------------------------------------------------------------


class TestF9Boundary:
    def test_dialogue_has_no_development_execution_surface(self, dialogue):
        for attr in (
            "approval_manager",
            "development_controller",
            "planner",
            "self_development_loop",
            "execution_gateway",
            "promotion_gate",
            "code_sandbox",
            "advisor",
            "scheduler",
            "tick",
        ):
            assert not hasattr(dialogue, attr), f"dialogue unexpectedly has {attr}"

    def test_dialogue_module_imports_no_forbidden_machinery(self):
        source = (
            _ROOT / "atlas" / "conversation" / "development_need_dialogue.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source, filename="development_need_dialogue.py")
        forbidden = (
            "atlas.evolution",
            "atlas.orchestration",
            "atlas.advisory",
            "atlas.kernel",
            "atlas.runtime",
            "atlas.storage",
        )
        for node in ast.walk(tree):
            module = getattr(node, "module", None)
            if module and any(
                module == p or module.startswith(p + ".") for p in forbidden
            ):
                raise AssertionError(f"dialogue imports forbidden module: {module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(
                        alias.name == p or alias.name.startswith(p + ".")
                        for p in forbidden
                    ):
                        raise AssertionError(
                            f"dialogue imports forbidden module: {alias.name}"
                        )

    def test_dialogue_only_depends_on_conversation(self):
        source = (
            _ROOT / "atlas" / "conversation" / "development_need_dialogue.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source, filename="development_need_dialogue.py")
        for node in ast.walk(tree):
            module = getattr(node, "module", None)
            if module and module.startswith("atlas"):
                assert module.startswith("atlas.conversation"), (
                    f"dialogue imports non-conversation module: {module}"
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("atlas"):
                        assert alias.name.startswith("atlas.conversation"), (
                            f"dialogue imports non-conversation module: {alias.name}"
                        )

    def test_dialogue_never_calls_f9(self):
        source = (
            _ROOT / "atlas" / "conversation" / "development_need_dialogue.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "run_development_cycle",
            "create_approval_request",
            "approve_proposal",
            "run_development_execution",
            "submit_development_for_promotion_review",
        ):
            assert forbidden not in source, f"dialogue must not call {forbidden}"
