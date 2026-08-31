"""P3/B3.1 — Per-user preference & correction capture tests.

Verifies the additive interaction-recording layer:
- per-user preference records with provenance
- correction capture (user fixes an Atlas mistake -> recorded)
- provenance on every record (principal + authority + session + action)
- per-user scoping (no cross-user bleed)
- safe bounds (control chars stripped, oversized input truncated)
- fail-closed behavior (missing/invalid session, empty fields)
- authority preserved (OWNER/USER attribution, no self-elevation)
- no schema change, no infrastructure imports
"""

from __future__ import annotations

import pytest

from atlas.authority.service import AuthorityService
from atlas.interaction.models import (
    CorrectionRecord,
    InteractionKind,
    PreferenceRecord,
    Provenance,
)
from atlas.interaction.repository import InteractionRepository
from atlas.interaction.recorder import InteractionRecorder
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager


def _make_ctx(owner=False, user_id="alice", user_name="Alice"):
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    if owner:
        session = manager.create_session("owner")
    else:
        authority.add_user(user_name, principal_id=user_id)
        session = manager.create_session(user_id)
    return SessionContext.from_session(session)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TestModels:
    def test_preference_record_provenance_roundtrip(self):
        prov = Provenance(
            principal_id="alice",
            authority="user",
            session_id="s1",
            action="record_preference",
            source="interaction",
        )
        rec = PreferenceRecord("PREF-00000001", "alice", "tone", "concise", prov)
        d = rec.to_dict()
        assert d["kind"] == InteractionKind.PREFERENCE.value
        assert d["principal_id"] == "alice"
        assert d["provenance"]["authority"] == "user"

    def test_correction_record_provenance_roundtrip(self):
        prov = Provenance(principal_id="alice", authority="user", session_id="s1")
        rec = CorrectionRecord("CORR-00000001", "alice", "memory", "wrong", "use X", prov)
        d = rec.to_dict()
        assert d["kind"] == InteractionKind.CORRECTION.value
        assert d["correction"] == "use X"


# ---------------------------------------------------------------------------
# Repository scoping
# ---------------------------------------------------------------------------

class TestRepositoryScoping:
    def test_per_user_isolation(self):
        repo = InteractionRepository()
        repo.store_preference(
            PreferenceRecord("P1", "alice", "tone", "concise", Provenance("alice", "user"))
        )
        repo.store_preference(
            PreferenceRecord("P2", "bob", "tone", "verbose", Provenance("bob", "user"))
        )
        assert [r.principal_id for r in repo.get_preferences("alice")] == ["alice"]
        assert [r.principal_id for r in repo.get_preferences("bob")] == ["bob"]
        assert repo.get_preferences("carol") == []

    def test_bounded_and_fail_closed(self):
        repo = InteractionRepository(max_preferences=2, max_corrections=1)
        repo.store_preference(PreferenceRecord("P1", "a", "k", "v", Provenance("a", "user")))
        repo.store_preference(PreferenceRecord("P2", "a", "k", "v", Provenance("a", "user")))
        repo.store_preference(PreferenceRecord("P3", "a", "k", "v", Provenance("a", "user")))
        # Bounded: only 2 retained; "P1" evicted.
        assert repo.preference_count == 2
        assert repo.get_preference("P1") is None

    def test_get_preference_and_correction_by_id(self):
        repo = InteractionRepository()
        p = PreferenceRecord("P9", "a", "k", "v", Provenance("a", "user"))
        c = CorrectionRecord("C9", "a", "t", "d", "corr", Provenance("a", "user"))
        repo.store_preference(p)
        repo.store_correction(c)
        assert repo.get_preference("P9") is p
        assert repo.get_correction("C9") is c


# ---------------------------------------------------------------------------
# Recorder (provenance + authority + bounds + fail-closed)
# ---------------------------------------------------------------------------

class TestRecorder:
    def test_record_preference_with_owner_provenance(self):
        ctx = _make_ctx(owner=True)
        rec = InteractionRecorder()
        result = rec.record_preference(ctx, "response_length", "concise")
        assert isinstance(result, PreferenceRecord)
        assert result.principal_id == "owner"
        assert result.provenance.authority == "owner"
        assert result.provenance.session_id == ctx.session_id

    def test_record_preference_with_user_provenance(self):
        ctx = _make_ctx(owner=False)
        rec = InteractionRecorder()
        result = rec.record_preference(ctx, "tone", "casual")
        assert result.principal_id == "alice"
        assert result.provenance.authority == "user"
        # Authority comes from the session, never from text.
        assert result.key == "tone"

    def test_record_correction_captures_fix(self):
        ctx = _make_ctx(owner=False)
        rec = InteractionRecorder()
        result = rec.record_correction(
            ctx,
            target="memory recall",
            description="Atlas returned the wrong episode",
            correction="use the 2026 episode, not 2025",
        )
        assert isinstance(result, CorrectionRecord)
        assert result.principal_id == "alice"
        assert result.correction == "use the 2026 episode, not 2025"
        assert rec.repository.correction_count == 1

    def test_fail_closed_missing_session(self):
        rec = InteractionRecorder()
        assert rec.record_preference(None, "k", "v") is None
        assert rec.record_correction(None, "t", "d", "c") is None
        assert rec.repository.preference_count == 0
        assert rec.repository.correction_count == 0

    def test_fail_closed_empty_fields(self):
        ctx = _make_ctx(owner=False)
        rec = InteractionRecorder()
        assert rec.record_preference(ctx, "", "v") is None
        assert rec.record_preference(ctx, "k", "") is None
        assert rec.record_correction(ctx, "", "d", "c") is None
        assert rec.record_correction(ctx, "t", "d", "") is None

    def test_bounded_text_and_control_char_strip(self):
        ctx = _make_ctx(owner=False)
        rec = InteractionRecorder()
        result = rec.record_preference(ctx, "k", "a\x00b\x1f\n" + "x" * 5000)
        assert result is not None
        assert "\x00" not in result.value
        assert "\x1f" not in result.value
        assert len(result.value) <= 1000

    def test_record_ids_are_monotonic(self):
        ctx = _make_ctx(owner=False)
        rec = InteractionRecorder()
        a = rec.record_preference(ctx, "k", "v1")
        b = rec.record_preference(ctx, "k", "v2")
        assert a.record_id == "PREF-00000001"
        assert b.record_id == "PREF-00000002"


# ---------------------------------------------------------------------------
# No schema / no infrastructure
# ---------------------------------------------------------------------------

class TestArchitectureBoundaries:
    def test_no_infrastructure_imports(self):
        import atlas.interaction.models as m
        import atlas.interaction.repository as r
        import atlas.interaction.recorder as rec

        forbidden = {"atlas.events", "atlas.storage", "atlas.config", "atlas.state", "sqlite3"}
        for mod in (m, r, rec):
            import inspect
            source = inspect.getsource(mod)
            for f in forbidden:
                assert f not in source, f"{mod.__name__} imports {f}"

    def test_schema_unchanged(self):
        from atlas.storage.migration import CURRENT_SCHEMA_VERSION
        assert CURRENT_SCHEMA_VERSION == 11
