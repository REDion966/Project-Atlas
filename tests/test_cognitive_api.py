import unittest

from atlas.kernel.atlas import Atlas


class TestCognitiveAPI(unittest.TestCase):

    def test_cognitive_available_from_atlas(self):

        atlas = Atlas()

        atlas.start()

        self.assertIsNotNone(
            atlas.cognitive
        )

        atlas.shutdown()


if __name__ == "__main__":
    unittest.main()