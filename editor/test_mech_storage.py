"""Regression tests for active-bay slot reuse and buyback filtering."""
import base64
import json
import os
import tempfile
import unittest

from savefile import (
    BUYBACK_MARKET_LOADOUT_TYPE,
    COLD_STORAGE_LOADOUT_TYPE,
    MARKET_LOADOUT_TYPE,
    Mech,
    NON_OWNED_LOADOUT_TYPES,
    SaveFile,
    ZERO_GUID,
    write_fstring_payload,
)
from ue_property import ArrayValue, Property, PropertyList, Writer, write_property_list


def _slot(value: bytes) -> PropertyList:
    return PropertyList([
        Property("Value", "StructProperty", b"", value),
    ])


def _mech(loadout_type: str = "") -> Mech:
    properties = []
    if loadout_type:
        properties.append(Property(
            "MechLoadoutType",
            "EnumProperty",
            b"",
            write_fstring_payload(loadout_type),
        ))
    return Mech(PropertyList(), None, PropertyList(properties), b"")


class StorageHarness(SaveFile):
    def __init__(self, values: list[bytes]):
        self.storage = ArrayValue(
            "StructProperty",
            len(values),
            [_slot(value) for value in values],
        )
        self.wrappers = ArrayValue("StructProperty", 0, [])

    def _storage_array(self) -> ArrayValue:
        return self.storage

    def _wrappers_array(self) -> ArrayValue:
        return self.wrappers


class MechListHarness(SaveFile):
    def __init__(self, mechs: list[Mech]):
        self.all_mechs = mechs

    def _all_mechs(self) -> list[Mech]:
        return self.all_mechs


class StubImportedMech:
    def __init__(self, loadout_type: str):
        self.loadout_type = loadout_type
        self.guid = ZERO_GUID

    @property
    def is_owned(self) -> bool:
        return self.loadout_type not in NON_OWNED_LOADOUT_TYPES

    def flush(self):
        pass


class ImportHarness(StorageHarness):
    def __init__(self, loadout_types: list[str]):
        super().__init__([ZERO_GUID])
        self.incoming = [StubImportedMech(value) for value in loadout_types]

    def _mech_from_element(self, _element: PropertyList) -> StubImportedMech:
        return self.incoming.pop(0)

    def _sample_owner_payload(self) -> None:
        return None


def _empty_wrapper_blob() -> str:
    writer = Writer()
    write_property_list(writer, PropertyList())
    return base64.b64encode(writer.bytes()).decode("ascii")


class MechStorageTests(unittest.TestCase):
    def test_claim_reuses_first_zero_slot_without_growing_array(self):
        occupied = b"a" * 16
        added = b"b" * 16
        save = StorageHarness([occupied, ZERO_GUID, ZERO_GUID])
        reused_slot = save.storage.elements[1]

        save._claim_storage_slot(added)

        values = [slot.get("Value").raw_payload for slot in save.storage.elements]
        self.assertEqual(values, [occupied, added, ZERO_GUID])
        self.assertEqual(save.storage.count, 3)
        self.assertIs(save.storage.elements[1], reused_slot)

    def test_repeated_release_and_claim_keeps_reusing_same_slot(self):
        occupied = b"a" * 16
        save = StorageHarness([occupied, ZERO_GUID])

        for n in range(1, 11):
            guid = n.to_bytes(16, "little")
            save._claim_storage_slot(guid)
            save.remove_mech(guid)

        values = [slot.get("Value").raw_payload for slot in save.storage.elements]
        self.assertEqual(values, [occupied, ZERO_GUID])
        self.assertEqual(save.storage.count, 2)

    def test_claim_appends_only_when_no_zero_slot_exists(self):
        occupied = b"a" * 16
        added = b"b" * 16
        save = StorageHarness([occupied])

        save._claim_storage_slot(added)

        values = [slot.get("Value").raw_payload for slot in save.storage.elements]
        self.assertEqual(values, [occupied, added])
        self.assertEqual(save.storage.count, 2)

    def test_buyback_market_loadout_is_not_an_owned_mech(self):
        active = _mech()
        market = _mech(MARKET_LOADOUT_TYPE)
        buyback = _mech(BUYBACK_MARKET_LOADOUT_TYPE)
        cold = _mech(COLD_STORAGE_LOADOUT_TYPE)
        save = MechListHarness([active, market, buyback, cold])

        self.assertEqual(save.mechs(), [active])
        self.assertEqual(save.cold_storage_mechs(), [cold])

    def test_import_skips_market_and_buyback_wrappers_from_old_exports(self):
        save = ImportHarness([
            MARKET_LOADOUT_TYPE,
            BUYBACK_MARKET_LOADOUT_TYPE,
            "",
            COLD_STORAGE_LOADOUT_TYPE,
        ])
        blob = _empty_wrapper_blob()
        data = {
            "format": "mw5export",
            "mechs": [{"blob": blob} for _ in range(4)],
        }

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "legacy-buybacks.mw5export")
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(data, stream)
            summary = save.import_from(
                path,
                mechs=True,
                pilots=False,
                inventory=False,
                cbills=False,
                factions=False,
            )

        self.assertEqual(summary["mechs"], 2)
        self.assertEqual(save.wrappers.count, 2)
        self.assertEqual(len(save.wrappers.elements), 2)
        self.assertNotEqual(save.storage.elements[0].get("Value").raw_payload,
                            ZERO_GUID)


if __name__ == "__main__":
    unittest.main()
