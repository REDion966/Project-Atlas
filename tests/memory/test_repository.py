"""
Tests for Atlas Memory Manager.
"""

import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from atlas.memory.enums import MemoryImportance
from atlas.memory.manager import MemoryManager
from atlas.memory.models.memory import Memory
from atlas.memory.storage.json_storage import Storage


class TestMemoryManager(unittest.TestCase):

    def setUp(self):
        # Isolate each test with a temporary storage file to prevent
        # state contamination via the shared data/memory.json.
        self._temp_dir = tempfile.TemporaryDirectory()
        self._storage_patcher = patch.object(
            Storage,
            "MEMORY_FILE",
            Path(self._temp_dir.name) / "memory.json",
        )
        self._storage_patcher.start()
        self.manager = MemoryManager()

    def tearDown(self):
        self._storage_patcher.stop()
        self._temp_dir.cleanup()

    def test_add_and_get_memory(self):
        memory = Memory(
            id=str(uuid4()),
            title="Atlas Test",
            content="Testing Atlas Memory",
        )

        self.manager.add_memory(memory)

        loaded = self.manager.get_memory(memory.id)

        self.assertEqual(memory.id, loaded.id)

    def test_update_memory(self):
        memory = Memory(
            id=str(uuid4()),
            title="Old",
            content="Old Content",
        )

        self.manager.add_memory(memory)

        memory.title = "New"

        self.manager.update_memory(memory)

        loaded = self.manager.get_memory(memory.id)

        self.assertEqual(
            loaded.title,
            "New",
        )

    def test_delete_memory(self):
        memory = Memory(
            id=str(uuid4()),
            title="Delete",
            content="Delete",
        )

        self.manager.add_memory(memory)

        self.assertTrue(
            self.manager.delete_memory(memory.id)
        )

    def test_search_memory(self):
        memory = Memory(
            id=str(uuid4()),
            title="Python",
            content="Atlas uses Python",
        )

        self.manager.add_memory(memory)

        results = self.manager.search("python")

        self.assertGreaterEqual(len(results), 1)

    def test_filter_by_tag(self):
        memory = Memory(
            id=str(uuid4()),
            title="Python",
            content="Atlas Memory",
            tags=["python", "atlas"],
        )

        self.manager.add_memory(memory)

        results = self.manager.filter_by_tag("python")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, memory.id)

    def test_filter_by_importance(self):
        memory = Memory(
            id=str(uuid4()),
            title="Critical",
            content="Important memory",
            importance=MemoryImportance.HIGH,
        )

        self.manager.add_memory(memory)

        results = self.manager.filter_by_importance(
            MemoryImportance.HIGH,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0].importance,
            MemoryImportance.HIGH,
        )

    def test_sort_by_importance(self):
        low = Memory(
            id=str(uuid4()),
            title="Low",
            content="Low",
            importance=MemoryImportance.LOW,
        )

        high = Memory(
            id=str(uuid4()),
            title="High",
            content="High",
            importance=MemoryImportance.CRITICAL,
        )

        self.manager.add_memory(low)
        self.manager.add_memory(high)

        results = self.manager.sort_by_importance()

        self.assertEqual(
            results[0].importance,
            MemoryImportance.CRITICAL,
        )

    def test_sort_by_newest(self):
        results = self.manager.sort_by_newest()

        self.assertIsInstance(results, list)

    def test_sort_by_oldest(self):
        results = self.manager.sort_by_oldest()

        self.assertIsInstance(results, list)


if __name__ == "__main__":
    unittest.main()
