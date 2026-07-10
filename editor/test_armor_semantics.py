"""Regression tests for current / installed / MDA max armor semantics."""
import unittest

import stock_templates
from savefile import ARMOR_PARTS, REAR_PARTS, Mech


class ArmorHarness(Mech):
    def __init__(self):
        self.current = {loc: 1.0 for loc in ARMOR_PARTS + REAR_PARTS}
        self.installed = {loc: float(i + 10) for i, loc in enumerate(ARMOR_PARTS + REAR_PARTS)}

    def armor_value(self, location: str, installed: bool = False) -> float:
        return (self.installed if installed else self.current)[location]

    def set_armor(self, location: str, value: float, installed: bool = False):
        (self.installed if installed else self.current)[location] = value


class ArmorSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.old_data = stock_templates._DATA

    def tearDown(self):
        stock_templates._DATA = self.old_data

    def test_max_armor_caps_are_separate_template_metadata(self):
        caps = {"Head": 30.0, "CenterTorso": 124.0, "LeftLeg": 84.0}
        stock_templates._DATA = {
            "MAD-4A_MDA": {
                "armor": {"Head": 18.0, "CenterTorso": 90.0, "LeftLeg": 82.0},
                "maxArmor": caps,
            }
        }
        self.assertEqual(stock_templates.max_armor_caps("MAD-4A"), caps)
        self.assertEqual(stock_templates._DATA["MAD-4A_MDA"]["armor"]["LeftLeg"], 82.0)
        self.assertEqual(stock_templates.max_armor_caps("MAD-4A")["LeftLeg"], 84.0)

    def test_legacy_template_without_max_armor_has_no_caps(self):
        stock_templates._DATA = {"MAD-4A_MDA": {"armor": {"Head": 18.0}}}
        self.assertIsNone(stock_templates.max_armor_caps("MAD-4A"))

    def test_repair_armor_restores_current_to_installed_without_changing_installed(self):
        mech = ArmorHarness()
        before = dict(mech.installed)
        mech.repair_armor()
        self.assertEqual(mech.current, before)
        self.assertEqual(mech.installed, before)

    def test_historical_max_armor_alias_keeps_repair_semantics(self):
        mech = ArmorHarness()
        before = dict(mech.installed)
        mech.max_armor()
        self.assertEqual(mech.current, before)
        self.assertEqual(mech.installed, before)


if __name__ == "__main__":
    unittest.main()
