"""Tests for the Cognition API layer (Phase 5.5)."""

import unittest
from unittest.mock import MagicMock

from atlas.kernel.atlas import Atlas
from atlas.cognition.api import CognitionAPI
from atlas.cognition.decision import CognitionDecision
from atlas.services.cognition_service import CognitionService


class TestCognitiveAPI(unittest.TestCase):

    def test_cognitive_available_from_atlas(self):
        """Legacy test: cognitive loop is available from atlas."""

        atlas = Atlas()

        atlas.start()

        self.assertIsNotNone(
            atlas.cognitive
        )

        atlas.shutdown()


class TestCognitionAPI(unittest.TestCase):
    """Tests for the CognitionAPI public boundary."""

    def test_api_delegates_to_cognition_service(self):
        """CognitionAPI.process delegates to CognitionService and returns CognitionDecision."""

        service = MagicMock(spec=CognitionService)
        service.process.return_value = CognitionDecision(
            action="respond",
            reasoning="test reasoning",
            data={"input": "hello"},
        )

        api = CognitionAPI(cognition_service=service)
        result = api.process("hello")

        service.process.assert_called_once_with(
            user_input="hello",
            memory=None,
            metadata=None,
            goal=None,
        )
        self.assertIsInstance(result, CognitionDecision)
        self.assertEqual(result.action, "respond")
        self.assertEqual(result.reasoning, "test reasoning")
        self.assertEqual(result.data["input"], "hello")

    def test_api_delegates_with_all_optional_args(self):
        """CognitionAPI passes all optional arguments through to service."""

        service = MagicMock(spec=CognitionService)
        service.process.return_value = CognitionDecision(
            action="query",
            reasoning="lookup",
        )

        api = CognitionAPI(cognition_service=service)
        result = api.process(
            user_input="find data",
            memory=["mem1"],
            metadata={"key": "val"},
            goal="retrieve",
        )

        service.process.assert_called_once_with(
            user_input="find data",
            memory=["mem1"],
            metadata={"key": "val"},
            goal="retrieve",
        )
        self.assertEqual(result.action, "query")

    def test_api_contains_no_reasoning_logic(self):
        """CognitionAPI is a pure delegate with no reasoning logic."""

        service = MagicMock(spec=CognitionService)
        api = CognitionAPI(cognition_service=service)

        # Verify API has no extra reasoning methods/attributes
        attrs = [a for a in dir(api) if not a.startswith("_")]
        self.assertEqual(attrs, ["process"])

        # Verify process method just calls service.process and returns result
        intermediate = MagicMock()
        service.process.return_value = intermediate
        result = api.process("test")
        self.assertIs(result, intermediate)

    def test_api_initialization_with_service(self):
        """CognitionAPI can be constructed with a service and delegates to it."""

        service = MagicMock(spec=CognitionService)
        service.process.return_value = CognitionDecision(
            action="respond",
        )

        api = CognitionAPI(cognition_service=service)
        result = api.process("init test")

        service.process.assert_called_once_with(
            user_input="init test",
            memory=None,
            metadata=None,
            goal=None,
        )
        self.assertEqual(result.action, "respond")


class TestCognitionAPIKernelRegistration(unittest.TestCase):
    """Tests that CognitionAPI is registered in the Atlas kernel."""

    def test_cognition_api_registered_in_container(self):
        """cognition_api is registered in the service container after start."""

        atlas = Atlas()

        atlas.start()

        api = atlas.container.get("cognition_api")

        self.assertIsNotNone(api)
        self.assertIsInstance(api, CognitionAPI)
        self.assertIs(api, atlas.cognition_api)

        atlas.shutdown()

    def test_cognition_api_accessible_from_atlas(self):
        """CognitionAPI is accessible via atlas.cognition_api property."""

        atlas = Atlas()

        atlas.start()

        api = atlas.cognition_api

        self.assertIsNotNone(api)
        self.assertIsInstance(api, CognitionAPI)

        atlas.shutdown()

    def test_existing_service_keys_preserved(self):
        """All existing service keys remain registered."""

        atlas = Atlas()

        atlas.start()

        self.assertTrue(atlas.container.has("cognition"))
        self.assertTrue(atlas.container.has("cognitive"))
        self.assertTrue(atlas.container.has("cognition_service"))
        self.assertTrue(atlas.container.has("cognition_api"))

        atlas.shutdown()

    def test_cognition_api_delegates_from_kernel(self):
        """CognitionAPI retrieved from kernel delegates to CognitionService."""

        atlas = Atlas()

        atlas.start()

        api = atlas.cognition_api

        result = api.process("kernel test")

        self.assertIsInstance(result, CognitionDecision)
        self.assertEqual(result.action, "respond")
        self.assertEqual(result.data["input"], "kernel test")

        atlas.shutdown()


if __name__ == "__main__":
    unittest.main()