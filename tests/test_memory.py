"""
Tests for the Atlas Memory Manager.
"""

import unittest

from atlas.memory.memory_manager import MemoryManager


class TestMemoryManager(unittest.TestCase):
    """Test Atlas memory operations."""

    def test_reset_memory(self):
        """Memory should reset to default structure."""

        MemoryManager.reset()

        memory = MemoryManager.get_memory()

        self.assertIn("identity", memory)
        self.assertIn("users", memory)
        self.assertIn("projects", memory)
        self.assertIn("knowledge", memory)
        self.assertIn("settings", memory)
        self.assertIn("system", memory)

    def test_save_memory(self):
        """Memory should save values correctly."""

        MemoryManager.reset()

        MemoryManager.save_memory({
            "identity": {
                "name": "Atlas"
            }
        })

        memory = MemoryManager.get_memory()

        self.assertEqual(
            memory["identity"]["name"],
            "Atlas"
        )


if __name__ == "__main__":
    unittest.main()