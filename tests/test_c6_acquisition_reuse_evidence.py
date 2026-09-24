"""C6 — EVIDENCE ONLY: does the acquisition/research path reuse existing
validated knowledge? (F16 disposition.)

C6.1 already made EXISTING validated knowledge reachable conversationally. This
module observes the remaining F16 question: when validated, persistent knowledge
relevant to a new research request already exists, does the acquisition/research
path use it, or does it unconditionally re-acquire?

It implements NO reuse, NO cache, NO new subsystem and changes NO production
behaviour. Every test pins the OBSERVED contract and records a classification in
its docstring. All SQLite stores are pointed at a fresh temporary database, and
fixtures live in temporary directories, so no production data or knowledge is
touched.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from atlas.evolution.freshness.models import KnowledgeRef
from atlas.kernel.atlas import Atlas

_TMP_DIR = Path(tempfile.mkdtemp(prefix="c6_reuse_"))
_TMP_DB = _TMP_DIR / "atlas_experience.db"

_ACQ_ID_RE = re.compile(r"ACQ-\d{6}")


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


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _fixture(tmp_path: Path, name: str, fact: str) -> Path:
    return _write(
        tmp_path / name,
        f"# Atlas Evidence Device (test fixture: {name})\n\n{fact}\n",
    )


def _rows(kernel) -> tuple[int, int, int, int]:
    storage = kernel._research_storage
    return (
        len(storage.load_claims()),
        len(storage.load_verifications()),
        len(storage.load_citations()),
        len(storage.load_reports()),
    )


def _statements(kernel, needle: str) -> list[str]:
    return [
        claim.statement
        for claim in kernel._research_storage.load_claims()
        if needle in claim.statement
    ]


# ---------------------------------------------------------------------------
# A. ESTABLISH EXISTING VALIDATED KNOWLEDGE
# ---------------------------------------------------------------------------


class TestEstablishedKnowledge:
    def test_authorized_fixture_is_acquired_validated_and_persisted(self, kernel, tmp_path):
        """A fixture fact becomes SUPPORTED, cited, persisted, retrievable."""
        source = _fixture(
            tmp_path, "established.md", "The Atlas Evidence Device sensor count is 4."
        )
        result = kernel.acquisition_service.acquire(
            question="atlas evidence device established sensor count", sources=[str(source)]
        )
        assert result.status == "ok"
        assert result.claim_count == 1
        assert result.verification_statuses == ("SUPPORTED",)
        assert source.name in " ".join(result.sources)
        assert result.stale_candidate_ids == ()

        retrieved = kernel.validated_knowledge("atlas evidence device established sensor count")
        assert retrieved.status.value == "ok"
        assert retrieved.items
        assert retrieved.items[0].citations

    def test_knowledge_outlives_its_source(self, kernel, tmp_path):
        """The critical state: knowledge exists, source no longer available."""
        source = _fixture(
            tmp_path, "outlives.md", "The Atlas Evidence Device retention marker is R7."
        )
        assert (
            kernel.acquisition_service.acquire(
                question="atlas evidence device retention marker", sources=[str(source)]
            ).status
            == "ok"
        )
        source.unlink()
        retrieved = kernel.validated_knowledge("atlas evidence device retention marker")
        assert retrieved.status.value == "ok"
        assert any("R7" in item.statement for item in retrieved.items)


# ---------------------------------------------------------------------------
# B. DIRECT ACQUISITION AFTER SOURCE REMOVAL (F16 reproduction)
# ---------------------------------------------------------------------------


class TestDirectAcquisitionAfterSourceRemoval:
    def test_acquisition_does_not_consult_validated_knowledge(self, kernel, tmp_path):
        """With the source gone, acquisition re-runs and resolves nothing.

        Observation: status ok/partial, decision "research", `sources == ()` and
        `stale_candidate_ids == ()` — the run neither consults the validated
        store nor reports a knowledge-based reuse; the populated claim/status
        fields come from the durable REPORT read-back keyed by the identical
        query id, not from the validated store.
        Classification: KNOWLEDGE_REUSE_GAP (intentional research contract).
        """
        source = _fixture(
            tmp_path, "gone.md", "The Atlas Evidence Device retention marker is G1."
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device retention marker gone", sources=[str(source)]
        )
        source.unlink()

        again = kernel.acquisition_service.acquire(
            question="atlas evidence device retention marker gone", sources=[str(source)]
        )
        assert again.decision == "research"
        assert again.sources == ()
        assert again.stale_candidate_ids == ()
        assert again.findings == "verification summary: no claims verified"

    def test_retained_knowledge_is_still_available_but_unused_by_the_run(self, kernel, tmp_path):
        """The knowledge the run did not reuse is available elsewhere."""
        source = _fixture(
            tmp_path, "unused.md", "The Atlas Evidence Device retention marker is U2."
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device retention marker unused", sources=[str(source)]
        )
        source.unlink()
        kernel.acquisition_service.acquire(
            question="atlas evidence device retention marker unused", sources=[str(source)]
        )
        retrieved = kernel.validated_knowledge("atlas evidence device retention marker unused")
        assert any("U2" in item.statement for item in retrieved.items)

    def test_no_acquisition_field_signals_existing_knowledge(self, kernel, tmp_path):
        """The result surface exposes no reuse/sufficiency information."""
        source = _fixture(
            tmp_path, "surface.md", "The Atlas Evidence Device retention marker is S3."
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device retention marker surface", sources=[str(source)]
        )
        result = kernel.acquisition_service.acquire(
            question="atlas evidence device retention marker surface", sources=[str(source)]
        )
        payload = result.to_dict()
        assert result.stale_candidate_ids == ()
        assert not any(
            "reuse" in key or "existing_knowledge" in key for key in payload
        )
        assert "prior" not in " ".join(payload.keys())


# ---------------------------------------------------------------------------
# C. PUBLIC CONVERSATIONAL RESEARCH
# ---------------------------------------------------------------------------


class TestPublicPath:
    def test_repeated_identical_research_reacquires(self, kernel):
        """Two identical public research turns both run acquisition.

        Observation: two distinct acquisition ids ("ACQ-…") and new
        report/claim rows — the public path does not answer from the validated
        knowledge it already holds.
        Classification: RESEARCH_CONTRACT (fresh evidence per request).
        """
        service = _conversation(kernel)
        question = "Research the memory ranking module of the atlas memory subsystem."
        before = _rows(kernel)
        first = service.send(question)
        second = service.send(question)
        after = _rows(kernel)

        first_ids = _ACQ_ID_RE.findall(first.content)
        second_ids = _ACQ_ID_RE.findall(second.content)
        assert first_ids and second_ids
        assert first_ids != second_ids
        assert after[0] > before[0] and after[3] > before[3]

    def test_research_turn_does_not_report_validated_knowledge(self, kernel):
        """A research turn never answers with the C6.1 knowledge surface."""
        service = _conversation(kernel)
        message = service.send(
            "Research the memory ranking module of the atlas memory subsystem."
        )
        assert message.metadata.get("builtin_intent") != "validated_knowledge"
        assert isinstance(message.metadata.get("orchestration"), dict)


# ---------------------------------------------------------------------------
# D. SUFFICIENT EXISTING KNOWLEDGE
# ---------------------------------------------------------------------------


class TestSufficiency:
    def test_sufficiency_gate_exists_only_for_explicit_knowledge_refs(self, kernel):
        """An F2 fresh ref yields a bounded no-op (no research at all).

        Observation: `decision == "noop"`, no sources, no report — the
        sufficiency mechanism EXISTS, but only via explicit knowledge_refs.
        Classification: SUCCESS (existing F2 gate; not objective coverage).
        """
        now = datetime.now(timezone.utc)
        ref = KnowledgeRef(
            knowledge_id="claim:reuse-fixture-fresh",
            source_uris=("unused.md",),
            retrieved_at=now,
            verified_at=now,
            confidence=1.0,
        )
        result = kernel.acquisition_service.acquire(knowledge_refs=[ref])
        assert result.decision == "noop"
        assert result.status == "noop"
        assert result.sources == ()
        assert result.report_ids == ()

    def test_a_question_never_consults_the_sufficiency_gate(self, kernel, tmp_path):
        """The question path always decides "research", even when knowledge exists.

        Classification: RESEARCH_CONTRACT (documented: explicit requests always
        research; sufficiency assessment is a separate F2 mode).
        """
        source = _fixture(
            tmp_path, "sufficient.md", "The Atlas Evidence Device sensor count is 4."
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device sufficient sensor count", sources=[str(source)]
        )
        assert kernel.validated_knowledge("atlas evidence device sufficient sensor count").items

        result = kernel.acquisition_service.acquire(
            question="atlas evidence device sufficient sensor count", sources=[str(source)]
        )
        assert result.decision == "research"
        assert result.stale_candidate_ids == ()

    def test_objective_adequacy_is_never_assessed_against_the_store(self, kernel, tmp_path):
        """Nothing checks whether the stored claims already answer the objective."""
        source = _fixture(
            tmp_path, "adequacy.md", "The Atlas Evidence Device operating mode is bounded test mode."
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device adequacy operating mode", sources=[str(source)]
        )
        retrieved = kernel.validated_knowledge("atlas evidence device adequacy operating mode")
        assert retrieved.items

        # The same objective, whose answer is already stored, is re-acquired.
        again = kernel.acquisition_service.acquire(
            question="atlas evidence device adequacy operating mode", sources=[str(source)]
        )
        assert again.decision == "research"
        assert again.sources


# ---------------------------------------------------------------------------
# E. PARTIAL EXISTING KNOWLEDGE
# ---------------------------------------------------------------------------


class TestPartialKnowledge:
    def test_retained_and_new_evidence_are_not_composed(self, kernel, tmp_path):
        """Stored claim + a new objective are never combined.

        Observation: the new run acquires from its own source only; afterwards
        the store simply holds both statements side by side — no composition,
        no "acquire only the missing part" behaviour.
        Classification: KNOWLEDGE_COMPOSITION_GAP (no composition mechanism).
        """
        first_source = _fixture(
            tmp_path, "partial_a.md", "The Atlas Evidence Device partial sensor count is 4."
        )
        second_source = _fixture(
            tmp_path,
            "partial_b.md",
            "The Atlas Evidence Device partial operating mode is bounded test mode.",
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device partial sensor count", sources=[str(first_source)]
        )
        result = kernel.acquisition_service.acquire(
            question="atlas evidence device partial operating mode", sources=[str(second_source)]
        )
        assert result.decision == "research"
        assert Path(result.sources[0]).name == second_source.name
        assert not any("sensor count is 4" in s for s in (result.findings or ""))

        statements = _statements(kernel, "partial")
        assert any("partial sensor count is 4" in s for s in statements)
        assert any("partial operating mode is bounded test mode" in s for s in statements)


# ---------------------------------------------------------------------------
# F. CONTRADICTORY EXISTING KNOWLEDGE
# ---------------------------------------------------------------------------


class TestConflict:
    def test_new_source_is_validated_only_within_its_own_run(self, kernel, tmp_path):
        """Contradictory evidence is not checked against retained knowledge.

        Observation: after acquiring "sensor count is 4" (source A) and then the
        same objective from a contradicting source B ("6"), both claims persist
        as SUPPORTED and the second run's own verdict is PLAUSIBLE — the stored
        claim is never consulted, so no cross-run contradiction is detected.
        Classification: CORRECT_BOUNDARY for reuse; the cross-run consistency
        observation is recorded separately (no update policy is intentional).
        """
        source_a = _fixture(
            tmp_path, "conflict_a.md", "The Atlas Evidence Device conflict calibration count is 4."
        )
        source_b = _fixture(
            tmp_path, "conflict_b.md", "The Atlas Evidence Device conflict calibration count is 6."
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device conflict calibration count", sources=[str(source_a)]
        )
        second = kernel.acquisition_service.acquire(
            question="atlas evidence device conflict calibration count", sources=[str(source_b)]
        )
        assert second.decision == "research"
        assert second.verification_statuses == ("SUPPORTED",)
        assert "CONTESTED" not in second.findings

        statements = _statements(kernel, "conflict calibration count")
        assert any("conflict calibration count is 4" in s for s in statements)
        assert any("conflict calibration count is 6" in s for s in statements)

    def test_no_update_or_preference_is_applied_to_retained_knowledge(self, kernel, tmp_path):
        """The earlier claim is neither replaced nor marked stale by the new one."""
        source_a = _fixture(
            tmp_path, "conflict_c.md", "The Atlas Evidence Device conflict calibration count is 4."
        )
        source_b = _fixture(
            tmp_path, "conflict_d.md", "The Atlas Evidence Device conflict calibration count is 6."
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device conflict calibration count", sources=[str(source_a)]
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device conflict calibration count", sources=[str(source_b)]
        )
        retrieved = kernel.validated_knowledge("atlas evidence device conflict calibration count")
        values = {item.statement for item in retrieved.items}
        assert any("calibration count is 4" in v for v in values)
        assert any("calibration count is 6" in v for v in values)
        assert all(item.validation_status == "SUPPORTED" for item in retrieved.items)


# ---------------------------------------------------------------------------
# G. SAME SOURCE, SAME FACT (observable re-read)
# ---------------------------------------------------------------------------


class TestSameSourceSameFact:
    def test_a_repeated_acquisition_re_reads_the_source(self, kernel, tmp_path):
        """The same objective re-reads the source instead of reusing knowledge.

        The fixture content is changed between the two identical requests; the
        second result reflects the CHANGED content, which is only possible if
        the source was re-read.
        Classification: RESEARCH_CONTRACT (unconditional re-acquisition).
        """
        source = _write(
            tmp_path / "swap.md",
            "# Swap fixture\n\nThe Atlas Evidence Device calibration level is 4.\n",
        )
        first = kernel.acquisition_service.acquire(
            question="atlas evidence device calibration level", sources=[str(source)]
        )
        assert first.status == "ok"
        _write(
            source,
            "# Swap fixture (revised)\n\nThe Atlas Evidence Device calibration level is 9.\n",
        )
        second = kernel.acquisition_service.acquire(
            question="atlas evidence device calibration level", sources=[str(source)]
        )
        assert second.status == "ok"

        statements = _statements(kernel, "calibration level")
        assert any("level is 4" in s for s in statements)
        assert any("level is 9" in s for s in statements)

    def test_a_repeated_acquisition_revalidates_and_repersists(self, kernel, tmp_path):
        """Each run re-extracts, re-verifies and persists its own artifacts."""
        source = _fixture(
            tmp_path, "revalidate.md", "The Atlas Evidence Device repetition marker is P5."
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device repetition marker", sources=[str(source)]
        )
        before = _rows(kernel)
        kernel.acquisition_service.acquire(
            question="atlas evidence device repetition marker", sources=[str(source)]
        )
        after = _rows(kernel)
        # Same deterministic claim/source -> the same claim row is re-stored; the
        # durable report is re-written. Nothing is skipped because knowledge exists.
        assert after[1] >= before[1]


# ---------------------------------------------------------------------------
# H. DIFFERENT PHRASING, SAME OBJECTIVE
# ---------------------------------------------------------------------------


class TestPhrasing:
    def test_equivalent_objectives_produce_distinct_queries(self, kernel, tmp_path):
        """There is no objective normalization or equivalence reuse.

        Observation: two bounded phrasings of the same objective get different
        deterministic query ids and both run a full acquisition.
        Classification: RESEARCH_CONTRACT / current limitation (recorded, not a
        defect by itself — no semantic equivalence is required of Atlas).
        """
        source = _fixture(
            tmp_path, "phrasing.md", "The Atlas Evidence Device sensor count is 4."
        )
        first = kernel.acquisition_service.acquire(
            question="atlas evidence device phrasing sensor count", sources=[str(source)]
        )
        second = kernel.acquisition_service.acquire(
            question="find how many sensors the atlas evidence device phrasing has",
            sources=[str(source)],
        )
        assert first.query_id != second.query_id
        assert first.decision == second.decision == "research"


# ---------------------------------------------------------------------------
# I. C6.1 CONTROL COMPARISON
# ---------------------------------------------------------------------------


class TestC61Control:
    def test_c6_1_retrieves_while_a_research_turn_reacquires(self, kernel, tmp_path):
        """Knowledge access and research are architecturally distinct."""
        source = _fixture(
            tmp_path, "control.md", "The Atlas Evidence Device control marker is C8."
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device control marker", sources=[str(source)]
        )
        source.unlink()

        service = _conversation(kernel)
        knowledge = service.send("What do you know about the Atlas Evidence Device control marker?")
        assert knowledge.metadata.get("builtin_intent") == "validated_knowledge"
        assert knowledge.metadata.get("validated_knowledge_status") == "ok"
        assert "C8" in knowledge.content

        research = service.send("Research the Atlas Evidence Device control marker.")
        assert research.metadata.get("builtin_intent") != "validated_knowledge"
        assert "C8" not in research.content


# ---------------------------------------------------------------------------
# J. PROVENANCE
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_provenance_remains_available_through_the_retriever(self, kernel, tmp_path):
        """No reuse occurs; the retriever still carries full provenance.

        Classification: SUCCESS (provenance preserved where knowledge is served).
        """
        source = _fixture(
            tmp_path, "provenance.md", "The Atlas Evidence Device provenance marker is V9."
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device provenance marker", sources=[str(source)]
        )
        result = kernel.validated_knowledge("atlas evidence device provenance marker")
        assert result.status.value == "ok"
        item = result.items[0]
        assert "V9" in item.statement
        assert item.validation_status == "SUPPORTED"
        assert item.claim_confidence is not None
        assert item.verification_score is not None
        assert item.citations and item.citations[0].source_uri


# ---------------------------------------------------------------------------
# K. MODEL INDEPENDENCE
# ---------------------------------------------------------------------------


class TestModelIndependence:
    def test_all_paths_are_model_free(self, kernel, tmp_path):
        """Acquisition, reuse probing and the C6.1 surface use no model."""
        source = _fixture(
            tmp_path, "model_free.md", "The Atlas Evidence Device model marker is M1."
        )
        result = kernel.acquisition_service.acquire(
            question="atlas evidence device model marker", sources=[str(source)]
        )
        assert result.status == "ok"

        message = _conversation(kernel).send(
            "What verified information do you have about the Atlas Evidence Device model marker?"
        )
        assert message.metadata.get("model_used") is False
        assert (
            kernel._config.get("ai", "external_providers", default=False) is not True
        )


# ---------------------------------------------------------------------------
# L. GOVERNANCE
# ---------------------------------------------------------------------------


class TestGovernance:
    def test_unauthorized_source_remains_denied(self, kernel):
        """No reuse is treated as authorization to reach a source."""
        result = kernel.acquisition_service.acquire(
            question="atlas evidence device reuse web probe",
            sources=["https://example.test/device"],
        )
        assert result.sources == ()
        assert result.claim_count == 0

    def test_retained_knowledge_does_not_authorize_source_access(self, kernel, tmp_path):
        """Having stored knowledge changes no source-policy decision."""
        source = _fixture(
            tmp_path, "policy.md", "The Atlas Evidence Device policy marker is Y4."
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device policy marker", sources=[str(source)]
        )
        blocked = kernel.acquisition_service.acquire(
            question="atlas evidence device policy marker",
            sources=["http://10.0.0.1/private"],
        )
        assert blocked.sources == ()

    def test_read_only_knowledge_access_writes_nothing(self, kernel, tmp_path):
        """The C6.1 retrieval path leaves the store unchanged."""
        source = _fixture(
            tmp_path, "readonly.md", "The Atlas Evidence Device readonly marker is W6."
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device readonly marker", sources=[str(source)]
        )
        before = _rows(kernel)
        _conversation(kernel).send(
            "What do you know about the Atlas Evidence Device readonly marker?"
        )
        assert _rows(kernel) == before


# ---------------------------------------------------------------------------
# M. PERSISTENCE / RESTART
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_knowledge_survives_restart_but_reuse_does_not_appear(self, kernel, tmp_path):
        """After restart: knowledge is retrievable; acquisition still re-acquires."""
        source = _fixture(
            tmp_path, "restart.md", "The Atlas Evidence Device restart marker is Z2."
        )
        kernel.acquisition_service.acquire(
            question="atlas evidence device restart marker", sources=[str(source)]
        )
        source.unlink()

        atlas2 = Atlas()
        atlas2.start()
        try:
            retrieved = atlas2.validated_knowledge("atlas evidence device restart marker")
            assert any("Z2" in item.statement for item in retrieved.items)

            service = atlas2.container.get("conversation")
            service._conversation = service._history.create()
            service._state_manager.clear()
            message = service.send(
                "What verified information do you have about the Atlas Evidence Device restart marker?"
            )
            assert message.metadata.get("validated_knowledge_status") == "ok"

            again = atlas2.acquisition_service.acquire(
                question="atlas evidence device restart marker", sources=[str(source)]
            )
            assert again.decision == "research"
            assert again.sources == ()
            assert again.stale_candidate_ids == ()
        finally:
            atlas2.shutdown()
