"""C3 — Real-World Capability Evidence (evidence-collection module).

This module is the *evidence* for the C3 milestone. It exercises the REAL public
conversation path (``ConversationService.send`` on a fully wired ``Atlas``
kernel) with realistic user language across eight capability classes, and pins
the OBSERVED behaviour so the current real capability boundary is documented and
reproducible.

It deliberately asserts the CURRENT contract — including its limitations — and
classifies each observation in its docstring (A–J taxonomy from the C3 task):
    A SUCCESS            B CORRECT CLARIFICATION     C GOVERNANCE-EXPECTED
    D KNOWLEDGE/SOURCE   E LANGUAGE-UNDERSTANDING    F CONTEXT/STATE
    G PLANNING/REASONING H EXECUTION/INTEGRATION     I SELF-KNOWLEDGE
    J TEST/ENVIRONMENT

Nothing in this module changes Atlas behaviour: it does not add NLU rules,
entity/reference rules, matching, models, web access, or governance changes.

Environment note (classification J): every SQLite store defaults to ONE shared
file (``atlas_data/atlas_experience.db``) which has grown to ~320 MB across
repeated runs; using it made each delegated turn take ~2 minutes and the kernel
boot ~2 minutes. This module points every store at a fresh temporary database
for the duration of the module (restored afterwards), so the evidence reflects a
clean install and the module stays runnable. This changes only where the test's
data lives, never production behaviour.
"""

from __future__ import annotations

import importlib
import pkgutil
import tempfile
from pathlib import Path

import pytest

from atlas.kernel.atlas import Atlas


# ---------------------------------------------------------------------------
# Environment isolation (test harness only; restored after the module)
# ---------------------------------------------------------------------------


def _patch_default_db_paths(new_path: Path) -> list[tuple[type, object]]:
    import atlas.storage as storage_pkg

    saved: list[tuple[type, object]] = []
    for info in pkgutil.iter_modules(storage_pkg.__path__):
        try:
            module = importlib.import_module(f"atlas.storage.{info.name}")
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and hasattr(obj, "DEFAULT_DB_PATH"):
                saved.append((obj, obj.DEFAULT_DB_PATH))
                setattr(obj, "DEFAULT_DB_PATH", new_path)
    return saved


@pytest.fixture(scope="module")
def kernel():
    """A single wired Atlas kernel for the module, backed by a fresh DB."""
    saved = _patch_default_db_paths(
        Path(tempfile.mkdtemp(prefix="c3_evidence_")) / "atlas_experience.db"
    )
    atlas = Atlas()
    atlas.start()
    try:
        yield atlas
    finally:
        try:
            atlas.shutdown()
        except Exception:  # noqa: BLE001
            pass
        for cls, original in saved:
            setattr(cls, "DEFAULT_DB_PATH", original)


def _conversation(kernel) -> object:
    """A fresh public conversation on the kernel-wired service.

    Mirrors what a new user conversation is: a new Conversation plus cleared
    ConversationState. (Atlas exposes no public "new conversation" method, so
    the harness resets the same public service rather than duplicating wiring.)
    """
    service = kernel.container.get("conversation")
    service._conversation = service._history.create()
    service._state_manager.clear()
    service._last_investigation_report = None
    return service


def _state(service):
    return service._state_manager.state


# ---------------------------------------------------------------------------
# CLASS A — INFORMATION / RESEARCH REQUESTS
# ---------------------------------------------------------------------------


class TestClassAInformationResearch:
    def test_named_subject_is_understood_and_routed_but_has_no_authorized_source(self, kernel):
        """'Research the camera system of the Samsung Galaxy S26 Ultra.'

        Observed (pre-I3): information_request -> research step -> acquisition
        noop -> honest 'Could not complete ... no_evidence'.
        Observed (post-I3, reconciled): information_request -> existing
        local-first knowledge path (validated knowledge, then the D3 knowledge
        decision that owns the governed D2 boundary) -> honest
        'No validated knowledge matched ... (status: empty)'.
        Classification: D (KNOWLEDGE/SOURCE) — the request is understood and
        answered by the authoritative knowledge path; there is simply no
        authorized source for consumer product facts (web stays
        deny-by-default). Never a fabricated answer and never a 'done' claim.
        """
        message = _conversation(kernel).send(
            "Research the camera system of the Samsung Galaxy S26 Ultra."
        )
        text = message.content.lower()
        assert message.metadata.get("builtin_intent") == "validated_knowledge"
        assert message.metadata.get("validated_knowledge_status") == "empty"
        assert "no validated knowledge matched" in text
        assert "done" not in text
        assert not isinstance(message.metadata.get("orchestration"), dict)

    def test_comparison_request_is_routed_to_the_answerable_path(self, kernel):
        """'Compare the Samsung Galaxy S26 Ultra and iPhone 17 Pro cameras.'

        Observed: conversation/request -> reasoned the turn is answerable
        (reasoning_eligibility present) -> deterministic floor decline.
        Classification: C (GOVERNANCE-EXPECTED) — the model is optional and OFF
        in the shipped default, so no external answer is produced. This is the
        deliberate model-independent/deterministic-first boundary, not a bug.
        """
        message = _conversation(kernel).send(
            "Compare the Samsung Galaxy S26 Ultra and iPhone 17 Pro cameras."
        )
        assert "without an external ai model" in message.content.lower()
        assert message.metadata.get("reasoning_eligibility", {}).get("eligible") is True
        assert message.metadata.get("model_used") is False

    def test_generic_domain_research_declines_honestly(self, kernel):
        """'Research the latest information about smartphone camera sensors.'

        Observed (pre-I3): information_request -> research acquired local
        sources that do not address the subject -> honest
        'no_relevant_evidence' (NLU-2 relevance gate).
        Observed (post-I3, reconciled): the request now enters the existing
        local-first knowledge path, which declines honestly with
        'No validated knowledge matched ... (status: empty)' — the same
        NLU-2 outcome (no authorized, relevant evidence) reported by the
        authoritative knowledge path. Classification: D (KNOWLEDGE/SOURCE).
        """
        message = _conversation(kernel).send(
            "Research the latest information about smartphone camera sensors."
        )
        text = message.content.lower()
        assert "no validated knowledge matched" in text
        assert "done" not in text


# ---------------------------------------------------------------------------
# CLASS B — MULTI-TURN CONVERSATION
# ---------------------------------------------------------------------------


class TestClassBMultiTurn:
    def test_subject_and_references_are_preserved_across_turns(self, kernel):
        """Turn1 subject -> 'its' -> 'that'/explicit iPhone across 4 turns.

        Observed: the subject entity is captured and each bounded reference
        resolves to exactly one antecedent; the ANSWER for each casual /
        comparative turn is the deterministic decline (model off).
        Classification: A (SUCCESS) for interpretation/context/reference
        preservation; C for the answer boundary.
        """
        service = _conversation(kernel)
        service.send("I'm reviewing the Samsung Galaxy S26 Ultra.")
        assert [e.name for e in _state(service).captured_entities] == [
            "Samsung Galaxy S26 Ultra"
        ]

        service.send("What about its camera?")
        assert [e.name for e in _state(service).captured_entities] == [
            "Samsung Galaxy S26 Ultra"
        ]

        service.send("Compare that with the iPhone 17 Pro.")
        names = [e.name for e in _state(service).captured_entities]
        assert "Samsung Galaxy S26 Ultra" in names
        assert "iPhone 17 Pro" in names

        message = service.send("Which camera features matter most for video?")
        assert "without an external ai model" in message.content.lower()

    def test_reference_resolution_is_observable_through_the_public_turn(self, kernel):
        """'What about its camera?' resolves 'its' to the captured subject."""
        from atlas.orchestration.target_resolution import task_spec_to_execution_steps

        service = _conversation(kernel)
        service.send("I'm reviewing the Samsung Galaxy S26 Ultra.")
        spec = service._intake("What about its camera?", 2)
        spec, response = service._apply_reference_resolution(spec, "What about its camera?")
        assert response is None
        assert spec.context.get("resolved_reference") == {
            "field": "captured_entity",
            "value": "Samsung Galaxy S26 Ultra",
        }
        # A research-shaped follow-up carries the resolved subject.
        rq_spec = service._intake("Research its camera system.", 2)
        rq_spec, _ = service._apply_reference_resolution(rq_spec, "Research its camera system.")
        steps = task_spec_to_execution_steps(rq_spec)
        assert steps[0].inputs["question"].startswith("Samsung Galaxy S26 Ultra: ")


# ---------------------------------------------------------------------------
# CLASS C — CONTEXTUAL FOLLOW-UPS
# ---------------------------------------------------------------------------


class TestClassCContextualFollowups:
    def test_possessive_followup_resolves(self, kernel):
        """'What about its battery?' -> resolves to the active subject.

        Classification: A (SUCCESS) at the reference/context layer.
        """
        service = _conversation(kernel)
        service.send("I am reviewing the Samsung Galaxy S26 Ultra.")
        spec = service._intake("What about its battery?", 2)
        spec, _ = service._apply_reference_resolution(spec, "What about its battery?")
        assert spec.context.get("resolved_reference", {}).get("value") == (
            "Samsung Galaxy S26 Ultra"
        )

    def test_elliptical_topic_continuation_is_not_linked(self, kernel):
        """'And the display?' after a subject turn is NOT linked to the subject.

        Observed: no reference token -> unresolved -> deterministic floor.
        Classification: F (CONTEXT/STATE) — an elliptical topic continuation
        (no pronoun/determiner) is not attached to the active subject. Recorded
        limitation (MINOR): the per-turn objective is unaffected, and the answer
        is model-dependent anyway.
        """
        service = _conversation(kernel)
        service.send("I am reviewing the Samsung Galaxy S26 Ultra.")
        spec = service._intake("And the display?", 2)
        spec, _ = service._apply_reference_resolution(spec, "And the display?")
        assert "resolved_reference" not in spec.context
        message = service.send("And the display?")
        assert "without an external ai model" in message.content.lower()

    def test_domain_capabilities_question_is_not_atlas_inventory(self, kernel):
        """'What about the video recording capabilities?' -> NOT Atlas's OWN
        capability inventory.

        C3 originally observed `builtin_intent = capabilities` here (the
        self-inventory matcher fired on a domain question). C5.1 fixed that
        bounded collision: the domain question now declines deterministically
        instead of misdirecting the user to Atlas's own inventory.
        Classification (original): E (LANGUAGE-UNDERSTANDING), MINOR; now
        resolved for this evidenced case.
        """
        service = _conversation(kernel)
        service.send("I am reviewing the Samsung Galaxy S26 Ultra.")
        message = service.send("What about the video recording capabilities?")
        assert message.metadata.get("builtin_intent") != "capabilities"
        assert "confirmed registered capabilities" not in message.content.lower()

    def test_focus_instruction_has_no_objective_transition(self, kernel):
        """'Now focus only on the camera.' -> no objective refinement.

        Observed: statement -> deterministic floor; nothing narrows the active
        objective. Classification: F (CONTEXT/STATE) — there is no
        objective-refinement transition. Recorded (MINOR).
        """
        service = _conversation(kernel)
        service.send("I am reviewing the Samsung Galaxy S26 Ultra.")
        message = service.send("Now focus only on the camera.")
        assert "without an external ai model" in message.content.lower()

    def test_research_followup_carries_the_resolved_subject(self, kernel):
        """'Can you research that part?' -> objective carries the subject.

        Observed: information_request; reference resolves; the research question
        becomes 'Samsung Galaxy S26 Ultra: research that part?'; acquisition
        returns no authorized evidence (D).
        """
        from atlas.orchestration.target_resolution import task_spec_to_execution_steps

        service = _conversation(kernel)
        service.send("I am reviewing the Samsung Galaxy S26 Ultra.")
        spec = service._intake("Can you research that part?", 2)
        spec, _ = service._apply_reference_resolution(spec, "Can you research that part?")
        steps = task_spec_to_execution_steps(spec)
        assert steps is not None
        assert steps[0].inputs["question"].startswith("Samsung Galaxy S26 Ultra: ")
        message = service.send("Can you research that part?")
        assert "no_evidence" in message.content.lower()


# ---------------------------------------------------------------------------
# CLASS D — CORRECTION / REVISION
# ---------------------------------------------------------------------------


class TestClassDCorrection:
    def test_correction_utterance_response_stays_bounded(self, kernel):
        """'Actually, I meant the S26 Ultra's video recording.'

        Observed (C3, pre-I2/I3): conversation/statement -> deterministic floor;
        the prior research objective was NOT revised.
        Observed (post-I2): the correction IS applied — conversation state
        records it and installs the corrected subject as ``current_objective``
        (see tests/test_evidence_improvement_2.py for the full contract).
        Observed (post-I3, reconciled): the correction utterance itself is still
        the bounded deterministic reply, and the preceding research turn is now
        answered honestly by the knowledge path (no authorized source for
        consumer product facts). This test now asserts only what it can
        deterministically pin: both turns return bounded, honest, model-free
        responses and never a fabricated result.
        """
        service = _conversation(kernel)
        first = service.send("Research the Galaxy S26 Ultra camera.")
        assert first.metadata.get("builtin_intent") == "validated_knowledge"
        assert "no validated knowledge matched" in first.content.lower()
        assert "done" not in first.content.lower()
        corrected = service.send("Actually, I meant the S26 Ultra's video recording.")
        assert "without an external ai model" in corrected.content.lower()
        assert corrected.metadata.get("builtin_intent") in {"unsupported", "conversation"}

    def test_correction_capture_is_imperfect(self, kernel):
        """Observed: the possessive fragment 'S26 Ultra's' is captured as an
        entity name. Classification: E (bounded capture imprecision), MINOR —
        it does not change routing but pollutes the captured-entity set."""
        service = _conversation(kernel)
        service.send("Research the Galaxy S26 Ultra camera.")
        service.send("Actually, I meant the S26 Ultra's video recording.")
        names = [e.name for e in _state(service).captured_entities]
        assert "Galaxy S26 Ultra" in names
        assert "S26 Ultra's" in names  # recorded capture imprecision


# ---------------------------------------------------------------------------
# CLASS E — AMBIGUITY
# ---------------------------------------------------------------------------


class TestClassEAmbiguity:
    def test_fresh_dangling_reference_declines_without_guessing(self, kernel):
        """'Compare the two phones.' / 'What about the other one?' / 'Look into
        that product.' in a FRESH conversation.

        Observed: no captured entity -> nothing is invented -> deterministic
        floor (no fabricated antecedent).
        Classification: B/C — fail-closed (no guess). Recorded (MINOR): these
        dangling forms produce a generic decline rather than a targeted
        clarification. (NLU-2's possessive/indefinite/demonstrative gap rules do
        clarify other forms, e.g. 'Research this product for me.'.)
        """
        for text in (
            "Compare the two phones.",
            "What about the other one?",
            "Look into that product.",
        ):
            service = _conversation(kernel)
            message = service.send(text)
            lowered = message.content.lower()
            assert "samsung" not in lowered and "iphone" not in lowered, text

    def test_ambiguous_research_keeps_the_governed_clarification(self, kernel):
        """'Find out what module handles this capability.' (fresh)

        Observed: information_request + ambiguous reference -> bounded
        clarification 'What does the ambiguous reference refer to?'.
        Classification: B (CORRECT CLARIFICATION).
        """
        message = _conversation(kernel).send(
            "Find out what module handles this capability."
        )
        assert "ambiguous reference" in message.content.lower()


# ---------------------------------------------------------------------------
# CLASS F — OPEN-ENDED NATURAL LANGUAGE
# ---------------------------------------------------------------------------


class TestClassFOpenEnded:
    def test_open_ended_product_question_declines_deterministically(self, kernel):
        """'I'm trying to figure out whether this phone is actually good for
        shooting video.'

        Classification: C/D — the sentence is understood as casual conversation
        and routed to the answerable path, which declines without the optional
        model.
        """
        message = _conversation(kernel).send(
            "I'm trying to figure out whether this phone is actually good for shooting video."
        )
        assert "without an external ai model" in message.content.lower()

    def test_capable_phrasing_is_not_misrouted_to_the_self_inventory(self, kernel):
        """'Can you look into what its cameras are capable of?'

        C3 originally observed the self-inventory matcher firing on 'capable'
        (domain question). C5.1 fixed that bounded collision.
        Classification (original): E (LANGUAGE-UNDERSTANDING), MINOR; now
        resolved for this evidenced case.
        """
        message = _conversation(kernel).send(
            "Can you look into what its cameras are capable of?"
        )
        assert message.metadata.get("builtin_intent") != "capabilities"
        assert "confirmed registered capabilities" not in message.content.lower()

    def test_natural_research_phrasing_clarifies_and_captures_noise(self, kernel):
        """'Before I decide what to test, find the important camera differences.'

        Observed: information_request; the fail-closed clarification is
        requested; the bounded capture also recorded 'Before I' as an entity.
        Classification: B (CORRECT CLARIFICATION) + E (MINOR capture imprecision).
        """
        service = _conversation(kernel)
        message = service.send(
            "Before I decide what to test, find the important camera differences."
        )
        assert "need a bit more detail" in message.content.lower()
        names = [e.name for e in _state(service).captured_entities]
        assert "Before I" in names  # recorded capture imprecision


# ---------------------------------------------------------------------------
# CLASS G — SELF-KNOWLEDGE
# ---------------------------------------------------------------------------


class TestClassGSelfKnowledge:
    def test_capability_inventory_is_available(self, kernel):
        """'What can you currently do?' -> the deterministic registered
        capability inventory. Classification: A (SUCCESS)."""
        message = _conversation(kernel).send("What can you currently do?")
        assert "confirmed registered capabilities" in message.content.lower()

    @pytest.mark.parametrize(
        "question",
        [
            "What parts of your system handle conversation?",
            "How do you resolve references?",
            "What happens when you don't have enough evidence?",
            "What are your current limitations?",
        ],
    )
    def test_self_knowledge_questions_are_now_answered(self, kernel, question):
        """Self-knowledge questions about Atlas's own modules, reference
        resolution, evidence policy, and limitations.

        C3 recorded these as unanswerable (deterministic floor / research
        misroute) — classification I (SELF-KNOWLEDGE LIMITATION), the MATERIAL
        gap that justified C5.1. C5.1 now answers them from verified internal
        knowledge, so this evidence case asserts the NEW authoritative contract.
        """
        message = _conversation(kernel).send(question)
        assert message.metadata.get("builtin_intent") in {"architecture", "self_knowledge"}
        text = message.content.lower()
        assert "self-knowledge" in text
        assert "no external ai model used" in text
        assert message.metadata.get("model_used") is False

    def test_self_referential_research_question_is_now_answered(self, kernel):
        """'Can you explain how your research process works?'

        C3 recorded this as misrouted into research -> no_relevant_evidence
        (classification I + E). C5.1's self-knowledge precedence now answers it
        from the verified research architecture instead.
        """
        message = _conversation(kernel).send(
            "Can you explain how your research process works?"
        )
        assert message.metadata.get("builtin_intent") == "self_knowledge"
        assert "research process" in message.content.lower()
        assert "concreteresearchcoordinator" in message.content.lower()


# ---------------------------------------------------------------------------
# CLASS H — CAPABILITY-BUILDING REQUESTS
# ---------------------------------------------------------------------------


class TestClassHCapabilityBuilding:
    def test_self_investigation_reaches_a_real_read_only_investigation(self, kernel):
        """'I need you to investigate how your own research system works.'

        Observed: investigation_request -> read-only investigation report naming
        the relevant components, plus a (non-executed) proposal.
        Classification: A (SUCCESS) — Atlas can investigate its own architecture
        deterministically and read-only.
        """
        message = _conversation(kernel).send(
            "I need you to investigate how your own research system works."
        )
        assert "## investigation" in message.content.lower()
        assert isinstance(message.metadata.get("investigation"), dict)

    def test_architecture_question_reaches_a_read_only_investigation(self, kernel):
        """'Analyze your current architecture and tell me where this behavior
        belongs.' Classification: A (SUCCESS)."""
        message = _conversation(kernel).send(
            "Analyze your current architecture and tell me where this behavior belongs."
        )
        assert "## investigation" in message.content.lower()

    def test_change_request_enters_the_governed_development_path(self, kernel):
        """'What would need to change to add this capability?'

        Observed: development_request + needs-clarification -> governed
        development clarification (no autonomous change).
        Classification: B (CORRECT CLARIFICATION) — the capability-build request
        is handled by the governed development pathway and fails closed.
        """
        message = _conversation(kernel).send(
            "What would need to change to add this capability?"
        )
        lowered = message.content.lower()
        assert "governed development request" in lowered
        assert "## investigation" not in lowered
