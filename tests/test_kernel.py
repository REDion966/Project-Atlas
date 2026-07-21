import unittest

from atlas.kernel.atlas import Atlas


class TestKernel(unittest.TestCase):

    def test_create_atlas(self):
        atlas = Atlas()

        self.assertIsNotNone(atlas)

    def test_memory_service_registered_after_start(self):
        atlas = Atlas()
        atlas.start()

        self.assertTrue(atlas.container.has("memory"))

        atlas.shutdown()

    def test_memory_service_available_via_container(self):
        atlas = Atlas()
        atlas.start()

        memory_service = atlas.container.get("memory")

        self.assertIsNotNone(memory_service)

        atlas.shutdown()

    def test_memory_service_cleaned_after_shutdown(self):
        atlas = Atlas()

        atlas.start()
        atlas.shutdown()

        self.assertFalse(
            atlas.container.has("memory")
        )

        self.assertFalse(
            atlas.started
        )

    def test_kernel_registers_knowledge_service(self):
        atlas = Atlas()

        atlas.start()

        knowledge = atlas.container.get("knowledge")

        self.assertIsNotNone(
            knowledge
        )

        atlas.shutdown()


if __name__ == "__main__":
    unittest.main()