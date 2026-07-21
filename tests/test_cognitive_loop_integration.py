import unittest

from atlas.kernel.atlas import Atlas
from atlas.intelligence.cognitive_loop import CognitiveLoop


class TestCognitiveLoopIntegration(unittest.TestCase):

    def test_cognitive_loop_uses_atlas_services(self):

        atlas = Atlas()

        atlas.start()

        loop = CognitiveLoop(
            memory_service=atlas.container.resolve("memory"),
            knowledge_manager=atlas.container.resolve("knowledge"),
        )

        result = loop.process(
            "Learn Atlas architecture"
        )

        self.assertIsNotNone(result)

        atlas.shutdown()


if __name__ == "__main__":
    unittest.main()
