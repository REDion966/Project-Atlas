import unittest

from atlas.kernel.atlas import Atlas


class TestKernel(unittest.TestCase):

    def test_create_atlas(self):
        atlas = Atlas()

        self.assertIsNotNone(atlas)


if __name__ == "__main__":
    unittest.main()