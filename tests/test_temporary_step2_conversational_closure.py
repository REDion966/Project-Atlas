"""Temporary Roadmap Step 2 — conversational interface closure.

Pins the Step-2 language-understanding / routing changes that make natural
variations of the same intent reach the correct EXISTING Atlas surface, and
guards the Step-1 exposure policy, the governed routes and the stream/non-stream
parity:

* an EXPLICIT validated-knowledge request about a named subject belongs to the
  knowledge surface, not to a self-knowledge topic page;
* a subject-scoped staleness/currency question is answered from the EXISTING
  temporal seam ONLY when Atlas actually retains knowledge about that subject;
* bounded STRUCTURE/COMPOSITION architecture forms resolve a component or
  subsystem from the EXISTING architecture model (and decline otherwise);
* the bounded multi-word investigation idioms ("look into X", "dig into X",
  "check out X") classify as investigation requests, and a classified
  investigation keeps its read-only route;
* the unsupported floor states the real reason (a bounded surface set) instead of
  implying that an external model would answer.

Nothing here grants authority, acquires anything, or consults a model.
"""

from __future__ import annotations

import pkgutil
import socket
from pathlib import Path

import pytest

import atlas.storage as storage_pkg
from atlas.conversation.builtin_response import (
    BUILTIN_INTENT_ARCHITECTURE,
    BUILTIN_INTENT_KNOWLEDGE_STATE,
    BUILTIN_INTENT_SELF_KNOWLEDGE,
    BUILTIN_INTENT_SOURCE_AUTHORIZATION,
    BUILTIN_INTENT_UNSUPPORTED,
    EXPOSURE_PRECEDENCE,
    BuiltinResponseService,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAIMS = (
    (
        "tel",
        "The telemetry_index keeps deployment telemetry metrics for each "
        "environment.",
    ),
    (
        "inv",
        "The invoice_ledger records every customer invoice line for each "
        "billing period.",
    ),
)


# ---------------------------------------------------------------------------
# Step 2.1 — the knowledge surface owns explicit knowledge requests (pure)
# ---------------------------------------------------------------------------


class _TemporalEntry:
    def __init__(self, claim_id, status, *, age_days=None, standing="supported"):
        self.claim_id = claim_id
        self.status = status
        self.age_days = age_days
        self.standing = standing


class _Temporal:
    def __init__(self, status, *, entries=(), message=""):
        self.status = status
        self.entries = tuple(entries)
        self.message = message


def _service(*, temporal=None):
    def _provider(query):
        # Faithful to the real seam: the verdict exists only for a subject the
        # store can resolve, so an unrelated subject yields nothing.
        if temporal is None:
            return None
        if getattr(temporal, "entries", None):
            if not any(token in query for token in ("telemetry", "invoice", "ledger")):
                return _Temporal("empty", message="No validated claim matched.")
        return temporal

    return BuiltinResponseService(knowledge_state_provider=_provider)


class TestSubjectScopedKnowledgeState:
    def _known(self):
        return _service(
            temporal=_Temporal(
                "ok",
                entries=(_TemporalEntry("tel", "current_relative", age_days=1.0),),
            )
        )

    @pytest.mark.parametrize(
        "text",
        [
            "Has the telemetry_index gone stale?",
            "Is the telemetry_index still accurate?",
            "Has the telemetry_index become outdated?",
            "Is the telemetry_index still up to date?",
            "Is the invoice_ledger still valid?",
        ],
    )
    def test_subject_scoped_forms_reach_the_state_surface(self, text):
        message = self._known().match_knowledge_state_question(text)
        assert message is not None
        assert message.metadata["builtin_intent"] == BUILTIN_INTENT_KNOWLEDGE_STATE
        assert message.metadata["model_used"] is False

    def test_answer_is_scoped_to_atlas_retained_knowledge(self):
        message = self._known().match_knowledge_state_question(
            "Has the telemetry_index gone stale?"
        )
        assert "the validated knowledge Atlas" in message.content
        assert "not a claim about the subject itself" in message.content

    @pytest.mark.parametrize(
        "text",
        [
            "Has the Zorblax protocol gone stale?",
            "Is the Glorptronic pipeline still accurate?",
        ],
    )
    def test_unknown_subject_keeps_its_existing_route(self, text):
        # no retained knowledge about the subject -> not claimed (fail closed)
        service = _service(temporal=_Temporal("empty"))
        assert service.match_knowledge_state_question(text) is None

    def test_no_retained_knowledge_is_never_claimed_as_a_world_claim(self):
        service = _service(temporal=_Temporal("empty"))
        assert (
            service.match_knowledge_state_question("Has anything gone stale?") is None
        )

    @pytest.mark.parametrize(
        "text",
        [
            "Is the deployment pipeline healthy?",
            "Is the sandbox still available?",
            "Is the research capability still current?",
            "Get me the latest information about the telemetry_index.",
        ],
    )
    def test_other_turns_are_not_claimed(self, text):
        assert self._known().match_knowledge_state_question(text) is None


# ---------------------------------------------------------------------------
# Step 2.2 — the unsupported floor states the real reason (pure)
# ---------------------------------------------------------------------------


class TestUnsupportedHonesty:
    def test_refusal_states_the_bounded_surface_reason(self):
        message = _service().respond("Handle that.", spec=None)
        assert message is not None
        assert message.metadata["builtin_intent"] == BUILTIN_INTENT_UNSUPPORTED
        assert "outside the bounded set" in message.content
        assert "no model is my intelligence or my authority" in message.content
        assert message.metadata["model_used"] is False


# ---------------------------------------------------------------------------
# Real Atlas/kernel
# ---------------------------------------------------------------------------


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
        _seed(atlas)
        yield atlas
    finally:
        atlas.shutdown()


def _seed(atlas):
    from atlas.research.models import (
        CitationRecord,
        ClaimVerification,
        KnowledgeClaim,
        SourceKind,
        VerificationStatus,
    )

    for cid, statement in CLAIMS:
        uri = f"https://example.org/{cid}"
        atlas._research_storage.store_claim(
            KnowledgeClaim(
                claim_id=cid,
                statement=statement,
                citations=(
                    CitationRecord(
                        record_id=f"cite:{cid}:0000",
                        source_uri=uri,
                        source_title=cid,
                        source_kind=SourceKind.WEB,
                        section="chunk:0000",
                    ),
                ),
                confidence=0.8,
            )
        )
        atlas._research_storage.store_verification(
            ClaimVerification(
                verification_id=f"verify:{cid}",
                claim_id=cid,
                status=VerificationStatus.SUPPORTED,
                score=0.75,
                metadata={
                    "outcome": "PLAUSIBLE",
                    "supporting": [uri],
                    "contradicting": [],
                },
            )
        )


def _intent(message):
    return (getattr(message, "metadata", {}) or {}).get("builtin_intent")


class TestKnowledgeOwnership:
    @pytest.mark.parametrize(
        "text",
        [
            "What validated facts do you have about the telemetry_index?",
            "What verified information do you have about the telemetry_index?",
            "What confirmed knowledge do you hold about the invoice_ledger?",
        ],
    )
    def test_explicit_knowledge_requests_reach_the_knowledge_surface(
        self, kernel, text
    ):
        assert _intent(kernel.chat(text)) == "validated_knowledge"

    def test_self_knowledge_topics_still_work(self, kernel):
        # a genuine self-knowledge question is unchanged by the precedence guard
        message = kernel.chat("What are your current limitations?")
        assert _intent(message) == BUILTIN_INTENT_SELF_KNOWLEDGE

    def test_plain_knowledge_questions_are_unchanged(self, kernel):
        assert _intent(kernel.chat("What do you know about the telemetry_index?")) == (
            "validated_knowledge"
        )


class TestArchitectureStructure:
    @pytest.mark.parametrize(
        "text",
        [
            "How is the conversation service structured?",
            "What is the structure of the conversation service?",
            "How is the conversation service organized?",
        ],
    )
    def test_component_structure_forms(self, kernel, text):
        message = kernel.chat(text)
        assert _intent(message) == BUILTIN_INTENT_ARCHITECTURE
        assert "Structure of component" in message.content
        assert message.metadata["architecture"]["kind"] == "component_structure"

    @pytest.mark.parametrize(
        "text",
        [
            "What components make up the research subsystem?",
            "Which components belong to the research subsystem?",
            "What is the structure of the research subsystem?",
        ],
    )
    def test_subsystem_composition_forms(self, kernel, text):
        message = kernel.chat(text)
        assert _intent(message) == BUILTIN_INTENT_ARCHITECTURE
        assert "Structure of subsystem" in message.content
        assert message.metadata["architecture"]["kind"] == "subsystem_structure"

    @pytest.mark.parametrize(
        "text",
        [
            "How is the Zorblax component structured?",
            "What components make up the Glorptronic subsystem?",
        ],
    )
    def test_unresolvable_structure_targets_are_reported_honestly(self, kernel, text):
        # fail closed: no structure is invented for an unknown target
        message = kernel.chat(text)
        kind = (message.metadata.get("architecture") or {}).get("kind")
        assert kind not in ("component_structure", "subsystem_structure")
        assert "no registered component" in message.content.lower()
        assert message.metadata["model_used"] is False

    def test_existing_architecture_answers_are_unchanged(self, kernel):
        assert _intent(kernel.chat("What are your governance boundaries?")) == (
            BUILTIN_INTENT_ARCHITECTURE
        )
        responsibility = kernel.chat(
            "What is the responsibility of the conversation service component?"
        )
        assert responsibility.metadata["architecture"]["kind"] == "component"


class TestInvestigationIdioms:
    @pytest.mark.parametrize(
        "text",
        [
            "Look into why the deployment fails.",
            "Dig into the sandbox failure.",
            "Check out the promotion gate.",
            "Check into the approval flow.",
        ],
    )
    def test_idioms_classify_as_investigation(self, text):
        from atlas.conversation.task_intake import TaskIntake, TaskType

        assert (
            TaskIntake().intake(text).task_type is TaskType.INVESTIGATION_REQUEST
        )

    @pytest.mark.parametrize(
        "text",
        [
            "Check whether the telemetry_index is documented.",
            "Research the deployment pipeline.",
            "What do you know about the sandbox?",
        ],
    )
    def test_knowledge_and_research_phrasings_are_not_captured(self, text):
        from atlas.conversation.task_intake import TaskIntake, TaskType

        assert TaskIntake().intake(text).task_type is not TaskType.INVESTIGATION_REQUEST

    def test_idiom_reaches_the_investigation_surface(self, kernel):
        message = kernel.chat("Look into why the deployment fails.")
        assert message.metadata.get("investigation") is not None
        assert _intent(message) != "validated_knowledge"

    def test_classified_investigation_keeps_its_route(self, kernel):
        message = kernel.chat("Check out the promotion gate.")
        assert message.metadata.get("investigation") is not None

    def test_mention_guard_still_prevents_approval_hijack(self, kernel):
        from atlas.conversation.task_intake import TaskIntake, TaskType

        assert (
            TaskIntake().intake("Look into the approval flow.").task_type
            is TaskType.INVESTIGATION_REQUEST
        )
        assert kernel.pending_promotion_reviews() == []


class TestStep1PolicyPreserved:
    def test_internal_state_precedence_is_unchanged(self):
        order = list(EXPOSURE_PRECEDENCE)
        for surface in (
            "capability_detail",
            "capability_state",
            "architecture",
            "self_knowledge",
            "knowledge_state",
            "source_authorization",
        ):
            assert order.index(surface) < order.index("knowledge_request")
            assert order.index(surface) < order.index("validated_knowledge")

    def test_step1_surfaces_still_work(self, kernel):
        state = kernel.chat("Is your knowledge about the telemetry_index current?")
        assert _intent(state) == BUILTIN_INTENT_KNOWLEDGE_STATE
        requirements = kernel.chat("What does the research capability require?")
        assert "Requirements for `research`" in requirements.content
        authorization = kernel.chat("Authorize wikipedia.org as a research source.")
        assert _intent(authorization) == BUILTIN_INTENT_SOURCE_AUTHORIZATION


class TestContextAndParity:
    def test_reference_and_clarification_are_preserved(self, kernel):
        kernel.chat("Investigate the approval flow.")
        found = kernel.chat("What did you find?")
        assert _intent(found) == "reference"
        ambiguous = kernel.chat("Is it current?")
        assert ambiguous.content

    def test_multi_turn_subject_then_state_question(self, kernel):
        kernel.chat("What do you know about the telemetry_index?")
        message = kernel.chat("Is your knowledge about the telemetry_index current?")
        assert _intent(message) == BUILTIN_INTENT_KNOWLEDGE_STATE

    @pytest.mark.parametrize(
        "text",
        [
            "Is your knowledge about the telemetry_index still current?",
            "Has the telemetry_index gone stale?",
            "How is the conversation service structured?",
            "What components make up the research subsystem?",
            "Authorization for wikipedia.org as a research source: explain it.",
        ],
    )
    def test_stream_and_send_agree(self, kernel, text):
        sent = kernel.chat(text)
        streamed = "".join(kernel.stream(text))
        assert sent.content.strip() == streamed.strip()

    def test_no_network_and_no_authority(self, kernel, monkeypatch):
        def _blocked(*args, **kwargs):
            raise AssertionError("no network access is allowed")

        monkeypatch.setattr(socket.socket, "connect", _blocked)
        head = _git_head()
        for text in (
            "Has the telemetry_index gone stale?",
            "How is the conversation service structured?",
            "Look into why the deployment fails.",
        ):
            message = kernel.chat(text)
            assert (message.metadata or {}).get("model_used") in (False, None)
        assert kernel.pending_promotion_reviews() == []
        assert _git_head() == head


def _git_head() -> str:
    import subprocess

    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    ).stdout.strip()
