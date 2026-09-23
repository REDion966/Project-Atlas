"""Phase 3.8 — Memory/knowledge independence from external AI models.

Investigation result (evidence, not aspiration): every Phase 3 memory/knowledge
path is deterministic and requires no external AI model. Optional model seams
exist but are opt-in, fail-soft, and non-authoritative. No production change was
needed to establish independence.

Verification approach (beyond a single import scan):

* static — no provider SDK / network client imports on the Phase 3 core modules;
* runtime (unit) — memory persistence, conversation/context, research
  extraction/validation run with a failing provider double;
* runtime (kernel) — a started Atlas with the AI chat path instrumented to
  raise still serves self-knowledge and validated-knowledge retrieval.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.entity_identification import EntityCatalog
from atlas.conversation.task_intake import TaskIntake
from atlas.memory.models.memory import Memory
from atlas.memory.repository.memory_repository import MemoryRepository
from atlas.memory.storage.json_storage import Storage
from atlas.research.extractor import KnowledgeExtractor
from atlas.research.models import SourceKind, SourceProfile
from atlas.research.verifier import ClaimVerifier

_REPO_ROOT = Path(__file__).resolve().parents[1]

_PHASE3_MODULES = (
    "atlas/memory/storage/json_storage.py",
    "atlas/memory/repository/memory_repository.py",
    "atlas/memory/service/memory_manager_service.py",
    "atlas/memory/models/memory.py",
    "atlas/conversation/conversation.py",
    "atlas/conversation/conversation_state.py",
    "atlas/conversation/conversation_context.py",
    "atlas/conversation/history.py",
    "atlas/storage/conversation_storage.py",
    "atlas/self_knowledge/architecture_model.py",
    "atlas/self_knowledge/capability_model.py",
    "atlas/research/repository_map.py",
    "atlas/research/validated_retrieval.py",
    "atlas/research/coordinator.py",
    "atlas/research/extractor.py",
    "atlas/research/verifier.py",
    "atlas/research/planner.py",
    "atlas/research/source_selection.py",
    "atlas/experience/models.py",
    "atlas/experience/experience_repository.py",
    "atlas/experience/experience_accumulator.py",
    "atlas/experience/serialization.py",
    "atlas/evolution/decision_intelligence.py",
    "atlas/evolution/knowledge/query.py",
    "atlas/storage/experience_storage.py",
    "atlas/storage/research_storage.py",
)


class _FailingAI:
    def chat(self, *args, **kwargs):
        raise RuntimeError("no external model available")

    def stream_chat(self, *args, **kwargs):
        def _gen():
            raise RuntimeError("no external model available")
            yield ""  # pragma: no cover

        return _gen()


class TestPhase38ModelIndependence:
    def test_phase3_core_modules_have_no_provider_or_network_imports(self):
        banned = ("openai", "anthropic", "ollama", "requests", "httpx")
        for relative in _PHASE3_MODULES:
            tree = ast.parse((_REPO_ROOT / relative).read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            for module in imported:
                assert not module.startswith(banned), f"{relative} imports {module}"

    def test_persistent_memory_works_without_a_model(self, tmp_path):
        with patch.object(Storage, "MEMORY_FILE", tmp_path / "memory.json"):
            repo = MemoryRepository()
            repo.add(Memory(id="m-p38", title="T", content="C", source="test"))
            loaded = repo.get("m-p38")
            assert loaded is not None and loaded.content == "C"

    def test_conversation_context_works_with_a_failing_provider(self):
        catalog = EntityCatalog.from_names({"capability": ["code_inspector"]})
        service = ConversationService(
            _FailingAI(),
            task_intake=TaskIntake(),
            builtin_response=BuiltinResponseService(),
            entity_catalog=catalog,
        )
        # The deterministic floor answers without any provider call.
        message = service.send("what can you do?")
        assert message is not None and message.content
        # Multi-turn context retention also works with no provider.
        service.send("What does code_inspector do?")
        assert service.state_manager.state.current_subject == "code_inspector"

    def test_research_seams_are_optional_and_fail_soft(self):
        profile = SourceProfile(
            uri="https://example.com/doc",
            kind=SourceKind.WEB,
            text="External fact one. External fact two.",
        )

        class _RaisingModel:
            def complete(self, prompt):
                raise RuntimeError("model unavailable")

        # A raising optional model must not break extraction: it fails soft to
        # the deterministic sentence path.
        extractor = KnowledgeExtractor(model=_RaisingModel())
        claims = extractor.extract(profile)
        assert claims
        assert extractor._last_extraction_origin == "deterministic"

        # Verification requires no model at all.
        verifications = ClaimVerifier().verify(claims, [profile])
        assert len(verifications) == len(claims)


@pytest.fixture
def _kernel(monkeypatch, tmp_path):
    import atlas.kernel.atlas as kernel_mod
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class _Tmp(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107
            super().__init__(db_path=tmp_path / "evolution.db")

    monkeypatch.setattr(kernel_mod, "SQLiteEvolutionStorage", _Tmp)
    atlas = kernel_mod.Atlas()
    atlas.start()
    yield atlas
    atlas.shutdown()


class TestPhase38KernelIndependence:
    def test_kernel_phase3_surfaces_work_with_a_disabled_provider(
        self, _kernel, monkeypatch
    ):
        atlas = _kernel

        def _boom(*_a, **_k):
            raise AssertionError("external model contacted on a Phase 3 path")

        monkeypatch.setattr(atlas._ai_manager.service, "chat", _boom, raising=False)
        monkeypatch.setattr(
            atlas._ai_manager.service, "complete", _boom, raising=False
        )

        # Persistent memory (read path), self-knowledge, and validated-knowledge
        # retrieval all function with the provider disabled.
        assert isinstance(atlas._memory_service.list_memories(), list)
        assert atlas.architecture_model().component_count > 0
        assert atlas.capability_model().component_count > 0

        message = atlas.builtin_response.respond("What does Atlas do?")
        assert (message.metadata or {}).get("builtin_intent") == "self_description"

        result = atlas.validated_knowledge("anything")
        assert hasattr(result, "status")
