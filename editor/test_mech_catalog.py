"""Regression tests for campaign-only mech display metadata."""
import unittest

import mech_catalog


class CampaignMechDisplayTests(unittest.TestCase):
    def test_duncan_warhammer_names_resolve_to_heavy_70t(self):
        for asset in ("WHM-DNC_MDA", "WHM-DNC_PLAYABLE_MDA"):
            with self.subTest(asset=asset):
                self.assertEqual(mech_catalog.chassis_info(asset), (70, "Heavy"))
                self.assertEqual(
                    mech_catalog.display(asset),
                    'Warhammer "Duncan Fisher" (WHM-DNC)',
                )

    def test_campaign_variant_is_not_offered_for_add_mech(self):
        self.assertNotIn("WHM-DNC", mech_catalog.ALL_VARIANTS)


if __name__ == "__main__":
    unittest.main()
