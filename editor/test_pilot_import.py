"""Regression tests for transferring commander pilots (issue #17)."""
import os
import struct
import tempfile
import unittest

from savefile import (
    Pilot,
    SaveFile,
    build_text_property,
    read_fstring_payload,
    write_fstring_payload,
)
from ue_property import ArrayValue, Property, PropertyList, Writer


def _header(size: int) -> bytes:
    return struct.pack("<q", size) + b"\x00"


def _leaf(name: str, prop_type: str, payload: bytes) -> Property:
    return Property(name, prop_type, _header(len(payload)), payload)


def _struct(name: str, children: list[Property], struct_name: str = "TestStruct") -> Property:
    w = Writer()
    w.i64(0)
    w.fstring(struct_name)
    w.write(b"\x00" * 16)
    return Property(
        name,
        "StructProperty",
        w.bytes(),
        b"",
        PropertyList(children),
        struct_leading_byte=b"\x00",
    )


def _guid(name: str, value: bytes) -> Property:
    w = Writer()
    w.i64(16)
    w.fstring("Guid")
    w.write(b"\x00" * 16)
    return Property(
        name,
        "StructProperty",
        w.bytes(),
        value,
        struct_leading_byte=b"\x00",
    )


def _enum(name: str, value: str) -> Property:
    payload = write_fstring_payload(value)
    w = Writer()
    w.i64(len(payload))
    w.fstring("EMechWarriorPlayerSlot")
    w.write(b"\x00")
    return Property(name, "EnumProperty", w.bytes(), payload)


def _pilot_element(callsign: str, slot: str, guid: bytes) -> PropertyList:
    return PropertyList([
        _struct("PersonaData", [
            _struct("PersonaId", [_guid("Value", guid)]),
            _leaf("Callsign", "TextProperty", build_text_property(callsign)),
        ]),
        _enum("LockedPlayerSlot", slot),
    ])


class PilotHarness(SaveFile):
    def __init__(self, elements=None):
        self.roster = ArrayValue("StructProperty", len(elements or []), elements or [])

    def model(self, name):
        if name != "RosterModel":
            raise KeyError(name)
        pilot_roster = Property("PilotRoster", "ArrayProperty", b"", b"", self.roster)
        return type("Model", (), {"plist": PropertyList([pilot_roster])})()


class PilotImportTests(unittest.TestCase):
    def test_imported_commander_becomes_regular_pilot(self):
        source_guid = b"c" * 16
        source = PilotHarness([
            _pilot_element(
                "MASON", "EMechWarriorPlayerSlot::Player1", source_guid
            )
        ])
        target = PilotHarness()

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "pilot.mw5export")
            source.export_to(
                path, mechs=False, pilots=True, inventory=False,
                cbills=False, factions=False,
            )
            summary = target.import_from(
                path, mechs=False, pilots=True, inventory=False,
                cbills=False, factions=False,
            )

        self.assertEqual(summary["pilots"], 1)
        imported = Pilot(target.roster.elements[0])
        self.assertFalse(imported.is_commander)
        self.assertNotEqual(imported.persona_id, source_guid)
        self.assertEqual(
            read_fstring_payload(imported.element.get("LockedPlayerSlot").raw_payload),
            "EMechWarriorPlayerSlot::None",
        )


if __name__ == "__main__":
    unittest.main()
