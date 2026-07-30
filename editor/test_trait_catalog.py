"""Regression tests for trait dropdown display, sorting, and resolution."""
import unittest

from trait_catalog import display, dropdown_values, resolve


class TraitDropdownTests(unittest.TestCase):
    def test_labeled_traits_show_friendly_name_first(self):
        self.assertEqual(
            display("Specialist_Laser_PilotTrait", "Laser Specialist"),
            "Laser Specialist -- Specialist_Laser_PilotTrait",
        )

    def test_labeled_traits_sort_before_unknown_assets(self):
        values = dropdown_values(
            ["ZZZ_ModTrait", "AAA_ModTrait", "Known_Asset"],
            [
                ("Known_Asset", "Beta Friendly"),
                ("Another_Asset", "Alpha Friendly"),
            ],
        )
        self.assertEqual(
            values,
            [
                "Alpha Friendly -- Another_Asset",
                "Beta Friendly -- Known_Asset",
                "AAA_ModTrait",
                "ZZZ_ModTrait",
            ],
        )

    def test_empty_labels_are_treated_as_unknown(self):
        self.assertEqual(
            dropdown_values(["ModdedTrait"], [("CatalogTrait", "")]),
            ["CatalogTrait", "ModdedTrait"],
        )

    def test_display_and_raw_values_resolve_to_asset_names(self):
        self.assertEqual(
            resolve("Laser Specialist -- Specialist_Laser_PilotTrait"),
            "Specialist_Laser_PilotTrait",
        )
        self.assertEqual(resolve("ModdedTrait"), "ModdedTrait")


if __name__ == "__main__":
    unittest.main()
