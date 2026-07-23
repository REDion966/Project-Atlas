import unittest

from atlas.kernel.atlas import Atlas
from atlas.intelligence.cognitive_loop import CognitiveLoop
from atlas.intelligence.cognitive_service import CognitiveService as IntelligenceCognitiveService
from atlas.services.cognition_service import CognitionService


class TestCognitionService(unittest.TestCase):

    def test_cognition_service_registered(self):

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
            IntelligenceCognitiveService,
        )

        atlas.shutdown()

    def test_cognition_service_new_registered(self):

        atlas = Atlas()

        atlas.start()

        service = atlas.container.get(
            "cognition_service"
        )

        self.assertIsNotNone(
            service
        )

        self.assertIsInstance(
            service,
            CognitionService,
        )

        self.assertTrue(
            service.is_running()
        )

        atlas.shutdown()

    def test_cognition_service_new_process(self):

        atlas = Atlas()

        atlas.start()

        service = atlas.container.get(
            "cognition_service"
        )

        result = service.process(
            "Test cognition"
        )

        self.assertEqual(
            result.action,
            "respond",
        )

        self.assertEqual(
            result.data["input"],
            "Test cognition",
        )

        atlas.shutdown()


if __name__ == "__main__":
    unittest.main()