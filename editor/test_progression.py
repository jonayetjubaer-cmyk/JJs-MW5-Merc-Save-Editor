"""Exercise the progress controls and atomic weapon/ammo edits."""
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import gui
import progression
from savefile import SaveFile
from test_cantina import array, asset_id, blob
from ue_property import PropertyList, Reader, read_property_list


class ProgressSave(SaveFile):
    def __init__(self, name="TestObjective"):
        objective = PropertyList([asset_id("MWMetagameObjectiveAsset", name)])
        self.models = {
            "ArenaFameModel": SimpleNamespace(plist=PropertyList()),
            "BountyHunterModel": SimpleNamespace(plist=PropertyList()),
            "InventoryModel": SimpleNamespace(plist=PropertyList()),
            "MetagameObjectiveModel": SimpleNamespace(plist=PropertyList([
                array("ObjectiveList", "MetagameObjectiveAssetId", [objective]),
            ])),
        }

    def model(self, name):
        return self.models[name]

    def reload(self, name):
        model = self.model(name)
        model.plist = read_property_list(Reader(blob(model.plist)))


class ProgressionTests(unittest.TestCase):
    def test_quest_checkbox_updates_saved_state_in_both_directions(self):
        with patch("gui.load_pref", side_effect=lambda key, default=None:
                   "en" if key == "language" else False if key == "check_updates" else default):
            app = gui.EditorApp()
        self.addCleanup(app.destroy)
        app.withdraw()
        name = "SC02_Prompt"
        app.save = ProgressSave(name)
        app._refresh_progress()
        self.assertEqual(app._point_controls["arena"][1].get(), "0 points · stock level 0")
        self.assertEqual(app.quest_tree.item(name, "values"), ("Distress Call", "Active"))
        app.quest_tree.selection_set(name)
        app._select_quest()
        self.assertEqual(app.quest_id_var.get(), "Objective ID: SC02_Prompt")
        with patch("gui.messagebox.askyesno", return_value=True):
            app.quest_check.invoke()
            app.save.reload("MetagameObjectiveModel")
            self.assertEqual(progression.quest_states(app.save), [(name, True)])
            app.quest_check.invoke()
        app.save.reload("MetagameObjectiveModel")
        self.assertEqual(progression.quest_states(app.save), [(name, False)])

    def test_quest_titles_use_game_translation_then_english_then_asset_id(self):
        self.assertEqual(progression.quest_title("a1m1_objective", "fr"), "Cambriolage")
        self.assertEqual(progression.quest_title("A1M1_Objective", "unknown"), "Smash and Grab")
        self.assertEqual(progression.quest_title("ModQuest_42", "en"), "ModQuest_42")

    def test_quest_with_pending_claim_is_left_unchanged(self):
        save = ProgressSave()
        model = save.model("MetagameObjectiveModel").plist
        objective = model.get("ObjectiveList").decoded.elements[0]
        model.properties.append(array("ClaimList", "MetagameObjectiveAssetId", [objective]))
        before = blob(model)
        with self.assertRaisesRegex(ValueError, "pending reward"):
            progression.set_quest_completed(save, "TestObjective", True)
        self.assertEqual(blob(model), before)

    def test_paired_inventory_add_rolls_back_when_ammo_overflows(self):
        save = ProgressSave()
        save.add_weapon_with_ammo("MWProjectileWeaponDataAsset", "Autocannon10",
                                  1, "AC10_Standard_AmmoEquipment", 2)
        save.reload("InventoryModel")
        before = blob(save.model("InventoryModel").plist)
        with self.assertRaises(struct.error):
            save.add_weapon_with_ammo("MWProjectileWeaponDataAsset", "Autocannon10",
                                      1, "AC10_Standard_AmmoEquipment", 2147483647)
        self.assertEqual(blob(save.model("InventoryModel").plist), before)


if __name__ == "__main__":
    unittest.main()

