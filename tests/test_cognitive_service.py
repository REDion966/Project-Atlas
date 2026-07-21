import unittest

from atlas.kernel.atlas import Atlas
from atlas.intelligence.cognitive_service import CognitiveService


class TestCognitiveService(unittest.TestCase):

    def test_cognitive_service_registered(self):

        atlas = Atlas()

        atlas.start()

        service = atlas.container.get(
            "cognitive"
        )

        self.assertIsNotNone(
            service
        )

        self.assertIsInstance(
            service,
            CognitiveService,
        )

        atlas.shutdown()


    def test_cognitive_service_process(self):

        atlas = Atlas()

        atlas.start()

        service = atlas.container.get(
            "cognitive"
        )

        result = service.process(
            "Understand Atlas architecture"
        )

        self.assertIsNotNone(
            result
        )

        atlas.shutdown()


if __name__ == "__main__":
    unittest.main()