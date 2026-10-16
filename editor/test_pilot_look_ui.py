"""Portrait / voice / persona buttons on the Pilots tab write to the save."""
import tkinter as tk
import unittest
from unittest.mock import patch

import gui
from test_pilot_appearance import _pilot, _pilot_with_bio
from test_pilot_import import PilotHarness


class PilotLookUiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.app = gui.EditorApp()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        first, second = _pilot_with_bio(), _pilot(portrait="Raptor", voice="MaleAlly9")
        first.persona_id = b"a" * 16
        second.persona_id = b"b" * 16
        self.app.save = PilotHarness([first.element, second.element])
        self.app._refresh_pilots()
        self.app.update()

    def tearDown(self):
        if hasattr(self, "app"):
            self.app.destroy()

    def _select(self, index):
        self.app.pilot_list.selection_clear(0, "end")
        self.app.pilot_list.selection_set(index)
        self.app._load_pilot_form()

    def test_set_buttons_persist_when_switching_pilots(self):
        self._select(0)
        self.app.pilot_portrait_var.set("Female_Rank3_1")
        self.app.pilot_voice_var.set("FemaleAlly1")
        self.app.on_set_pilot_portrait()
        self.app.on_set_pilot_voice()
        self._select(1)
        self.assertEqual(gui.pilot_catalog.resolve_asset(self.app.pilot_portrait_var.get()), "Raptor")
        self._select(0)
        self.assertEqual(gui.pilot_catalog.resolve_asset(self.app.pilot_portrait_var.get()), "Female_Rank3_1")
        self.assertEqual(gui.pilot_catalog.resolve_asset(self.app.pilot_voice_var.get()), "FemaleAlly1")
        pilot = self.app.save.pilots()[0]
        self.assertEqual((pilot.portrait, pilot.voice), ("Female_Rank3_1", "FemaleAlly1"))

    def test_labelled_picker_values_are_resolved_when_set(self):
        self._select(0)
        self.app.pilot_voice_var.set(gui.pilot_catalog.voice_display("MaleAlly4"))
        self.assertIn(" -- ", self.app.pilot_voice_var.get())     # tagged with its users
        self.app.on_set_pilot_voice()
        self.assertEqual(self.app.save.pilots()[0].voice, "MaleAlly4")

    def test_bio_caption_says_whether_the_pilot_has_a_bio(self):
        self._select(0)
        self.assertIn("Current bio", self.app.pilot_bio_caption.get())
        self._select(1)     # this pilot has no bio fields
        self.assertIn("no bio", self.app.pilot_bio_caption.get())

    def test_unset_picker_does_not_change_the_pilot(self):
        self._select(0)
        self.app.pilot_portrait_var.set("")
        with patch.object(gui.messagebox, "showinfo") as info:
            self.app.on_set_pilot_portrait()
        info.assert_called_once()
        self.assertEqual(self.app.save.pilots()[0].portrait, "MalePilot")

    def test_apply_persona_sets_portrait_and_voice(self):
        self._select(0)
        persona = next(p for p in gui.pilot_catalog.PERSONAS
                       if p["asset_name"] == "Raptor_Persona")
        self.app.pilot_persona_var.set(gui.pilot_catalog.persona_display(persona))
        self.app.on_apply_persona()
        self.assertEqual(gui.pilot_catalog.resolve_asset(self.app.pilot_portrait_var.get()), "Raptor")
        pilot = self.app.save.pilots()[0]
        self.assertEqual((pilot.portrait, pilot.voice), ("Raptor", "MaleAlly9"))

    def test_bio_box_shows_the_bio_and_set_writes_it(self):
        self._select(0)
        self.assertEqual(self.app.pilot_bio_text.get("1.0", "end").strip(),
                         "Bio one. Bio two. Bio three.")
        self.app.pilot_bio_text.delete("1.0", "end")
        self.app.pilot_bio_text.insert("1.0", "Fresh story.")
        self.app.on_set_pilot_bio()
        self._select(1)
        self._select(0)
        self.assertEqual(self.app.save.pilots()[0].bio_parts(), ["Fresh story.", "", ""])
        self.assertEqual(self.app.pilot_bio_text.get("1.0", "end").strip(), "Fresh story.")

    def test_untouched_bio_box_leaves_the_bio_payloads_alone(self):
        self._select(0)
        before = self.app.save.pilots()[0].bio_parts()
        self.app.on_set_pilot_bio()
        self.assertEqual(self.app.save.pilots()[0].bio_parts(), before)

    def test_template_persona_keeps_the_pilots_name_and_bio(self):
        self._select(0)
        pilot = self.app.save.pilots()[0]
        pilot.callsign = "Angel"
        template = {"asset_name": "Female_Rank3_5", "portrait": "Female_Rank3_5",
                    "voice": "FemaleAlly5"}
        with patch.object(gui.pilot_catalog, "find_persona", return_value=template):
            self.app.pilot_persona_var.set("Female_Rank3_5")
            self.app.pilot_persona_text_var.set(True)
            self.app.on_apply_persona()
        self.assertEqual(pilot.callsign, "Angel")
        self.assertEqual(pilot.bio_parts()[0], "Bio one.")
        self.assertEqual((pilot.portrait, pilot.voice), ("Female_Rank3_5", "FemaleAlly5"))

    def test_persona_with_a_bio_sets_all_three_parts(self):
        self._select(0)
        persona = {"asset_name": "P", "full_name": "Jo Smith", "callsign": "Jo",
                   "bio": "{name} one.", "bio1": "Two.", "portrait": "Raptor"}
        with patch.object(gui.pilot_catalog, "find_persona", return_value=persona):
            self.app.pilot_persona_var.set("P")
            self.app.pilot_persona_text_var.set(True)
            self.app.on_apply_persona()
        pilot = self.app.save.pilots()[0]
        self.assertEqual(pilot.bio_parts(), ["{name} one.", "Two.", ""])
        self.assertEqual(pilot.bio, "Jo one. Two.")   # test pilot has no FullName field

    def _type_pending_edits(self):
        """Type into the form without clicking any Apply / Set button."""
        self.app.pilot_vars["callsign"].set("Typed Callsign")
        self.app.pilot_vars["salary"].set("4321")
        self.app.pilot_vars["skill_Ballistics"].set("123456")
        self.app.pilot_vars["cap_Ballistics"].set("7")
        self.app.pilot_bio_text.delete("1.0", "end")
        self.app.pilot_bio_text.insert("1.0", "Typed bio.")

    def _apply_persona(self, persona, with_text):
        with patch.object(gui.pilot_catalog, "find_persona", return_value=persona):
            self.app.pilot_persona_var.set(persona["asset_name"])
            self.app.pilot_persona_text_var.set(with_text)
            self.app.on_apply_persona()

    PERSONA = {"asset_name": "P", "full_name": "Jo Smith", "callsign": "Jo",
               "bio": "Persona bio.", "portrait": "Raptor", "voice": "MaleAlly9"}

    def test_persona_without_text_keeps_every_pending_edit(self):
        self._select(0)
        saved = self.app.save.pilots()[0]
        before = (saved.callsign, saved.salary, saved.skill("Ballistics"), saved.bio_parts())
        self._type_pending_edits()
        self._apply_persona(self.PERSONA, False)
        v = self.app.pilot_vars
        self.assertEqual((v["callsign"].get(), v["salary"].get(), v["skill_Ballistics"].get(),
                          v["cap_Ballistics"].get()), ("Typed Callsign", "4321", "123456", "7"))
        self.assertEqual(self.app.pilot_bio_text.get("1.0", "end").strip(), "Typed bio.")
        self.assertEqual(gui.pilot_catalog.resolve_asset(self.app.pilot_portrait_var.get()), "Raptor")
        self.assertEqual((saved.portrait, saved.voice), ("Raptor", "MaleAlly9"))
        self.assertEqual(before, (saved.callsign, saved.salary, saved.skill("Ballistics"),
                                  saved.bio_parts()))

    def test_persona_with_text_replaces_only_name_and_bio(self):
        self._select(0)
        self._type_pending_edits()
        self._apply_persona(self.PERSONA, True)
        v = self.app.pilot_vars
        self.assertEqual(v["callsign"].get(), "Jo")
        self.assertEqual(self.app.pilot_bio_text.get("1.0", "end").strip(), "Persona bio.")
        self.assertEqual((v["salary"].get(), v["skill_Ballistics"].get(), v["cap_Ballistics"].get()),
                         ("4321", "123456", "7"))
        self.assertEqual(self.app.pilot_list.get(0), "Jo")

    def test_apply_pilot_keeps_pending_portrait_voice_and_bio(self):
        self._select(0)
        self._type_pending_edits()
        self.app.pilot_portrait_var.set("Female_Rank3_1")
        self.app.pilot_voice_var.set("FemaleAlly1")
        self.app.on_apply_pilot()
        pilot = self.app.save.pilots()[0]
        self.assertEqual(pilot.callsign, "Typed Callsign")   # fixture has no salary/skill fields
        self.assertEqual(self.app.pilot_list.get(0), "Typed Callsign")
        self.assertEqual(self.app.pilot_portrait_var.get(), "Female_Rank3_1")
        self.assertEqual(self.app.pilot_voice_var.get(), "FemaleAlly1")
        self.assertEqual(self.app.pilot_bio_text.get("1.0", "end").strip(), "Typed bio.")
        self.assertEqual((pilot.portrait, pilot.voice), ("MalePilot", pilot.voice))
        self.assertEqual(pilot.bio_parts(), ["Bio one.", "Bio two.", "Bio three."])

    def test_reordering_retains_pending_edits_and_apply_targets_moved_pilot(self):
        self._select(0)
        original = self.app.save.pilots()[0]
        other = self.app.save.pilots()[1]
        self._type_pending_edits()
        self.app.pilot_portrait_var.set("Female_Rank3_1")
        self.app.pilot_voice_var.set("FemaleAlly1")
        self.app.on_move_pilot("bottom")
        self.app.pilot_list.event_generate("<<ListboxSelect>>")
        self.app.update()
        self.assertEqual(self.app.pilot_list.curselection(), (1,))
        self.assertIs(self.app.save.pilots()[1].element, original.element)
        self.assertEqual(self.app.pilot_vars["callsign"].get(), "Typed Callsign")
        self.assertEqual(self.app.pilot_vars["skill_Ballistics"].get(), "123456")
        self.assertEqual(self.app.pilot_vars["cap_Ballistics"].get(), "7")
        self.assertEqual(self.app.pilot_bio_text.get("1.0", "end").strip(), "Typed bio.")
        self.app.on_apply_pilot()
        self.app.on_set_pilot_portrait()
        self.app.on_set_pilot_voice()
        self.app.on_set_pilot_bio()
        self.assertEqual(original.callsign, "Typed Callsign")
        self.assertEqual(original.portrait, "Female_Rank3_1")
        self.assertEqual(original.voice, "FemaleAlly1")
        self.assertEqual(original.bio_parts(), ["Typed bio.", "", ""])
        self.assertEqual(other.portrait, "Raptor")
        self.assertEqual(other.voice, "MaleAlly9")
        self.assertNotEqual(other.callsign, "Typed Callsign")
        self._select(0)
        self.assertEqual(gui.pilot_catalog.resolve_asset(self.app.pilot_portrait_var.get()), "Raptor")
        self._select(1)
        self.assertEqual(self.app.pilot_vars["callsign"].get(), "Typed Callsign")

    def test_reordering_no_selection_and_protected_player_are_safe(self):
        self._select(0)
        pilot = self.app.save.pilots()[0]
        from savefile import write_fstring_payload
        pilot.element.get("LockedPlayerSlot").raw_payload = write_fstring_payload(
            "EMechWarriorPlayerSlot::Player1")
        self.app.on_move_pilot("bottom")
        self.assertIs(self.app.save.pilots()[0].element, pilot.element)
        self.assertIn("keep their existing", self.app.status.get())
        self.app.pilot_list.selection_clear(0, "end")
        with patch.object(self.app, "_need_selection") as info:
            self.app.on_move_pilot(-1)
        info.assert_called_once()


if __name__ == "__main__":
    unittest.main()
