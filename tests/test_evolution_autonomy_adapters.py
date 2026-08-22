"""Tests for the production StateReader/StateWriter adapters (Batch 9).

Covers:
- memory adapter   (read / has / write / remove / idempotent / namespace)
- knowledge adapter (read / has / write / idempotent / remove fail-closed)
- config adapter    (read / has / write+remove fail-closed)
- capability adapter (read / has / write / remove / governance controls)

Isolation:
- memory tests patch ``Storage.MEMORY_FILE``/``DATA_DIR`` to a temp dir
- config tests build the adapter over a temp TOML file
- knowledge/capability are pure in-memory and safe
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from atlas.config.configuration import Configuration
from atlas.evolution.autonomy.adapters import (
    CapabilityStateAdapter,
    ConfigStateAdapter,
    KnowledgeStateAdapter,
    MemoryStateAdapter,
)
from atlas.evolution.autonomy.adapters.config_adapter import (
    ConfigWriteUnsupportedError,
)
from atlas.evolution.autonomy.adapters.knowledge_adapter import (
    StateRemoveUnsupportedError,
)
from atlas.knowledge.knowledge_entry import KnowledgeEntry
from atlas.knowledge.knowledge_manager import KnowledgeManager
from atlas.memory.enums import MemoryImportance, MemoryType
from atlas.memory.models.memory import Memory
from atlas.memory.repository.memory_repository import MemoryRepository
from atlas.memory.service.memory_manager_service import MemoryManagerService
from atlas.reasoning.execution.registry import CapabilityRegistry


class _Handler:
    """Minimal callable capability handler."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, ctx=None):
        return {"ok": self.name}


def _make_memory_service(tmp_dir: Path) -> MemoryManagerService:
    """Build a MemoryManagerService isolated to ``tmp_dir``."""
    from atlas.memory.ranking.ranking_engine import RankingEngine
    from atlas.memory.search.search_engine import MemorySearchEngine
    from atlas.memory.storage.json_storage import Storage

    # Patch the storage paths so tests never touch real data/memory.json.
    Storage.MEMORY_FILE = tmp_dir / "memory.json"
    Storage.DATA_DIR = tmp_dir
    repository = MemoryRepository()
    ranking = RankingEngine()
    search = MemorySearchEngine(repository, ranking)
    return MemoryManagerService(
        repository=repository,
        ranking_engine=ranking,
        search_engine=search,
    )


def _write_config_file(tmp_dir: Path) -> Path:
    """Write a minimal config.toml and return its path."""
    path = tmp_dir / "config.toml"
    path.write_text(
        "[application]\n"
        'name = "Atlas Test"\n'
        'version = "0.0.0"\n'
        "\n"
        "[ai]\n"
        'provider = "mock"\n'
        'model = "atlas-mock-v1"\n'
        "temperature = 0.1\n"
        "timeout = 5\n"
        "\n"
        "[conversation]\n"
        "history_limit = 20\n"
        "\n"
        "[logging]\n"
        'level = "INFO"\n'
        "\n"
        "[api_keys]\n"
        'openai = ""\n'
        'anthropic = ""\n',
        encoding="utf-8",
    )
    return path


def _make_configuration(tmp_dir: Path) -> Configuration:
    path = _write_config_file(tmp_dir)
    config = Configuration(filename=str(path))
    config.load()
    return config


class TestMemoryStateAdapter(unittest.TestCase):
    """Memory adapter: read/has/write/remove/idempotency against a temp store."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="atlas_adapters_mem_"))
        self.adapter = MemoryStateAdapter(_make_memory_service(self.tmp_dir))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_missing_key_read_default(self):
        self.assertIsNone(self.adapter.read("memory.missing"))
        self.assertEqual(self.adapter.read("memory.missing", "dflt"), "dflt")

    def test_has_false_when_missing(self):
        self.assertFalse(self.adapter.has("memory.nope"))

    def test_write_dict_and_read_back(self):
        self.adapter.write(
            "memory.M1",
            {"title": "T1", "content": "hello"},
        )
        self.assertTrue(self.adapter.has("memory.M1"))
        memory = self.adapter.read("memory.M1")
        self.assertIsInstance(memory, Memory)
        self.assertEqual(memory.id, "M1")
        self.assertEqual(memory.title, "T1")
        self.assertEqual(memory.content, "hello")
        self.assertEqual(memory.source, "governed_evolution")

    def test_write_memory_instance_round_trip(self):
        memory = Memory(
            id="M2",
            title="T2",
            content="body",
            memory_type=MemoryType.KNOWLEDGE,
            importance=MemoryImportance.HIGH,
            tags=["a", "b"],
            source="research",
        )
        self.adapter.write("M2", memory)  # bare key also accepted
        loaded = self.adapter.read("memory.M2")
        self.assertEqual(loaded.title, "T2")
        self.assertEqual(loaded.memory_type, MemoryType.KNOWLEDGE)
        self.assertEqual(loaded.importance, MemoryImportance.HIGH)
        self.assertEqual(loaded.tags, ["a", "b"])
        self.assertEqual(loaded.source, "research")

    def test_idempotent_repeated_write(self):
        self.adapter.write("memory.M3", {"title": "T3", "content": "v1"})
        self.adapter.write("memory.M3", {"title": "T3", "content": "v2"})
        loaded = self.adapter.read("memory.M3")
        self.assertEqual(loaded.content, "v2")
        all_mem = self.adapter._memory_service.list_memories()
        self.assertEqual([m.id for m in all_mem].count("M3"), 1)

    def test_remove_and_result(self):
        self.adapter.write("memory.M4", {"title": "T4", "content": "x"})
        self.assertTrue(self.adapter.remove("memory.M4"))
        self.assertFalse(self.adapter.has("memory.M4"))
        self.assertFalse(self.adapter.remove("memory.M4"))

    def test_write_rejects_unsupported_type(self):
        with self.assertRaises(TypeError):
            self.adapter.write("memory.M5", 42)


class TestKnowledgeStateAdapter(unittest.TestCase):
    """Knowledge adapter: read/has/write/idempotency; remove fails closed."""

    def setUp(self) -> None:
        self.adapter = KnowledgeStateAdapter(KnowledgeManager())

    def test_missing_key_read_default(self):
        self.assertIsNone(self.adapter.read("knowledge.absent"))
        self.assertEqual(self.adapter.read("knowledge.absent", 7), 7)

    def test_write_dict_and_read_back(self):
        self.adapter.write(
            "knowledge.Fact One",
            {"content": "the content", "source": "research"},
        )
        self.assertTrue(self.adapter.has("knowledge.Fact One"))
        entry = self.adapter.read("knowledge.Fact One")
        self.assertIsInstance(entry, KnowledgeEntry)
        self.assertEqual(entry.title, "Fact One")
        self.assertEqual(entry.content, "the content")
        self.assertEqual(entry.source, "research")

    def test_write_entry_instance(self):
        entry = KnowledgeEntry(title="Fact Two", content="c", source="s")
        self.adapter.write("Fact Two", entry)  # bare key accepted
        loaded = self.adapter.read("knowledge.Fact Two")
        self.assertEqual(loaded.content, "c")

    def test_idempotent_repeated_write(self):
        self.adapter.write("knowledge.Fact Three", {"content": "v1"})
        self.adapter.write("knowledge.Fact Three", {"content": "v2"})
        entries = self.adapter._knowledge_manager.base.all()
        matches = [e for e in entries if e.title == "Fact Three"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].content, "v1")  # first write wins (no-op)

    def test_remove_fails_closed(self):
        self.adapter.write("knowledge.Fact Four", {"content": "x"})
        with self.assertRaises(StateRemoveUnsupportedError):
            self.adapter.remove("knowledge.Fact Four")

    def test_write_rejects_unsupported_type(self):
        with self.assertRaises(TypeError):
            self.adapter.write("knowledge.Bad", 99)


class TestConfigStateAdapter(unittest.TestCase):
    """Config adapter: read-only; writes/removes fail closed by design."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="atlas_adapters_cfg_"))
        self.adapter = ConfigStateAdapter(_make_configuration(self.tmp_dir))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_read_namespaced_key(self):
        self.assertEqual(self.adapter.read("config.ai.provider"), "mock")
        self.assertEqual(self.adapter.read("config.application.name"), "Atlas Test")
        self.assertEqual(self.adapter.read("config.conversation.history_limit"), 20)

    def test_read_bare_dotted_key(self):
        self.assertEqual(self.adapter.read("ai.provider"), "mock")

    def test_read_default_on_missing(self):
        self.assertIsNone(self.adapter.read("config.unknown.thing"))
        self.assertEqual(self.adapter.read("config.unknown.thing", "d"), "d")

    def test_has(self):
        self.assertTrue(self.adapter.has("config.ai.provider"))
        self.assertFalse(self.adapter.has("config.nope.nope"))

    def test_write_fails_closed(self):
        with self.assertRaises(ConfigWriteUnsupportedError):
            self.adapter.write("config.ai.provider", "other")

    def test_remove_fails_closed(self):
        with self.assertRaises(ConfigWriteUnsupportedError):
            self.adapter.remove("config.ai.provider")


class TestCapabilityStateAdapter(unittest.TestCase):
    """Capability adapter: read/has/write/remove + registry governance rules."""

    def setUp(self) -> None:
        self.adapter = CapabilityStateAdapter(CapabilityRegistry())

    def test_missing_key_read_default(self):
        self.assertIsNone(self.adapter.read("capability.nope"))
        self.assertEqual(self.adapter.read("capability.nope", "d"), "d")

    def test_write_and_read_back(self):
        handler = _Handler("h1")
        self.adapter.write("capability.my_cap", handler)
        self.assertTrue(self.adapter.has("capability.my_cap"))
        self.assertIs(self.adapter.read("capability.my_cap"), handler)

    def test_remove_and_result(self):
        self.adapter.write("capability.my_cap", _Handler("h2"))
        self.assertTrue(self.adapter.remove("capability.my_cap"))
        self.assertFalse(self.adapter.has("capability.my_cap"))
        self.assertFalse(self.adapter.remove("capability.my_cap"))

    def test_duplicate_write_raises_value_error(self):
        self.adapter.write("capability.dup", _Handler("a"))
        with self.assertRaises(ValueError):
            self.adapter.write("capability.dup", _Handler("b"))

    def test_write_rejects_non_callable(self):
        with self.assertRaises(TypeError):
            self.adapter.write("capability.bad", {"upgrade_kind": "register"})


if __name__ == "__main__":
    unittest.main()
