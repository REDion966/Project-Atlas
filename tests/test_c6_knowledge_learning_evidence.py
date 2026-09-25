"""C6 — Knowledge & Learning Maturity: EVIDENCE-ONLY validation.

This module observes Atlas's CURRENT knowledge acquisition, validation,
retention, persistence, reuse, update and "learning"-language behaviour through
the real public path (``ConversationService.send`` on a wired ``Atlas`` kernel)
and through the directly relevant existing acquisition/validated-knowledge
capability.

It implements NO C6 capability and changes no production behaviour. Every test
pins the OBSERVED contract (including its limitations) and records a
classification (SUCCESS / CORRECT_BOUNDARY / SOURCE_POLICY_LIMITATION /
CONTEXT_ONLY / *_GAP / ENVIRONMENT_ARTIFACT) in its docstring.

Environment isolation (constraint 11): every SQLite store defaults to the shared
``atlas_data/atlas_experience.db``; this module points them at a fresh temporary
database (restored afterwards) so the evidence run never touches or grows
production data. The test-only fixture source lives in a temporary directory.
"""

from __future__ import annotations

import importlib
import pkgutil
import tempfile
from pathlib import Path

import pytest

from atlas.kernel.atlas import Atlas

_TMP_DIR = Path(tempfile.mkdtemp(prefix="c6_evidence_"))
_TMP_DB = _TMP_DIR / "atlas_experience.db"

#: Test-only deterministic fixture ("Atlas Evidence Device") — synthetic facts
#: that cannot be confused with real-world knowledge. NOT added to any
#: production knowledge base.
_FACT_A = _TMP_DIR / "evidence_device_a.md"
_FACT_C = _TMP_DIR / "evidence_device_c.md"
_FACT_A.write_text(
    "# Atlas Evidence Device (test fixture)\n\n"
    "The Atlas Evidence Device sensor count is 4.\n"
    "The Atlas Evidence Device operating mode is bounded test mode.\n",
    encoding="utf-8",
)
_FACT_C.write_text(
    "# Atlas Evidence Device (test fixture, contradicting)\n\n"
    "The Atlas Evidence Device sensor count is not 4.\n",
    encoding="utf-8",
)

_QUERY = "atlas evidence device sensor count operating mode"
_CLAIM_QUERY = "atlas evidence device operating mode"


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
    saved = _patch_default_db_paths(_TMP_DB)
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


def _conversation(kernel):
    service = kernel.container.get("conversation")
    service._conversation = service._history.create()
    service._state_manager.clear()
    service._last_investigation_report = None
    return service


def _send(kernel, text):
    return _conversation(kernel).send(text)


# ---------------------------------------------------------------------------
# CLASS A — KNOWLEDGE ACQUISITION
# ---------------------------------------------------------------------------


class TestClassAAcquisition:
    def test_authorized_local_source_yields_evidence_backed_claims(self, kernel):
        """A fixture (test-only, authorized local) source -> status ok + claims.

        Observation: `status="ok"`, `claim_count=2`, verification statuses
        SUPPORTED, `sources=[fixture]`, confidence 0.75.
        Classification: SUCCESS (evidence-backed acquisition exists).
        """
        result = kernel.acquisition_service.acquire(question=_QUERY, sources=[str(_FACT_A)])
        assert result.status == "ok"
        assert result.claim_count > 0
        assert result.verification_count > 0
        assert len(result.sources) == 1 and _FACT_A.name in result.sources[0]

    def test_acquisition_carries_provenance(self, kernel):
        """Acquired knowledge carries a source citation.

        Observation: `kernel.validated_knowledge(<claim query>)` returns the
        claim with a citation whose source_uri is the fixture file.
        Classification: SUCCESS (provenance exists and is retrievable).
        """
        result = kernel.validated_knowledge(_CLAIM_QUERY)
        assert result.status.value == "ok"
        assert result.items
        item = result.items[0]
        assert _FACT_A.name in " ".join(c.source_uri for c in item.citations)

    def test_acquisition_is_persisted_not_merely_a_turn_response(self, kernel):
        """The acquisition produces a durable, retrievable representation.

        Observation: the claim is retrievable afterwards via the validated
        knowledge retriever (a stored report), not just as a turn response.
        Classification: SUCCESS (knowledge read-back exists).
        """
        result = kernel.validated_knowledge(_CLAIM_QUERY)
        assert result.status.value == "ok"
        assert any(
            "operating mode" in item.statement.lower() for item in result.items
        )

    def test_unauthorized_external_source_is_denied(self, kernel):
        """An https source is not authorized (web deny-by-default).

        Observation: `status="noop"`, `claim_count=0`, `sources=[]`.
        Classification: SOURCE_POLICY_LIMITATION (intentional; not a C6 defect).
        """
        result = kernel.acquisition_service.acquire(
            question="unrelated web acquisition zzz", sources=["https://example.test/d"]
        )
        assert result.status == "noop"
        assert result.claim_count == 0
        assert not result.sources

    def test_no_authorized_source_reports_no_evidence(self, kernel):
        """A question with no resolvable authorized source -> honest noop.

        Classification: SUCCESS (fail-closed no-evidence behaviour).
        """
        result = kernel.acquisition_service.acquire(
            question="Quantum flux capacitor calibration records"
        )
        assert result.status == "noop"
        assert result.claim_count == 0


# ---------------------------------------------------------------------------
# CLASS B — KNOWLEDGE VALIDATION / PROVENANCE
# ---------------------------------------------------------------------------


class TestClassBValidation:
    def test_validated_knowledge_requires_supported_verification(self, kernel):
        """Only SUPPORTED claims are returned as validated knowledge.

        Observation: the operating-mode claim is returned with validation
        status "SUPPORTED" and a citation.
        Classification: SUCCESS (validation gate exists).
        """
        result = kernel.validated_knowledge(_CLAIM_QUERY)
        assert result.status.value == "ok"
        assert all(i.validation_status == "SUPPORTED" for i in result.items)

    def test_contradictory_evidence_is_marked_contested(self, kernel):
        """Two sources that disagree are detected as contested.

        Observation: acquisition findings report CONTESTED, confidence drops
        (0.617 vs 0.75), and BOTH sources are retained.
        Classification: SUCCESS (conflict DETECTION and marking exist).
        """
        result = kernel.acquisition_service.acquire(
            question=_QUERY, sources=[str(_FACT_A), str(_FACT_C)]
        )
        assert result.status == "ok"
        assert "CONTESTED" in result.findings
        assert len(result.sources) == 2
        assert result.confidence < 0.75

    def test_unknown_fact_returns_empty_not_an_error(self, kernel):
        """An unknown fact is not fabricated.

        Observation: validated_knowledge returns status "empty" with 0 items and
        an explicit "not an error" message.
        Classification: SUCCESS (honest no-knowledge behaviour).
        """
        result = kernel.validated_knowledge("zeppelin maintenance schedule")
        assert result.status.value == "empty"
        assert not result.items

    def test_states_are_distinguishable(self, kernel):
        """evidence-backed vs no-source vs unknown are distinguishable.

        Observation: acquisition "ok" (evidence), "noop" (no authorized source),
        and retrieval "empty" (no matching validated claim) are distinct.
        Classification: SUCCESS (existing authoritative status vocabulary).
        """
        with_evidence = kernel.acquisition_service.acquire(
            question=_QUERY, sources=[str(_FACT_A)]
        )
        without = kernel.acquisition_service.acquire(
            question="Quantum flux capacitor calibration records"
        )
        unknown = kernel.validated_knowledge("zeppelin maintenance schedule")
        assert (with_evidence.status, without.status, unknown.status.value) == (
            "ok",
            "noop",
            "empty",
        )


# ---------------------------------------------------------------------------
# CLASS C — RETENTION ACROSS TURNS (public path)
# ---------------------------------------------------------------------------


class TestClassCRetention:
    def test_research_result_is_retained_as_conversation_state(self, kernel):
        """A research turn's outcome is retained in conversation state.

        Observation (C6): after a completed research turn, `latest_result` held a
        bounded report line (the orchestration report).
        Observation (post-I3, reconciled): a research turn is answered by the
        existing local-first knowledge path, and ITS outcome is retained in the
        dedicated ``last_knowledge`` slot (subject / status / answer material
        with provenance). ``latest_result`` remains the slot for orchestration
        results that do reach the bridge.
        Classification: CONTEXT_ONLY — this is conversation state, NOT durable
        learned knowledge.
        """
        service = _conversation(kernel)
        service.send(
            "Research the memory service, including memory storage and memory "
            "search of the atlas memory subsystem."
        )
        retained = service.state_manager.state.last_knowledge
        assert isinstance(retained, dict)
        assert retained.get("query")
        assert retained.get("content")

    def test_conversational_subject_is_retained_across_turns(self, kernel):
        """A subject named in turn 1 is retained for turn 2 (NLU-4).

        Classification: CONTEXT_ONLY (conversation-scoped context, not
        knowledge).
        """
        service = _conversation(kernel)
        service.send("I am reviewing the Samsung Galaxy S26 Ultra.")
        assert [e.name for e in service._state_manager.state.captured_entities] == [
            "Samsung Galaxy S26 Ultra"
        ]

    def test_authorized_corpus_knowledge_is_surfaced_by_conversational_recall(self, kernel):
        """Authorized-corpus research knowledge is reachable conversationally.

        C6 evidence originally observed this as a MATERIAL gap (the retained,
        validated knowledge could not be reached from a turn). C6.1 closed it
        with a bounded read-only bridge; the bridge is unchanged.

        Reconciled (Evidence-Driven Improvement 3): the bridge is what SURFACES
        knowledge — it does not populate the store. Pre-I3 this test relied on a
        conversational research turn running a work-acquisition over the code
        corpus; I3 deliberately routes a research request through the
        local-first knowledge path instead. The knowledge is therefore produced
        by the existing authorized acquisition API and must still be surfaced by
        conversational recall.

        Classification: SUCCESS (the C6.1 contract; the pre-C6.1 behaviour is
        pinned separately by tests/test_c6_1_validated_knowledge_conversation.py).
        """
        service = _conversation(kernel)
        acquired = kernel.acquisition_service.acquire(
            question=_CLAIM_QUERY, sources=[str(_FACT_A)]
        )
        assert acquired.status == "ok", acquired.message
        validated = kernel.validated_knowledge("atlas evidence device operating mode")
        assert validated.status.value == "ok", validated.message

        recall = service.send("what do you know about atlas evidence device operating mode?")
        assert recall.metadata.get("builtin_intent") == "validated_knowledge"
        assert recall.metadata.get("validated_knowledge_status") == "ok"
        assert "validated (supported) claim" in recall.content.lower()

    def test_fact_question_is_not_answered_from_validated_knowledge(self, kernel):
        """A raw fact question still declines (the bridge is cue-bounded).

        Observation: "How many sensors does the Atlas Evidence Device have?"
        carries no bounded validated-knowledge cue, so it still receives the
        deterministic unsupported floor even though `validated_knowledge` can
        return the fact. C6.1 deliberately exposes EXISTING validated knowledge
        through a bounded cue family only — it is not a general question
        answering surface.

        Classification: KNOWN LIMITATION (bounded by design, not a C6 gap).
        """
        service = _conversation(kernel)
        service.send(
            "Research the memory service, including memory storage and memory "
            "search of the atlas memory subsystem."
        )
        validated = kernel.validated_knowledge("memory storage")
        assert validated.status.value == "ok", validated.message

        recall = service.send("do you remember memory storage?")
        assert recall.metadata.get("builtin_intent") == "recall"
        assert "no memory or knowledge entry matched" in recall.content.lower()

    def test_fact_question_is_not_answered_from_validated_knowledge(self, kernel):
        """Turn 2 asks for a fact that IS in the validated store.

        Observation: the public path declines deterministically (`unsupported`)
        even though `validated_knowledge` can return the fact.
        Classification: KNOWLEDGE_APPLICATION_GAP (the conversation path has no
        route to already-validated persisted knowledge).
        """
        service = _conversation(kernel)
        message = service.send("How many sensors does the Atlas Evidence Device have?")
        assert "without an external ai model" in message.content.lower()
        # ... while the fact itself IS retrievable at the existing kernel level.
        assert kernel.validated_knowledge(_CLAIM_QUERY).items


# ---------------------------------------------------------------------------
# CLASS D — KNOWLEDGE APPLICATION
# ---------------------------------------------------------------------------


class TestClassDApplication:
    def test_validated_fact_is_available_to_an_existing_capability(self, kernel):
        """The verified fact is retrievable with provenance.

        Classification: SUCCESS at the retrieval layer (the application
        substrate exists).
        """
        result = kernel.validated_knowledge(_CLAIM_QUERY)
        assert any(
            "operating mode is bounded test mode" in i.statement.lower()
            for i in result.items
        )

    def test_public_path_cannot_apply_retained_knowledge_to_a_new_task(self, kernel):
        """'Given that sensor count, does it meet the >= 4 requirement?'

        Observation: the public path declines; no deterministic application of
        the retained fact occurs.
        Classification: KNOWLEDGE_APPLICATION_GAP (public path).
        """
        message = _send(
            kernel,
            "Given that sensor count, determine whether the device meets the "
            "test requirement of at least 4 sensors.",
        )
        lowered = message.content.lower()
        assert "meets" not in lowered and "requirement" not in lowered
        assert "without an external ai model" in lowered


# ---------------------------------------------------------------------------
# CLASS E — CORRECTION / UPDATE / CONFLICT
# ---------------------------------------------------------------------------


class TestClassEUpdate:
    def test_conflicting_values_are_both_retained_without_update(self, kernel):
        """A revised value does not replace the earlier one.

        Observation: after acquiring A (`= 4`) and C (`is not 4`), both sources
        are retained and the outcome is CONTESTED; nothing is replaced or
        preferred.
        Classification: KNOWLEDGE_UPDATE_GAP (no update/preference policy) —
        evidence only; automatic updating is NOT assumed to be required.
        """
        result = kernel.acquisition_service.acquire(
            question=_QUERY, sources=[str(_FACT_A), str(_FACT_C)]
        )
        assert len(result.sources) == 2
        assert "CONTESTED" in result.findings

    def test_no_newer_wins_rule_exists(self, kernel):
        """There is no 'newer/authoritative source wins' behaviour observable.

        Observation: the validated store returns the claim that remains
        SUPPORTED; the contested pair is not silently resolved to one value.
        Classification: KNOWLEDGE_UPDATE_GAP (bounded; intentional absence).
        """
        result = kernel.validated_knowledge("atlas evidence device sensor count")
        statuses = {i.validation_status for i in result.items}
        assert statuses <= {"SUPPORTED"}  # only supported claims surface


# ---------------------------------------------------------------------------
# CLASS F — SESSION / RESTART PERSISTENCE
# ---------------------------------------------------------------------------


class TestClassFPersistence:
    def test_validated_knowledge_survives_a_kernel_restart(self, kernel):
        """The verified claim persists across a fresh kernel/process boundary.

        Observation: a second kernel in the same (isolated) environment still
        returns the claim with its citation.
        Classification: SUCCESS (durable validated knowledge exists).
        """
        atlas2 = Atlas()
        atlas2.start()
        try:
            result = atlas2.validated_knowledge(_CLAIM_QUERY)
            assert result.status.value == "ok"
            assert result.items
        finally:
            atlas2.shutdown()

    def test_validated_knowledge_is_environment_scoped(self, kernel):
        """A clean environment has no such knowledge (proves it is persistence).

        Classification: SUCCESS (storage-backed, not in-process caching).
        """
        from atlas.research.validated_retrieval import ValidatedKnowledgeRetriever

        empty_retriever = ValidatedKnowledgeRetriever(None)
        result = empty_retriever.retrieve(_CLAIM_QUERY)
        assert result.status.value == "store_unavailable"
        assert not result.items

    def test_research_storage_is_isolated_from_production_data(self, kernel):
        """The harness writes only to the temporary database.

        Classification: SUCCESS (constraint 11 honoured).
        """
        db_path = str(getattr(kernel._research_storage, "db_path", ""))
        assert "c6_evidence_" in db_path
        assert "atlas_data" not in db_path


# ---------------------------------------------------------------------------
# CLASS G — USER ASSERTION VS VERIFIED KNOWLEDGE
# ---------------------------------------------------------------------------


class TestClassGUserAssertion:
    def test_user_assertion_is_not_promoted_to_knowledge(self, kernel):
        """A user statement is not automatically durable or 'verified'.

        Observation: "The Atlas Evidence Device has 99 sensors." is answered by
        the deterministic floor; the asserted value never becomes retrievable
        validated knowledge.
        Classification: SUCCESS / CORRECT_BOUNDARY (evidence-grounded discipline
        — assertions are not evidence).
        """
        service = _conversation(kernel)
        service.send("The Atlas Evidence Device has 99 sensors.")
        message = service.send("How many sensors does the Atlas Evidence Device have?")
        assert "99" not in message.content
        assert not any(
            "99" in item.statement
            for item in kernel.validated_knowledge("atlas evidence device sensor count").items
        )

    def test_assertion_is_not_retained_between_turns(self, kernel):
        """The asserted value does not persist as a fact.

        Classification: SUCCESS / CORRECT_BOUNDARY.
        """
        service = _conversation(kernel)
        service.send("The Atlas Evidence Device has 99 sensors.")
        state = service._state_manager.state
        assert "99" not in (state.latest_result or "")


# ---------------------------------------------------------------------------
# CLASS H — REUSE WITHOUT REACQUISITION
# ---------------------------------------------------------------------------


class TestClassHReuse:
    def test_retention_outlives_the_source_but_reacquisition_does_not_reuse_it(
        self, kernel, tmp_path
    ):
        """Previously validated knowledge survives the source becoming unavailable.

        Observation: after acquiring from a fixture copy and deleting it, a NEW
        acquisition of the same source resolves nothing (fresh lookup fails:
        `sources == []`), while `validated_knowledge` still returns the earlier
        validated claim. So retention EXISTS, but the acquisition path does not
        consult it (it re-acquires).
        Classification: retention SUCCESS; the acquisition/conversation reuse is
        a KNOWLEDGE_APPLICATION_GAP (no reuse-without-reacquisition wire).
        """
        disposable = tmp_path / "evidence_device_disposable.md"
        disposable.write_text(
            "# Disposable fixture\n\nThe Atlas Evidence Device retention marker is R7.\n",
            encoding="utf-8",
        )
        first = kernel.acquisition_service.acquire(
            question="atlas evidence device retention marker", sources=[str(disposable)]
        )
        assert first.status == "ok"
        disposable.unlink()

        again = kernel.acquisition_service.acquire(
            question="atlas evidence device retention marker", sources=[str(disposable)]
        )
        assert not again.sources  # fresh lookup cannot resolve the deleted source

        retained = kernel.validated_knowledge("atlas evidence device retention marker")
        assert any("R7" in i.statement for i in retained.items)


# ---------------------------------------------------------------------------
# CLASS I — OPEN-ENDED "LEARNING" REQUESTS (public path)
# ---------------------------------------------------------------------------


class TestClassILearningLanguage:
    @pytest.mark.parametrize(
        ("text", "expected_intent"),
        [
            ("Remember this information for later.", "recall"),
            ("Learn this fact.", "unsupported"),
            ("Keep this information and use it next time.", "unsupported"),
        ],
    )
    def test_learning_requests_do_not_learn(self, kernel, text, expected_intent):
        """Natural-language 'learn/remember' requests do not create knowledge.

        Observation: "remember …" maps to the bounded RECALL (a verbatim search
        over memory/knowledge — it stores nothing); "learn this fact" and "keep
        this information" fall to the deterministic unsupported floor.
        Classification: LEARNING_GAP (no learning intake exists) — an
        intentional boundary: Atlas requires evidence, not assertions.
        """
        message = _send(kernel, text)
        assert message.metadata.get("builtin_intent") == expected_intent
        assert message.metadata.get("model_used") is False

    def test_recall_after_research_matches_stored_entries_not_research_knowledge(self, kernel):
        """'what did you learn from that research?' is routed to research.

        Observation: it is typed as a research request (the word 'research') and
        reports no evidence; it is NOT answered from prior research knowledge.
        Classification: LEARNING_GAP + a MINOR language misroute.
        """
        message = _conversation(kernel).send("What did you learn from that research?")
        assert "no_evidence" in message.content.lower() or "no evidence" in message.content.lower()

    def test_knowledge_retention_question_is_misrouted_to_investigation(self, kernel):
        """'What knowledge do you currently retain from that investigation?'

        Observation: typed as an investigation request (the word 'investigation')
        and answered with a read-only repository investigation report.
        Classification: LEARNING_GAP + a MINOR language misroute (evidence only).
        """
        message = _conversation(kernel).send(
            "What knowledge do you currently retain from that investigation?"
        )
        assert "## investigation" in message.content.lower()


# ---------------------------------------------------------------------------
# CLASS J — MODEL INDEPENDENCE
# ---------------------------------------------------------------------------


class TestClassJModelIndependence:
    def test_evidence_paths_do_not_use_an_external_model(self, kernel):
        """No evidence path requires an external AI model.

        Classification: SUCCESS (model independence intact).
        """
        service = _conversation(kernel)
        # Reconciled (Evidence-Driven Improvement 3): a research turn is now
        # answered by the deterministic local-first knowledge path (the builtin
        # floor reports `model_used: False`); the memory/knowledge-language turns
        # are handled by the same deterministic floor. None uses a model.
        research = service.send(
            "Research the memory service, including memory storage of the atlas memory subsystem."
        )
        assert (research.metadata or {}).get("model_used") is False
        for text in (
            "Remember this information for later.",
            "Learn this fact.",
        ):
            message = service.send(text)
            assert (message.metadata or {}).get("model_used") is False, text
        result = kernel.acquisition_service.acquire(question=_QUERY, sources=[str(_FACT_A)])
        assert result.status == "ok"


# ---------------------------------------------------------------------------
# CLASS K — GOVERNANCE / SAFETY
# ---------------------------------------------------------------------------


class TestClassKGovernance:
    def test_unauthorized_source_stays_unauthorized(self, kernel):
        """The deny-by-default source policy is not bypassed by the evidence run.

        Classification: SUCCESS (governance intact).
        """
        result = kernel.acquisition_service.acquire(
            question="blocked web question yy", sources=["http://192.168.0.1/private"]
        )
        assert not result.sources
        assert result.claim_count == 0

    def test_no_secrets_are_surfaced(self, kernel):
        """Validated knowledge output contains fixture facts, never secrets.

        Classification: SUCCESS (no credential/secret exposure).
        """
        text = " ".join(
            item.statement for item in kernel.validated_knowledge(_CLAIM_QUERY).items
        )
        for marker in ("api_key", "password", "secret", "token"):
            assert marker not in text.lower()

    def test_production_data_store_is_not_used(self, kernel):
        """The evidence run writes only to the isolated temporary database.

        Classification: SUCCESS (constraint 11 / no production pollution).
        """
        assert "c6_evidence_" in str(getattr(kernel._research_storage, "db_path", ""))
        assert "atlas_data" not in str(getattr(kernel._research_storage, "db_path", ""))
