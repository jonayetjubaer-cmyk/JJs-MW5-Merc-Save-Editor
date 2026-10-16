"""Pilot portrait / voice / bio edits and the pilot catalog helpers."""
import unittest

import pilot_catalog
from savefile import (EMPTY_TEXT, Pilot, build_text_property, read_fstring_payload,
                      read_text_property, write_fstring_payload)
from test_pilot_import import PilotHarness, _leaf, _pilot_element, _struct
from ue_property import Reader, Writer, read_property_list, write_property_list


def _asset_ref(field: str, asset_type: str, asset_name: str):
    return _struct(field, [
        _struct("ID", [
            _struct("PrimaryAssetType", [
                _leaf("Name", "NameProperty", write_fstring_payload(asset_type))]),
            _leaf("PrimaryAssetName", "NameProperty", write_fstring_payload(asset_name)),
        ], "PrimaryAssetId"),
    ], "MWPortraitAssetId")


def _pilot(portrait="MalePilot", voice="MaleAlly4", voice_type="MWDialogueVoiceAsset"):
    element = _pilot_element("EXAMPLE", "EMechWarriorPlayerSlot::None", b"p" * 16)
    persona = element.get("PersonaData").decoded
    persona.properties.append(_asset_ref("PortraitAssetId", "MWPortraitAsset", portrait))
    persona.properties.append(_asset_ref("DialogueVoiceAssetId", voice_type, voice))
    return Pilot(element)


def _pilot_with_bio(parts=("Bio one.", "Bio two.", "Bio three.")):
    pilot = _pilot()
    persona = pilot.persona.decoded
    for field, text in zip(Pilot.BIO_FIELDS, parts):
        payload = build_text_property(text) if text else EMPTY_TEXT
        persona.properties.append(_leaf(field, "TextProperty", payload))
    return pilot


def _reload(pilot: Pilot) -> Pilot:
    w = Writer()
    write_property_list(w, pilot.element)
    return Pilot(read_property_list(Reader(w.bytes())))


class PilotAppearanceTests(unittest.TestCase):
    def test_reads_portrait_and_voice(self):
        pilot = _pilot()
        self.assertEqual((pilot.portrait, pilot.voice), ("MalePilot", "MaleAlly4"))

    def test_edits_survive_serialization_even_when_the_name_gets_longer(self):
        pilot = _pilot()
        pilot.portrait = "Female_Rank3_1"
        pilot.voice = "FemaleAlly8"
        again = _reload(pilot)
        self.assertEqual((again.portrait, again.voice), ("Female_Rank3_1", "FemaleAlly8"))

    def test_voice_type_is_fixed_for_a_pilot_without_a_voice(self):
        # The commander's voice is stored as None / None.
        pilot = _pilot(voice="None", voice_type="None")
        pilot.voice = "MaleAlly1"
        kind = pilot.persona.decoded.get("DialogueVoiceAssetId").decoded \
            .get("ID").decoded.get("PrimaryAssetType").decoded.get("Name")
        self.assertEqual(read_fstring_payload(kind.raw_payload), "MWDialogueVoiceAsset")
        self.assertEqual(_reload(pilot).voice, "MaleAlly1")

    def test_empty_values_are_rejected_and_leave_the_pilot_alone(self):
        pilot = _pilot()
        with self.assertRaises(ValueError):
            pilot.portrait = "  "
        self.assertEqual(pilot.portrait, "MalePilot")

    def test_pilot_without_appearance_data_raises(self):
        element = _pilot_element("EXAMPLE", "EMechWarriorPlayerSlot::None", b"p" * 16)
        pilot = Pilot(element)
        self.assertEqual(pilot.portrait, "")
        with self.assertRaises(ValueError):
            pilot.portrait = "MalePilot"

    def test_add_pilot_can_set_portrait_and_voice(self):
        donor = _pilot()
        harness = PilotHarness([donor.element])
        new = harness.add_pilot("NEWBIE", portrait="Female_Rank1_1", voice="FemaleAlly2")
        self.assertEqual((new.portrait, new.voice), ("Female_Rank1_1", "FemaleAlly2"))
        self.assertEqual(donor.portrait, "MalePilot")   # the donor is untouched


class PilotBioTests(unittest.TestCase):
    def test_bio_joins_the_three_parts_and_fills_in_the_name(self):
        pilot = _pilot_with_bio(("{name} was born.", "Skilled.", "Loud."))
        pilot.callsign = "Jo Smith"
        self.assertEqual(pilot.bio, "Jo Smith was born. Skilled. Loud.")

    def test_setting_bio_writes_bio_and_clears_the_other_parts(self):
        pilot = _pilot_with_bio()
        pilot.bio = "A brand new story."
        self.assertEqual(pilot.bio_parts(), ["A brand new story.", "", ""])
        self.assertEqual(_reload(pilot).bio, "A brand new story.")

    def test_set_bio_parts_keeps_unchanged_payloads(self):
        pilot = _pilot_with_bio()
        before = pilot.persona.decoded.get("Bio1").raw_payload
        pilot.set_bio_parts("Changed.", "Bio two.", "Bio three.")
        self.assertEqual(pilot.persona.decoded.get("Bio1").raw_payload, before)
        self.assertEqual(pilot.bio_parts()[0], "Changed.")

    def test_pilot_without_bio_fields_reads_empty(self):
        pilot = _pilot()
        self.assertEqual(pilot.bio, "")
        pilot.bio = "ignored"   # no field to write; must not raise
        self.assertEqual(pilot.bio, "")


class PilotCatalogTests(unittest.TestCase):
    def test_bundled_catalog_has_the_known_assets(self):
        self.assertIn("LeonFreeman", pilot_catalog.PORTRAITS)
        self.assertIn("MaleAlly4", pilot_catalog.VOICES)
        self.assertTrue(pilot_catalog.PERSONAS)

    def test_sex_filter_drops_the_other_sex_but_keeps_unknown(self):
        names = ["Ally_Female_Rank_1", "Male_Rank1_1", "Lyana"]
        female = pilot_catalog.asset_choices(
            [], names, pilot_catalog.portrait_sex, pilot_catalog.FEMALE)
        self.assertIn("Ally_Female_Rank_1", female)
        self.assertNotIn("Male_Rank1_1", female)
        self.assertIn("Lyana", female)      # unknown sex stays selectable

    def test_choices_include_what_the_save_already_uses(self):
        values = pilot_catalog.asset_choices(["ModdedFace", "None"], ["A"], lambda n: None)
        self.assertEqual(values, ["A", "ModdedFace"])

    def test_names_are_derived_from_string_table_keys(self):
        persona = {"asset_name": "Lyana",
                   "full_name": "Persona_Character_LyanaMoore_FullName",
                   "callsign": "Persona_Character_LyanaMoore_Callsign"}
        self.assertEqual(pilot_catalog.persona_name(persona), "Lyana Moore")
        self.assertEqual(pilot_catalog.persona_name({**persona, "full_name": "Lyana Moore"}),
                         "Lyana Moore")
        self.assertEqual(pilot_catalog.persona_callsign({**persona, "callsign": "Raptor"}),
                         "Raptor")

    def test_persona_bio_parts_keep_placeholders_and_skip_non_prose(self):
        persona = {"asset_name": "X", "bio": "{name} hails from Luthien.", "bio1": "Fast."}
        self.assertEqual(pilot_catalog.persona_bio_parts(persona),
                         ["{name} hails from Luthien.", "Fast.", ""])
        self.assertIsNone(pilot_catalog.persona_bio_parts({"asset_name": "X", "bio": "ONEWORD"}))
        self.assertIsNone(pilot_catalog.persona_bio_parts({"asset_name": "X"}))

    def test_template_personas_have_no_name(self):
        self.assertFalse(pilot_catalog.has_name({"asset_name": "Female_Rank3_5"}))
        self.assertTrue(pilot_catalog.has_name({"asset_name": "Sam", "full_name": "Sam Hagel"}))
        self.assertTrue(pilot_catalog.has_name(
            {"asset_name": "X", "full_name": "Persona_Character_SamHagel_FullName"}))

    def test_voice_and_portrait_labels_name_their_users(self):
        label = pilot_catalog.voice_display("Freeman")
        self.assertTrue(label.startswith("Freeman -- "), label)
        self.assertEqual(pilot_catalog.resolve_asset(label), "Freeman")
        # No known user (or only a name equal to the asset): the bare name.
        self.assertEqual(pilot_catalog.voice_display("NoSuchVoice"), "NoSuchVoice")
        self.assertEqual(pilot_catalog.portrait_display("Raptor"), "Raptor")
        self.assertEqual(pilot_catalog.resolve_asset("Typed_Name"), "Typed_Name")

    def test_placeholder_names_do_not_label_assets(self):
        # "AI PILOT" repeats on dozens of personas, so it must not tag a voice.
        for voice in pilot_catalog.VOICES:
            self.assertNotIn("AI PILOT", pilot_catalog.voice_display(voice))

    def test_persona_picker_round_trips(self):
        persona = pilot_catalog.PERSONAS[0]
        found = pilot_catalog.find_persona(pilot_catalog.persona_display(persona))
        self.assertEqual(found["asset_name"], persona["asset_name"])
        self.assertIsNone(pilot_catalog.find_persona("nope"))


if __name__ == "__main__":
    unittest.main()
