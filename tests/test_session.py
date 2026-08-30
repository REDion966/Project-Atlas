"""P1/B1.2 — Session-scoped context tests.

Covers:
  1. session creation
  2. stable session ID
  3. session → principal attribution
  4. Owner session
  5. User session
  6. invalid/unknown principal rejection
  7. principal reassignment prevention
  8. session/context propagation
  9. conversation receives correct session scope
 10. memory/context receives correct scope where the architecture supports it
 11. backward compatibility where intentionally supported
 12. kernel wiring
 13. multiple sessions remaining isolated in-memory
 14. authority checks can consume session principal
 15. fail-closed behavior
"""

from __future__ import annotations

import pytest

from atlas.authority.models import AuthorityLevel
from atlas.authority.service import AuthorityService
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager
from atlas.session.models import Session


class TestSessionCreation:
    def test_create_owner_session(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        sess = mgr.create_session("owner")
        assert sess.principal_id == "owner"
        assert sess.is_owner
        assert sess.authority is AuthorityLevel.OWNER

    def test_create_user_session(self):
        auth = AuthorityService("Owner")
        auth.add_user("Alice", principal_id="alice")
        mgr = SessionManager(auth)
        sess = mgr.create_session("alice")
        assert sess.principal_id == "alice"
        assert not sess.is_owner
        assert sess.authority is AuthorityLevel.USER

    def test_session_id_is_stable(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        s1 = mgr.create_session("owner")
        s2 = mgr.create_session("owner")
        assert s1.session_id != s2.session_id
        assert s1.session_id == mgr.get(s1.session_id).session_id

    def test_session_has_created_at(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        sess = mgr.create_session("owner")
        assert sess.created_at is not None
        assert sess.created_at.tzinfo is not None

    def test_session_to_dict(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        sess = mgr.create_session("owner")
        d = sess.to_dict()
        assert d["session_id"] == sess.session_id
        assert d["principal_id"] == "owner"
        assert d["authority"] == "owner"


class TestSessionManagerValidation:
    def test_requires_authority_service(self):
        with pytest.raises(ValueError):
            SessionManager(None)  # type: ignore[arg-type]

    def test_unknown_principal_fails_closed(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        with pytest.raises(PermissionError):
            mgr.create_session("ghost")
        assert mgr.count() == 0

    def test_empty_principal_id_fails_closed(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        with pytest.raises(ValueError):
            mgr.create_session("")
        with pytest.raises(ValueError):
            mgr.create_session("   ")

    def test_get_unknown_returns_none(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        assert mgr.get("nope") is None
        assert mgr.get(123) is None  # type: ignore[arg-type]

    def test_require_unknown_raises(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        with pytest.raises(PermissionError):
            mgr.require("nope")

    def test_is_valid(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        sess = mgr.create_session("owner")
        assert mgr.is_valid(sess.session_id)
        assert not mgr.is_valid("ghost")


class TestPrincipalReassignmentPrevention:
    def test_session_is_frozen(self):
        auth = AuthorityService("Owner")
        auth.add_user("Alice", principal_id="alice")
        mgr = SessionManager(auth)
        sess = mgr.create_session("alice")
        with pytest.raises(Exception):
            sess.session_id = "hacked"  # type: ignore[misc]
        with pytest.raises(Exception):
            sess.principal = auth.owner  # type: ignore[misc]

    def test_session_never_changes_principal(self):
        auth = AuthorityService("Owner")
        auth.add_user("Alice", principal_id="alice")
        mgr = SessionManager(auth)
        sess = mgr.create_session("alice")
        assert sess.principal_id == "alice"
        # No API exists to mutate the principal; the stored session is the same object.
        stored = mgr.get(sess.session_id)
        assert stored.principal_id == "alice"

    def test_user_session_never_becomes_owner(self):
        auth = AuthorityService("Owner")
        auth.add_user("Alice", principal_id="alice")
        mgr = SessionManager(auth)
        sess = mgr.create_session("alice")
        assert not sess.is_owner
        assert sess.authority is AuthorityLevel.USER

    def test_session_context_is_frozen(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        sess = mgr.create_session("owner")
        ctx = SessionContext.from_session(sess)
        with pytest.raises(Exception):
            ctx.session = sess  # type: ignore[misc]


class TestIsolation:
    def test_multiple_sessions_isolated(self):
        auth = AuthorityService("Owner")
        auth.add_user("Alice", principal_id="alice")
        auth.add_user("Bob", principal_id="bob")
        mgr = SessionManager(auth)
        s_owner = mgr.create_session("owner")
        s_alice = mgr.create_session("alice")
        s_bob = mgr.create_session("bob")
        assert mgr.count() == 3
        assert len({s_owner.session_id, s_alice.session_id, s_bob.session_id}) == 3
        assert mgr.sessions_for_principal("alice") == [s_alice]
        assert mgr.sessions_for_principal("bob") == [s_bob]
        assert mgr.sessions_for_principal("owner") == [s_owner]

    def test_sessions_for_unknown_principal_empty(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        assert mgr.sessions_for_principal("ghost") == []


class TestSessionContext:
    def test_from_session(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        sess = mgr.create_session("owner")
        ctx = SessionContext.from_session(sess, action="test")
        assert ctx.session_id == sess.session_id
        assert ctx.principal_id == "owner"
        assert ctx.is_owner
        assert ctx.action == "test"

    def test_authority_context(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        sess = mgr.create_session("owner")
        ctx = SessionContext.from_session(sess, action="act")
        ac = ctx.authority_context()
        assert ac.principal.principal_id == "owner"
        assert ac.action == "act"

    def test_satisfies(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        owner_sess = mgr.create_session("owner")
        owner_ctx = SessionContext.from_session(owner_sess)
        assert owner_ctx.satisfies(AuthorityLevel.OWNER)
        assert owner_ctx.satisfies(AuthorityLevel.USER)
        auth.add_user("Alice", principal_id="alice")
        alice_sess = mgr.create_session("alice")
        alice_ctx = SessionContext.from_session(alice_sess)
        assert alice_ctx.satisfies(AuthorityLevel.USER)
        assert not alice_ctx.satisfies(AuthorityLevel.OWNER)

    def test_to_dict(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        sess = mgr.create_session("owner")
        ctx = SessionContext.from_session(sess)
        d = ctx.to_dict()
        assert d["session_id"] == sess.session_id
        assert d["principal_id"] == "owner"


class TestAuthorityChecksViaSession:
    def test_owner_session_passes_owner_check(self):
        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        sess = mgr.create_session("owner")
        ctx = SessionContext.from_session(sess)
        decision = auth.check(ctx.principal_id, AuthorityLevel.OWNER)
        assert decision.allowed

    def test_user_session_fails_owner_check(self):
        auth = AuthorityService("Owner")
        auth.add_user("Alice", principal_id="alice")
        mgr = SessionManager(auth)
        sess = mgr.create_session("alice")
        ctx = SessionContext.from_session(sess)
        assert not auth.check(ctx.principal_id, AuthorityLevel.OWNER).allowed
        assert auth.check(ctx.principal_id, AuthorityLevel.USER).allowed

    def test_authority_context_from_session(self):
        auth = AuthorityService("Owner")
        auth.add_user("Alice", principal_id="alice")
        mgr = SessionManager(auth)
        sess = mgr.create_session("alice")
        ctx = SessionContext.from_session(sess, action="write")
        ac = ctx.authority_context()
        assert not ac.satisfies(AuthorityLevel.OWNER)
        assert ac.satisfies(AuthorityLevel.USER)


class TestConversationPropagation:
    def test_conversation_receives_session_scope(self):
        from unittest.mock import MagicMock

        from atlas.ai.ai_manager import AIManager
        from atlas.cognition.api import CognitionAPI
        from atlas.conversation.conversation_service import ConversationService
        from atlas.services.cognition_service import CognitionService as CogService

        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        sess = mgr.create_session("owner")
        ctx = SessionContext.from_session(sess)

        manager = AIManager()
        manager.initialize(provider="Mock Provider", model="atlas-mock-v1", timeout=300)
        mock_cog = MagicMock(spec=CogService)
        from atlas.cognition.decision import CognitionDecision

        mock_cog.process.return_value = CognitionDecision(action="respond", reasoning="r", data={})
        api = CognitionAPI(cognition_service=mock_cog)
        service = ConversationService(manager.service, cognition_api=api, session_context=ctx)
        service.send("Hello Atlas")
        assert mock_cog.process.call_args.kwargs["metadata"]["session"]["principal_id"] == "owner"
        assert mock_cog.process.call_args.kwargs["metadata"]["session"]["session_id"] == sess.session_id

    def test_per_call_session_overrides_default(self):
        from unittest.mock import MagicMock

        from atlas.ai.ai_manager import AIManager
        from atlas.cognition.api import CognitionAPI
        from atlas.conversation.conversation_service import ConversationService
        from atlas.services.cognition_service import CognitionService as CogService

        auth = AuthorityService("Owner")
        auth.add_user("Alice", principal_id="alice")
        mgr = SessionManager(auth)
        owner_sess = mgr.create_session("owner")
        alice_sess = mgr.create_session("alice")
        owner_ctx = SessionContext.from_session(owner_sess)
        alice_ctx = SessionContext.from_session(alice_sess)

        manager = AIManager()
        manager.initialize(provider="Mock Provider", model="atlas-mock-v1", timeout=300)
        mock_cog = MagicMock(spec=CogService)
        from atlas.cognition.decision import CognitionDecision

        mock_cog.process.return_value = CognitionDecision(action="respond", reasoning="r", data={})
        api = CognitionAPI(cognition_service=mock_cog)
        service = ConversationService(manager.service, cognition_api=api, session_context=owner_ctx)
        service.send("Hello", session_context=alice_ctx)
        assert mock_cog.process.call_args.kwargs["metadata"]["session"]["principal_id"] == "alice"

    def test_conversation_backward_compat_no_session(self):
        from atlas.ai.ai_manager import AIManager
        from atlas.conversation.conversation_service import ConversationService

        manager = AIManager()
        manager.initialize(provider="Mock Provider", model="atlas-mock-v1", timeout=300)
        service = ConversationService(manager.service)
        resp = service.send("Hello Atlas")
        assert resp.role == "assistant"
        assert len(resp.content) > 0

    def test_task_spec_carries_session(self):
        from unittest.mock import MagicMock

        from atlas.ai.ai_manager import AIManager
        from atlas.cognition.api import CognitionAPI
        from atlas.conversation.conversation_service import ConversationService
        from atlas.services.cognition_service import CognitionService as CogService

        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        sess = mgr.create_session("owner")
        ctx = SessionContext.from_session(sess)
        manager = AIManager()
        manager.initialize(provider="Mock Provider", model="atlas-mock-v1", timeout=300)
        mock_cog = MagicMock(spec=CogService)
        from atlas.cognition.decision import CognitionDecision

        mock_cog.process.return_value = CognitionDecision(action="respond", reasoning="r", data={})
        api = CognitionAPI(cognition_service=mock_cog)
        service = ConversationService(manager.service, cognition_api=api, session_context=ctx)
        service.send("Create a report using local data")
        task = mock_cog.process.call_args.kwargs["metadata"]["task"]
        assert task["context"]["session_id"] == sess.session_id
        assert task["context"]["principal_id"] == "owner"

    def test_bind_session(self):
        from atlas.ai.ai_manager import AIManager
        from atlas.conversation.conversation_service import ConversationService

        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        sess = mgr.create_session("owner")
        manager = AIManager()
        manager.initialize(provider="Mock Provider", model="atlas-mock-v1", timeout=300)
        service = ConversationService(manager.service)
        ctx = service.bind_session(sess)
        assert service.session_context.session_id == sess.session_id
        assert ctx.session_id == sess.session_id


class TestMemoryContextPropagation:
    def test_context_engine_records_session(self):
        from atlas.memory.context.context_engine import ContextEngine
        from atlas.memory.repository.memory_repository import MemoryRepository
        from atlas.memory.ranking.ranking_engine import RankingEngine
        from atlas.memory.search.search_engine import MemorySearchEngine
        from atlas.memory.service.memory_manager_service import MemoryManagerService

        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        sess = mgr.create_session("owner")
        ctx = SessionContext.from_session(sess)
        repo = MemoryRepository()
        ranking = RankingEngine()
        search = MemorySearchEngine(repo, ranking)
        svc = MemoryManagerService(repo, ranking, search)
        engine = ContextEngine(memory_service=svc)
        engine.build_context(query="hello", session_context=ctx)
        assert engine.last_session_context.session_id == sess.session_id
        assert svc.last_session_context.session_id == sess.session_id
        assert search.last_session_context.session_id == sess.session_id

    def test_memory_service_backward_compat(self):
        from atlas.memory.repository.memory_repository import MemoryRepository
        from atlas.memory.ranking.ranking_engine import RankingEngine
        from atlas.memory.search.search_engine import MemorySearchEngine
        from atlas.memory.service.memory_manager_service import MemoryManagerService

        repo = MemoryRepository()
        ranking = RankingEngine()
        search = MemorySearchEngine(repo, ranking)
        svc = MemoryManagerService(repo, ranking, search)
        # Old call without session_context still works.
        assert svc.search(keyword="hello") == []
        assert svc.last_session_context is None

    def test_context_manager_forwards_session(self):
        from atlas.conversation.context import ContextManager
        from atlas.conversation.conversation import Conversation
        from atlas.memory.context.context_engine import ContextEngine
        from atlas.memory.repository.memory_repository import MemoryRepository
        from atlas.memory.ranking.ranking_engine import RankingEngine
        from atlas.memory.search.search_engine import MemorySearchEngine
        from atlas.memory.service.memory_manager_service import MemoryManagerService

        auth = AuthorityService("Owner")
        mgr = SessionManager(auth)
        sess = mgr.create_session("owner")
        ctx = SessionContext.from_session(sess)
        repo = MemoryRepository()
        ranking = RankingEngine()
        search = MemorySearchEngine(repo, ranking)
        svc = MemoryManagerService(repo, ranking, search)
        engine = ContextEngine(memory_service=svc)
        cm = ContextManager(context_engine=engine)
        conv = Conversation()
        cm.build(conv, memory_query="hello", session_context=ctx)
        assert engine.last_session_context.session_id == sess.session_id


class TestKernelWiring:
    def test_kernel_establishes_owner_session(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            assert atlas.session_manager is not None
            assert atlas.session_context is not None
            assert atlas.session_context.is_owner
            assert atlas.session_context.principal_id == "owner"
            assert atlas.session_manager.count() >= 1
        finally:
            atlas.shutdown()
        assert atlas.session_manager is None
        assert atlas.session_context is None

    def test_kernel_conversation_has_owner_session(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            conv = atlas.container.get("conversation")
            assert conv.session_context is not None
            assert conv.session_context.is_owner
        finally:
            atlas.shutdown()

    def test_start_user_session(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            atlas.authority_service.add_user("Alice", principal_id="alice")
            ctx = atlas.start_user_session("alice")
            assert ctx.principal_id == "alice"
            assert not ctx.is_owner
            # Unknown principal fails closed; no session created.
            with pytest.raises(PermissionError):
                atlas.start_user_session("ghost")
        finally:
            atlas.shutdown()

    def test_set_session_context(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            atlas.authority_service.add_user("Alice", principal_id="alice")
            ctx = atlas.start_user_session("alice")
            atlas.set_session_context(ctx)
            assert atlas.session_context.principal_id == "alice"
            assert atlas.container.get("conversation").session_context.principal_id == "alice"
            atlas.set_session_context(None)
            assert atlas.session_context is None
        finally:
            atlas.shutdown()
