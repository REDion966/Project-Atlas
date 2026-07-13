"""
Tests for Atlas Service Container.
"""

import unittest

from atlas.kernel.service_container import ServiceContainer


class DummyService:

    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class TestServiceContainer(unittest.TestCase):

    def setUp(self):
        self.container = ServiceContainer()

    def test_register_service(self):
        service = object()

        self.container.register("test", service)

        self.assertTrue(self.container.has("test"))

    def test_get_service(self):
        service = object()

        self.container.register("test", service)

        self.assertIs(
            self.container.get("test"),
            service,
        )

    def test_duplicate_registration_raises(self):
        service = object()

        self.container.register("test", service)

        with self.assertRaises(ValueError):
            self.container.register("test", service)

    def test_remove_service(self):
        service = object()

        self.container.register("test", service)

        self.container.remove("test")

        self.assertFalse(
            self.container.has("test")
        )

    def test_clear(self):
        self.container.register("one", object())
        self.container.register("two", object())

        self.container.clear()

        self.assertEqual(
            self.container.names(),
            [],
        )

    def test_start_all(self):
        service = DummyService()

        self.container.register("dummy", service)

        self.container.start_all()

        self.assertTrue(service.started)

    def test_stop_all(self):
        service = DummyService()

        self.container.register("dummy", service)

        self.container.stop_all()

        self.assertTrue(service.stopped)


if __name__ == "__main__":
    unittest.main()