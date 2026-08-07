"""Regression tests for importing into an empty inventory (issue #21)."""
import json
import os
import struct
import tempfile
import unittest
from types import SimpleNamespace

from savefile import SaveFile, InventoryItem, write_fstring_payload
from ue_property import (
    ArrayValue,
    Property,
    PropertyList,
    Reader,
    Writer,
    read_property_list,
    write_property_list,
)


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

    def _inventory_array(self, which: str, *, create: bool = False) -> ArrayValue:
        return self.arrays[which]


class InventoryModelHarness(SaveFile):
    def __init__(self, properties=None):
        self.inventory = PropertyList(properties or [])

    def model(self, name: str):
        if name != "InventoryModel":
            raise KeyError(name)
        return SimpleNamespace(plist=self.inventory)


def _array_property(raw_payload=b"", decoded=None) -> Property:
    w = Writer()
    w.i64(len(raw_payload))
    w.fstring("StructProperty")
    return Property(
        "Items",
        "ArrayProperty",
        w.bytes(),
        raw_payload,
        decoded,
        array_leading_byte=b"\x00",
    )


def _roundtrip_inventory(save: InventoryModelHarness) -> InventoryModelHarness:
    writer = Writer()
    write_property_list(writer, save.inventory)
    return InventoryModelHarness(
        read_property_list(Reader(writer.bytes())).properties
    )


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

    def test_old_export_uses_built_in_donor_for_empty_inventory(self):
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
            summary = target.import_from(
                path, mechs=False, pilots=False, inventory=True,
                cbills=False, factions=False,
            )

        self.assertEqual(summary["items"], 1)
        imported = InventoryItem(target.arrays["weapon"].elements[0])
        self.assertEqual(
            (imported.asset_type, imported.asset_name, imported.count),
            ("MWTraceWeaponDataAsset", "MediumLaser", 1),
        )

    def test_missing_inventory_wrapper_opens_empty_and_is_grafted_on_add(self):
        save = InventoryModelHarness()

        self.assertEqual(save.weapon_inventory(), [])
        self.assertEqual(save.inventory.properties, [])

        guid = save.add_item(
            "weapon", "MWTraceWeaponDataAsset", "MediumLaser", 2
        )
        reparsed = _roundtrip_inventory(save)
        items = reparsed.weapon_inventory()

        self.assertEqual(len(items), 1)
        self.assertEqual(
            (items[0].asset_type, items[0].asset_name, items[0].count),
            ("MWTraceWeaponDataAsset", "MediumLaser", 2),
        )
        self.assertEqual(items[0].guid, guid)

    def test_missing_items_property_is_grafted_on_add(self):
        wrapper = _struct("EquipmentInventory", [], "EquipmentInventory")
        save = InventoryModelHarness([wrapper])

        self.assertEqual(save.equipment_inventory(), [])
        save.add_item(
            "equipment", "MWHeatSinkDataAsset", "DoubleHeatSink", 3
        )

        items = _roundtrip_inventory(save).equipment_inventory()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].asset_name, "DoubleHeatSink")
        self.assertEqual(items[0].count, 3)

    def test_undecoded_zero_count_array_is_rebuilt_on_add(self):
        items = _array_property(struct.pack("<i", 0), decoded=None)
        wrapper = _struct(
            "WeaponInventory", [items], "WeaponInventory"
        )
        save = InventoryModelHarness([wrapper])

        self.assertEqual(save.weapon_inventory(), [])
        save.add_item(
            "weapon", "MWProjectileWeaponDataAsset", "Autocannon10", 1
        )

        reparsed = _roundtrip_inventory(save).weapon_inventory()
        self.assertEqual(len(reparsed), 1)
        self.assertEqual(reparsed[0].asset_name, "Autocannon10")

    def test_undecodable_nonempty_array_is_preserved_and_explained(self):
        raw = struct.pack("<i", 1) + b"not-a-valid-item"
        items = _array_property(raw, decoded=None)
        wrapper = _struct(
            "WeaponInventory", [items], "WeaponInventory"
        )
        save = InventoryModelHarness([wrapper])

        self.assertEqual(save.weapon_inventory(), [])
        with self.assertRaisesRegex(
                RuntimeError, "1 item.*could not be decoded safely"):
            save.add_item(
                "weapon", "MWTraceWeaponDataAsset", "MediumLaser", 1
            )
        self.assertEqual(items.raw_payload, raw)


if __name__ == "__main__":
    unittest.main()
