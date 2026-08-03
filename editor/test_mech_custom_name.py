"""Regression tests for stock CustomName assignment on added mechs."""
import struct
import unittest

from savefile import Mech, SaveFile, ZERO_GUID, read_fstring_payload, write_fstring_payload
from ue_property import ArrayValue, Property, PropertyList, Reader, Writer, read_property_list


def _header(size: int) -> bytes:
    return struct.pack("<q", size) + b"\x00"


def _leaf(name: str, prop_type: str, payload: bytes) -> Property:
    return Property(name, prop_type, _header(len(payload)), payload)


def _struct(name: str, children: list[Property]) -> Property:
    writer = Writer()
    writer.i64(0)
    writer.fstring("TestStruct")
    writer.write(b"\x00" * 16)
    return Property(
        name,
        "StructProperty",
        writer.bytes(),
        b"",
        PropertyList(children),
        struct_leading_byte=b"\x00",
    )


def _mech(custom_name: str | None) -> Mech:
    item_data = [_struct("MechDataAssetId", [])]
    if custom_name is not None:
        item_data.append(_leaf(
            "CustomName", "StrProperty", write_fstring_payload(custom_name)
        ))
    item_data.append(_struct("SkinCustomization", []))
    market_item = _struct("MarketItemMech", [
        _struct("Item", [_struct("ItemData", item_data)]),
    ])
    byte_data = Property("ByteData", "ArrayProperty", b"", b"")
    element = PropertyList([byte_data])
    return Mech(element, byte_data, PropertyList([market_item]), b"")


def _roundtrip(mech: Mech) -> Mech:
    mech.flush()
    byte_data = mech.element.get("ByteData")
    reader = Reader(byte_data.raw_payload)
    archive = reader.read(reader.i32())
    archive_reader = Reader(archive)
    nested = read_property_list(archive_reader)
    footer = archive[archive_reader.pos:]
    return Mech(mech.element, byte_data, nested, footer)


class FakeMech:
    def __init__(self, chassis: str, custom_name: str, *, is_owned: bool = True):
        self.chassis = chassis
        self.custom_name = custom_name
        self.guid = b"d" * 16
        self.is_owned = is_owned
        self.template_applied = False
        self.cold_storage = False

    def installed_weapon_count(self) -> int:
        return 1

    def repair(self):
        pass

    def apply_stock_template(self, _template, _weapon_element, _group_element):
        self.template_applied = True

    def apply_stock_equipment(self, _template, _part_element, _item_element) -> bool:
        return True

    def clear_loadout_type(self):
        self.cold_storage = False
        self.is_owned = True

    def set_cold_storage(self, _marker_template):
        self.cold_storage = True
        self.is_owned = False

    def flush(self):
        pass


class FakeElement:
    def __init__(self, mech: FakeMech):
        self.mech = mech


class AddMechHarness(SaveFile):
    def __init__(self, donor: FakeMech, *additional_donors: FakeMech):
        donors = (donor, *additional_donors)
        self.wrappers = ArrayValue(
            "StructProperty",
            len(donors),
            [FakeElement(mech) for mech in donors],
        )
        self.storage = ArrayValue("StructProperty", 1, [
            PropertyList([Property("Value", "StructProperty", b"", ZERO_GUID)]),
        ])

    def _wrappers_array(self) -> ArrayValue:
        return self.wrappers

    def _storage_array(self) -> ArrayValue:
        return self.storage

    def _mech_from_element(self, element: FakeElement) -> FakeMech:
        return element.mech

    def _wrapper_chassis(self, element: FakeElement) -> str:
        return element.mech.chassis

    def _loadout_scaffolds(self):
        return None, None, None, None

    def _mech_loadout_type_template(self):
        return object()


class MechCustomNameTests(unittest.TestCase):
    def test_existing_custom_name_is_replaced_and_roundtrips(self):
        mech = _mech("JVN-10F")

        mech.custom_name = "ADR-A"
        reparsed = _roundtrip(mech)

        self.assertEqual(reparsed.custom_name, "ADR-A")

    def test_missing_custom_name_is_inserted_after_mech_data_asset_id(self):
        mech = _mech(None)

        mech.custom_name = "ADR-PRIME"
        item_data = mech.market_item.decoded.get("Item").decoded.get("ItemData").decoded

        self.assertEqual(
            [prop.name for prop in item_data.properties],
            ["MechDataAssetId", "CustomName", "SkinCustomization"],
        )
        self.assertEqual(item_data.get("CustomName").type, "StrProperty")
        self.assertEqual(
            read_fstring_payload(item_data.get("CustomName").raw_payload),
            "ADR-PRIME",
        )
        self.assertEqual(_roundtrip(mech).custom_name, "ADR-PRIME")

    def test_stock_add_replaces_cross_chassis_donor_name(self):
        donor = FakeMech("JVN-10F_MDA", "JVN-10F")
        save = AddMechHarness(donor)

        _guid, status = save.add_mech("ADR-A_MDA", location="active")
        added = save.wrappers.elements[-1].mech

        self.assertEqual(status, "stock")
        self.assertTrue(added.template_applied)
        self.assertEqual(added.chassis, "ADR-A_MDA")
        self.assertEqual(added.custom_name, "ADR-A")
        self.assertEqual(donor.custom_name, "JVN-10F")

    def test_exact_add_resets_a_custom_donor_name_to_stock(self):
        donor = FakeMech("ADR-A_MDA", "MY ADDER")
        save = AddMechHarness(donor)

        _guid, status = save.add_mech("ADR-A_MDA", location="active")
        added = save.wrappers.elements[-1].mech

        self.assertEqual(status, "exact")
        self.assertEqual(added.custom_name, "ADR-A")
        self.assertEqual(donor.custom_name, "MY ADDER")

    def test_exact_donor_eligibility_is_independent_of_owned_classification(self):
        active_donor = FakeMech("JVN-10F_MDA", "JVN-10F")
        exact_non_owned_donor = FakeMech(
            "ADR-A_MDA",
            "MARKET ADDER",
            is_owned=False,
        )
        save = AddMechHarness(active_donor, exact_non_owned_donor)

        _guid, status = save.add_mech("ADR-A_MDA", location="active")
        added = save.wrappers.elements[-1].mech

        self.assertEqual(status, "exact")
        self.assertEqual(added.chassis, "ADR-A_MDA")
        self.assertTrue(added.is_owned)
        self.assertEqual(added.custom_name, "ADR-A")

    def test_cold_add_resets_name_without_claiming_active_storage(self):
        donor = FakeMech("JVN-10F_MDA", "JVN-10F")
        save = AddMechHarness(donor)

        _guid, status = save.add_mech("ADR-PRIME_MDA", location="cold")
        added = save.wrappers.elements[-1].mech

        self.assertEqual(status, "stock")
        self.assertEqual(added.custom_name, "ADR-PRIME")
        self.assertTrue(added.cold_storage)
        self.assertEqual(save.storage.count, 1)
        self.assertEqual(save.storage.elements[0].get("Value").raw_payload, ZERO_GUID)


if __name__ == "__main__":
    unittest.main()
