"""Phase 3.2 — Conversation/context memory: evidence contract.

Investigation result (evidence, not aspiration): Atlas already owns the
conversation/context machinery this milestone requires, so no new subsystem was
introduced.

* ``atlas/conversation/conversation.py::Conversation`` — conversation identity
  (``id``) + ordered ``messages`` + timestamps; ``to_dict``/``from_dict``.
* ``atlas/conversation/message.py::Message`` — a conversational turn.
* ``atlas/conversation/conversation_state.py`` — immutable, per-conversation
  :class:`ConversationState` (+ ``ConversationStateManager``): structured facts
  (``current_subject``, ``current_investigation``, ``latest_result``,
  ``pending_question``, ``last_operation``, ``turn_id``) carried across turns.
* ``atlas/conversation/conversation_context.py::build_conversation_context`` —
  bounded (last 10 messages / 500 chars) read-only projection handed to later
  stages.
* ``atlas/conversation/history.py::History`` — in-process conversation registry.
* ``atlas/storage/conversation_storage.py::ConversationStorage`` — JSON,
  durable, on-demand persistence (``atlas_data/conversations/``).
* ``atlas/conversation/conversation_service.py`` — composes the above:
  ``send``/``stream`` append turns; ``_state_manager`` retains context;
  ``save``/``load``/``saved_conversations`` are the durable surface.
* ``atlas/session/`` — session/principal attribution, distinct from
  conversation identity.

These tests pin: multi-turn continuity without a model, bounded context
availability to later turns, per-conversation isolation, process-boundary
persistence of history, separation of conversation history from durable
long-term memory, and model independence.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_context import build_conversation_context
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationState
from atlas.conversation.entity_identification import EntityCatalog
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake

_REPO_ROOT = Path(__file__).resolve().parents[1]

_CATALOG = EntityCatalog.from_names(
    {"capability": ["code_inspector", "workspace_search"]}
)


class _FailingAI:
    """A service double proving the deterministic path needs no provider."""

    def chat(self, *args, **kwargs):
        raise RuntimeError("no AI available")

    def stream_chat(self, *args, **kwargs):
        def _gen():
            raise RuntimeError("no AI available")
            yield ""  # pragma: no cover

        return _gen()


def _service(catalog: EntityCatalog | None = _CATALOG) -> ConversationService:
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        entity_catalog=catalog,
    )


#: Two-process driver: ``write`` records turns and persists the conversation
#: through the Atlas-owned surface; ``read`` (a fresh interpreter) reopens the
#: persisted conversation and recovers its history.
_DRIVER = """
import sys

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake


class _FailingAI:
    def chat(self, *a, **k):
        raise RuntimeError("no AI available")

    def stream_chat(self, *a, **k):
        def _g():
            raise RuntimeError("no AI available")
            yield ""

        return _g()


service = ConversationService(
    _FailingAI(),
    task_intake=TaskIntake(),
    builtin_response=BuiltinResponseService(),
)

if sys.argv[1] == "write":
    service.conversation.title = "P32"
    service.conversation.add_message(
        Message(role="user", content="My project is called Atlas.")
    )
    service.conversation.add_message(
        Message(role="assistant", content="Noted.")
    )
    path = service.save()
    print("SAVED:" + str(path))
else:
    files = service.saved_conversations()
    assert files, "no persisted conversation found"
    loaded = service.load(files[-1])
    contents = [m.content for m in loaded.messages]
    assert contents == ["My project is called Atlas.", "Noted."], contents
    assert loaded.title == "P32"
    print("LOADED:" + str(loaded.message_count()))
"""


class TestPhase32ConversationContextEvidence:
    def test_bounded_context_projection_exposes_earlier_turns(self):
        messages = [
            Message(role="user", content="My project is called Atlas."),
            Message(role="assistant", content="Noted."),
        ]
        context = build_conversation_context(
            messages, ConversationState(current_subject="Atlas")
        )

        assert context.has_history
        assert context.total_messages == 2
        assert "My project is called Atlas." in context.recent_user_turns
        assert "Noted." in context.recent_assistant_turns
        assert context.state.current_subject == "Atlas"

    def test_multi_turn_continuity_without_a_model(self):
        service = _service()

        service.send("What does code_inspector do?")
        carried = service.state_manager.state.current_subject
        assert carried == "code_inspector"

        # A later turn consults the carried state and resolves against it.
        text = "Tell me more about it."
        spec = service._intake(text, len(service.conversation.messages))
        spec = service._apply_entity_identification(spec, text)
        out_spec, response = service._apply_reference_resolution(spec, text)

        assert out_spec.context["resolved_reference"] == {
            "field": "current_subject",
            "value": "code_inspector",
        }
        assert response is None

        # The earlier user turn is still available in the bounded projection.
        context = service._build_conversation_context()
        assert any("code_inspector" in turn for turn in context.recent_user_turns)

    def test_conversations_are_isolated(self):
        first = _service()
        second = _service()
        assert first.conversation.id != second.conversation.id

        first.send("What does code_inspector do?")
        second.send("What does workspace_search do?")

        assert first.state_manager.state.current_subject == "code_inspector"
        assert second.state_manager.state.current_subject == "workspace_search"

        # No message or state bleed between the two conversations.
        first_content = [m.content for m in first.conversation.messages]
        second_content = [m.content for m in second.conversation.messages]
        assert all("workspace_search" not in c for c in first_content)
        assert all("code_inspector" not in c for c in second_content)

    def test_conversation_history_survives_a_process_boundary(self, tmp_path):
        driver = tmp_path / "driver.py"
        driver.write_text(_DRIVER, encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT))

        proc_a = subprocess.run(
            [sys.executable, str(driver), "write"],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc_a.returncode == 0, proc_a.stderr
        assert "SAVED:" in proc_a.stdout

        # Process A has terminated; a fresh interpreter reopens the history.
        proc_b = subprocess.run(
            [sys.executable, str(driver), "read"],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc_b.returncode == 0, proc_b.stderr
        assert "LOADED:2" in proc_b.stdout

    def test_conversation_turns_are_not_auto_promoted_to_long_term_memory(self):
        source = (
            _REPO_ROOT / "atlas" / "conversation" / "conversation_service.py"
        ).read_text(encoding="utf-8")
        assert "add_memory" not in source
        assert "MemoryRepository" not in source

        from atlas.memory.storage.json_storage import Storage as MemoryStorage
        from atlas.storage.conversation_storage import ConversationStorage

        # Distinct stores: conversation history is not durable memory.
        assert str(ConversationStorage.STORAGE_DIR) != str(
            MemoryStorage.MEMORY_FILE
        )

    def test_conversation_context_path_has_no_model_or_network_imports(self):
        banned = ("openai", "anthropic", "ollama", "requests", "httpx", "urllib")
        for relative in (
            "atlas/conversation/conversation.py",
            "atlas/conversation/conversation_state.py",
            "atlas/conversation/conversation_context.py",
            "atlas/conversation/history.py",
            "atlas/storage/conversation_storage.py",
        ):
            tree = ast.parse((_REPO_ROOT / relative).read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            for module in imported:
                assert not module.startswith(banned), f"{relative} imports {module}"
