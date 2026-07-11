"""Regression tests for Scarab version compatibility helpers."""
import unittest

import scarab_integration


class ScarabVersionTests(unittest.TestCase):
    def test_release_and_newer_versions_are_parsed(self):
        self.assertEqual(scarab_integration._version_tuple("scarab 1.7.4"), (1, 7, 4))
        self.assertGreater(
            scarab_integration._version_tuple("scarab v1.7.5"),
            scarab_integration._version_tuple(scarab_integration.MINIMUM_SCARAB),
        )

    def test_older_and_unknown_versions_are_distinct(self):
        self.assertLess(
            scarab_integration._version_tuple("scarab 1.7.3"),
            scarab_integration._version_tuple(scarab_integration.MINIMUM_SCARAB),
        )
        self.assertIsNone(scarab_integration._version_tuple("not a version"))


if __name__ == "__main__":
    unittest.main()
