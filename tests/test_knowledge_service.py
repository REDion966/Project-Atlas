import unittest

from atlas.kernel.atlas import Atlas


class TestKnowledgeService(unittest.TestCase):

    def test_knowledge_service_registered(self):

        atlas = Atlas()

        atlas.start()

        knowledge = atlas.container.resolve("knowledge")

        self.assertIsNotNone(
            knowledge
        )

        atlas.shutdown()


    def test_knowledge_can_remember_and_query(self):

        atlas = Atlas()

        atlas.start()

        knowledge = atlas.container.resolve("knowledge")

        knowledge.remember(
            title="Atlas Test Knowledge",
            content="Atlas is a modular AI operating system.",
            source="test",
        )

        result = knowledge.query(
            "AI operating system"
        )

        self.assertTrue(
            len(result) > 0
        )

        atlas.shutdown()


if __name__ == "__main__":
    unittest.main()
