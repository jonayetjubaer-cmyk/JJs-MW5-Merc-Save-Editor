"""Regression tests for loadout body-location grouping and layout."""
import unittest

from gui import (
    ARM_EQUIPMENT_SECTION,
    BODY_LOCATION_POS,
    LOCATION_LABEL,
    LOCATION_ORDER,
    weapon_slot_location,
    weapon_slot_location_label,
    weapon_slot_placement,
)


class WeaponSlotLocationTests(unittest.TestCase):
    def test_ranged_arm_mounts_share_side_panels_and_keep_detail(self):
        expected = {
            "Forearm_Left_EH1_mediumlaser": ("LeftArm", "Forearm"),
            "Forearm_Right_BH1_autocannon20": ("RightArm", "Forearm"),
            "Forearm_Left_OH1_Large": ("LeftArm", "Forearm"),
            "Forearm_Right_BH1_Hero": ("RightArm", "Forearm"),
            "Upperarm_Left_MH1_lrm15": ("LeftArm", "Upper Arm"),
            "Upperarm_Right_AH1_antimissilesystem": (
                "RightArm", "Upper Arm"),
            "Shoulder_Left_EH1_Medium": ("LeftArm", "Shoulder"),
            "Clavicle_Right_EH5_flamer": ("RightArm", "Clavicle"),
        }
        for slot_id, placement in expected.items():
            with self.subTest(slot_id=slot_id):
                self.assertEqual(weapon_slot_placement(slot_id), placement)

    def test_melee_and_actuator_mounts_use_the_hand_panels(self):
        expected = {
            "Arm_Left_Hand_Actuator_Melee": (
                "LeftHand", "Melee / Actuator"),
            "Arm_Right_BarrelFist_Actuator_Melee": (
                "RightHand", "Melee / Actuator"),
            "Arm_Left_LowerArm_Actuator_Melee": (
                "LeftHand", "Melee / Actuator"),
            "Hand_Left_Melee": ("LeftHand", "Melee / Actuator"),
            "Hand_Right_Melee": ("RightHand", "Melee / Actuator"),
            "Lowerarm_Left_Melee": ("LeftHand", "Melee / Actuator"),
            "Lowerarm_Right_Melee": ("RightHand", "Melee / Actuator"),
        }
        for slot_id, placement in expected.items():
            with self.subTest(slot_id=slot_id):
                self.assertEqual(weapon_slot_placement(slot_id), placement)

    def test_existing_head_torso_and_leg_mappings_are_unchanged(self):
        expected = {
            "Head_EH1_mediumlaser": "Head",
            "Torso_Left_MH1_lrm10": "LeftTorso",
            "Torso_Center_EH1_mediumlaser": "CenterTorso",
            "Torso_Right_BH1_autocannon5": "RightTorso",
            "Leg_Left_EH1_smalllaser": "LeftLeg",
            "Leg_Right_EH1_smalllaser": "RightLeg",
        }
        for slot_id, location in expected.items():
            with self.subTest(slot_id=slot_id):
                self.assertEqual(weapon_slot_location(slot_id), location)

    def test_nonstandard_torso_leg_and_arm_sides_keep_legacy_names(self):
        expected = {
            "Torso_Rear_EH1_mediumlaser": "RearTorso",
            "Leg_Center_EH1_smalllaser": "CenterLeg",
            "Arm_Center_Melee": "CenterArm",
        }
        for slot_id, location in expected.items():
            with self.subTest(slot_id=slot_id):
                self.assertEqual(weapon_slot_location(slot_id), location)

    def test_detailed_arm_region_is_kept_in_display_labels(self):
        self.assertEqual(
            weapon_slot_location_label("Forearm_Left_EH1_mediumlaser"),
            "Left Arm · Forearm",
        )
        self.assertEqual(
            weapon_slot_location_label("Shoulder_Left_EH1_Medium"),
            "Left Arm · Shoulder",
        )
        self.assertEqual(
            weapon_slot_location_label("Lowerarm_Right_Melee"),
            "Right Hand / Melee",
        )

    def test_hero_and_unknown_locations_still_use_other_hardpoints(self):
        for slot_id, expected in {
            "Hero_Left_EH1_ppc": "Hero",
            "Hero_EH1_Laser_smallpulselaser": "Hero",
            "Mystery_Left_EH1_mediumlaser": "Mystery",
        }.items():
            with self.subTest(slot_id=slot_id):
                location = weapon_slot_location(slot_id)
                self.assertEqual(location, expected)
                self.assertNotIn(location, BODY_LOCATION_POS)


class BodyLocationLayoutTests(unittest.TestCase):
    def test_composite_arms_flank_torsos_and_hands_sit_below(self):
        expected = {
            "Head": (0, 2),
            "LeftArm": (1, 0),
            "LeftTorso": (1, 1),
            "CenterTorso": (1, 2),
            "RightTorso": (1, 3),
            "RightArm": (1, 4),
            "LeftHand": (2, 0),
            "LeftLeg": (2, 1),
            "RightLeg": (2, 3),
            "RightHand": (2, 4),
        }
        self.assertEqual(BODY_LOCATION_POS, expected)

    def test_hand_labels_list_order_and_equipment_heading(self):
        self.assertEqual(LOCATION_LABEL["LeftHand"], "Left Hand / Melee")
        self.assertEqual(LOCATION_LABEL["RightHand"], "Right Hand / Melee")
        self.assertLess(
            LOCATION_ORDER.index("LeftArm"),
            LOCATION_ORDER.index("LeftHand"),
        )
        self.assertLess(
            LOCATION_ORDER.index("RightArm"),
            LOCATION_ORDER.index("RightHand"),
        )
        self.assertEqual(ARM_EQUIPMENT_SECTION, "Equipment")


if __name__ == "__main__":
    unittest.main()
