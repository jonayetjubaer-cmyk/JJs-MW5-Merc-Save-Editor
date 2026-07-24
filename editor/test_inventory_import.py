"""Regression tests for importing into an empty inventory (issue #21)."""
import json
import os
import struct
import tempfile
import unittest

from savefile import SaveFile, InventoryItem, write_fstring_payload
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


def _inventory_element(kind: str, asset_type: str, asset_name: str,
                       count: int, guid: bytes) -> PropertyList:
    id_field = "WeaponId" if kind == "weapon" else "EquipmentId"
    return PropertyList([
        _struct("ItemId", [_guid("Value", guid)]),
        _struct("ItemData", [
            _struct(id_field, [
                _struct("ID", [
                    _struct("PrimaryAssetType", [
                        _leaf("Name", "NameProperty", write_fstring_payload(asset_type)),
                    ]),
                    _leaf("PrimaryAssetName", "NameProperty", write_fstring_payload(asset_name)),
                ]),
            ]),
        ]),
        _leaf("Count", "IntProperty", struct.pack("<i", count)),
    ])


class InventoryHarness(SaveFile):
    def __init__(self, weapon_elements=None, equipment_elements=None):
        self.arrays = {
            "weapon": ArrayValue("StructProperty", len(weapon_elements or []), weapon_elements or []),
            "equipment": ArrayValue(
                "StructProperty", len(equipment_elements or []), equipment_elements or []
            ),
        }

    def _inventory_array(self, which: str) -> ArrayValue:
        return self.arrays[which]


class EmptyInventoryImportTests(unittest.TestCase):
    def test_new_export_supplies_donors_for_empty_inventory(self):
        weapon = _inventory_element(
            "weapon", "MWTraceWeaponDataAsset", "MediumLaser", 3, b"w" * 16
        )
        equipment = _inventory_element(
            "equipment", "MWEquipmentDataAsset", "SingleHeatSink", 5, b"e" * 16
        )
        source = InventoryHarness([weapon], [equipment])
        target = InventoryHarness()

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "inventory.mw5export")
            source.export_to(
                path, mechs=False, pilots=False, inventory=True,
                cbills=False, factions=False,
            )
            with open(path, encoding="utf-8") as f:
                exported = json.load(f)
            self.assertEqual(exported["version"], 2)
            self.assertEqual(set(exported["inventory_templates"]), {"weapon", "equipment"})

            summary = target.import_from(
                path, mechs=False, pilots=False, inventory=True,
                cbills=False, factions=False,
            )

        self.assertEqual(summary["items"], 2)
        imported_weapon = InventoryItem(target.arrays["weapon"].elements[0])
        imported_equipment = InventoryItem(target.arrays["equipment"].elements[0])
        self.assertEqual(
            (imported_weapon.asset_type, imported_weapon.asset_name, imported_weapon.count),
            ("MWTraceWeaponDataAsset", "MediumLaser", 3),
        )
        self.assertEqual(
            (imported_equipment.asset_type, imported_equipment.asset_name,
             imported_equipment.count),
            ("MWEquipmentDataAsset", "SingleHeatSink", 5),
        )
        self.assertNotEqual(imported_weapon.guid, b"w" * 16)
        self.assertNotEqual(imported_equipment.guid, b"e" * 16)

    def test_old_export_explains_the_required_workaround(self):
        target = InventoryHarness()
        data = {
            "format": "mw5export",
            "version": 1,
            "weapons": [["MediumLaser", "MWTraceWeaponDataAsset", 1]],
            "equipment": [],
        }
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "old.mw5export")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            with self.assertRaisesRegex(RuntimeError, "add one item in-game first"):
                target.import_from(
                    path, mechs=False, pilots=False, inventory=True,
                    cbills=False, factions=False,
                )


if __name__ == "__main__":
    unittest.main()
