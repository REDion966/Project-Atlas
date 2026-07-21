import unittest

from atlas.kernel.atlas import Atlas
from atlas.intelligence.cognitive_loop import CognitiveLoop


class TestCognitionService(unittest.TestCase):

    def test_cognitive_service_registered(self):

        atlas = Atlas()

        atlas.start()

        cognition = atlas.container.get(
            "cognition"
        )

        self.assertIsNotNone(
            cognition
        )

        self.assertIsInstance(
            cognition,
            CognitiveLoop,
        )

        atlas.shutdown()


if __name__ == "__main__":
    unittest.main()