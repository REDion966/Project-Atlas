"""
Tests for new Atlas Cognition Service.
"""

import unittest

from atlas.services.cognition_service import CognitionService


class TestNewCognitionService(unittest.TestCase):

    def setUp(self):

        self.service = CognitionService()


    def test_service_starts(self):

        self.service.start()

        self.assertTrue(
            self.service.running
        )


    def test_process_returns_decision(self):

        self.service.start()

        result = self.service.process(
            "Test input"
        )

        self.assertEqual(
            result.action,
            "respond",
        )


    def test_process_without_start_fails(self):

        with self.assertRaises(
            RuntimeError
        ):
            self.service.process(
                "Test"
            )