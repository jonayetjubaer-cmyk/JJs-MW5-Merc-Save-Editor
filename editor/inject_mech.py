"""Add a mech to a MW5 Mercs save file (No Man's Sky-save-editor style: clone an
existing owned mech record, give it a fresh GUID, optionally swap its chassis,
and append it to the save).

Two places must agree on the mech's instance GUID:
  - SaveStateModel.MechLoadoutWrappers[i].ByteData -> nested archive ->
    MarketItemMech.Item.ItemId.Value (Guid)         <- the full mech record
  - MechStorageModel.MechStorageList[j].Value (Guid) <- claims a hangar slot

Usage:
    python inject_mech.py <save_in.sav> <save_out.sav> [chassis_primary_asset_name]

Example:
    python inject_mech.py save.sav save_modded.sav AS7-D_MDA
"""
from __future__ import annotations

import copy
import sys
import uuid

from ue_property import Reader, Writer, read_property_list, write_property_list


def fstring_bytes(s: str) -> bytes:
    """Encode a Python str as the FString byte layout used inside raw_payload
    (ASCII, NUL-terminated, int32 length prefix)."""
    w = Writer()
    w.fstring(s)
    return w.bytes()


def find_property_path(plist, *names):
    """Walk nested StructProperty PropertyLists by property name."""
    cur = plist
    for name in names:
        prop = cur.get(name)
        if prop is None:
            return None
        cur = prop.decoded
        if cur is None:
            return prop
    return prop


def get_nested_archive(byte_data_prop):
    """ByteData is ArrayProperty<ByteProperty> whose payload is itself a nested
    tagged-property archive: [int32 length][PROPLIST][FOOTER].

    CRITICAL: the property list does NOT consume the whole declared region --
    every nested archive found (this one, PersistentModelData's, and each
    Model UObject's) ends with 4 extra bytes (observed as 00 00 00 00) beyond
    the 'None' terminator, still WITHIN the declared length. Must capture
    that footer and write it back verbatim, or the engine chokes on truncated/
    misaligned data downstream (silently -- this is what caused "all mechs
    vanished with no error" the first time around: these archives were rebuilt
    from the decoded property list alone and dropped the footer at 3 nested
    levels simultaneously).
    """
    br = Reader(byte_data_prop.raw_payload)
    length = br.i32()
    archive_bytes = br.read(length)
    nested = Reader(archive_bytes)
    plist = read_property_list(nested)
    footer = archive_bytes[nested.pos:]
    return plist, footer


def set_nested_archive(byte_data_prop, plist, footer):
    w = Writer()
    write_property_list(w, plist)
    w.write(footer)
    archive_bytes = w.bytes()
    out = Writer()
    out.i32(len(archive_bytes))
    out.write(archive_bytes)
    byte_data_prop.raw_payload = out.bytes()
    byte_data_prop.decoded = None


def clone_mech_wrapper(wrappers_array, donor_index, new_guid, new_chassis_name=None):
    """Deep-copy an existing MechLoadoutWrapper element, stamp it with a fresh
    instance GUID, and optionally swap its chassis PrimaryAssetName."""
    donor = wrappers_array.elements[donor_index]
    clone = copy.deepcopy(donor)

    nested, footer = get_nested_archive(clone.get("ByteData"))
    market_item = nested.get("MarketItemMech")

    item_id_value = find_property_path(market_item.decoded, "Item", "ItemId", "Value")
    if item_id_value is None or len(item_id_value.raw_payload) != 16:
        raise RuntimeError("could not locate Item.ItemId.Value (Guid) in donor mech")
    item_id_value.raw_payload = new_guid

    if new_chassis_name:
        primary_asset_name = find_property_path(
            market_item.decoded, "Item", "ItemData", "MechDataAssetId", "ID", "PrimaryAssetName"
        )
        if primary_asset_name is None:
            raise RuntimeError("could not locate MechDataAssetId.ID.PrimaryAssetName in donor mech")
        primary_asset_name.raw_payload = fstring_bytes(new_chassis_name)

    set_nested_archive(clone.get("ByteData"), nested, footer)
    return clone


def clone_storage_slot(storage_array, donor_index, new_guid):
    donor = storage_array.elements[donor_index]
    clone = copy.deepcopy(donor)
    value = clone.get("Value")
    if value is None or len(value.raw_payload) != 16:
        raise RuntimeError("could not locate ItemId.Value (Guid) in donor storage slot")
    value.raw_payload = new_guid
    return clone


def inject_mech(data: bytes, new_chassis_name: str | None = None) -> bytes:
    r = Reader(data)
    plist = read_property_list(r)
    consumed = r.pos
    trailer = data[consumed:]

    # NOTE: at every one of these nested-archive levels, the property list does
    # NOT consume the full declared region -- there's a fixed-size footer
    # (observed: 4 zero bytes) after the 'None' terminator that MUST be captured
    # and re-emit verbatim. (See get_nested_archive's docstring for the full
    # story of how dropping these caused "all mechs vanished, no error".)
    pmd = plist.get("PersistentModelData")
    pmd_reader = Reader(pmd.raw_payload)
    pmd_length = pmd_reader.i32()
    pmd_archive_bytes = pmd_reader.read(pmd_length)
    pmd_archive = Reader(pmd_archive_bytes)
    model_list = read_property_list(pmd_archive)
    pmd_footer = pmd_archive_bytes[pmd_archive.pos:]

    save_state = model_list.get("SaveStateModel")
    ss_reader = Reader(save_state.raw_payload)
    ss_class_path = ss_reader.fstring()
    ss_props = read_property_list(ss_reader)
    ss_footer = save_state.raw_payload[ss_reader.pos:]

    mech_storage = model_list.get("MechStorageModel")
    ms_reader = Reader(mech_storage.raw_payload)
    ms_class_path = ms_reader.fstring()
    ms_props = read_property_list(ms_reader)
    ms_footer = mech_storage.raw_payload[ms_reader.pos:]

    wrappers = ss_props.get("MechLoadoutWrappers")
    storage_list = ms_props.get("MechStorageList")

    new_guid = uuid.uuid4().bytes

    new_wrapper = clone_mech_wrapper(wrappers.decoded, 0, new_guid, new_chassis_name)
    wrappers.decoded.elements.append(new_wrapper)
    wrappers.decoded.count += 1

    new_slot = clone_storage_slot(storage_list.decoded, 0, new_guid)
    storage_list.decoded.elements.append(new_slot)
    storage_list.decoded.count += 1

    # Re-serialize bottom-up: model property lists -> models -> PersistentModelData -> top level.
    # Each rebuilt region = [[whatever framing] + property-list bytes + FOOTER],
    # mirroring the original layout exactly (sizes are recomputed from the new
    # lengths; footers are carried through verbatim).
    ss_w = Writer()
    ss_w.fstring(ss_class_path)
    write_property_list(ss_w, ss_props)
    ss_w.write(ss_footer)
    save_state.raw_payload = ss_w.bytes()
    save_state.decoded = None

    ms_w = Writer()
    ms_w.fstring(ms_class_path)
    write_property_list(ms_w, ms_props)
    ms_w.write(ms_footer)
    mech_storage.raw_payload = ms_w.bytes()
    mech_storage.decoded = None

    archive_w = Writer()
    write_property_list(archive_w, model_list)
    archive_w.write(pmd_footer)
    archive_bytes = archive_w.bytes()
    pmd_w = Writer()
    pmd_w.i32(len(archive_bytes))
    pmd_w.write(archive_bytes)
    pmd.raw_payload = pmd_w.bytes()
    pmd.decoded = None

    out_w = Writer()
    write_property_list(out_w, plist)
    return out_w.bytes() + trailer


def main():
    if len(sys.argv) not in (3, 4):
        print(__doc__)
        sys.exit(1)

    in_path, out_path = sys.argv[1], sys.argv[2]
    new_chassis = sys.argv[3] if len(sys.argv) == 4 else None

    with open(in_path, "rb") as f:
        data = f.read()

    print(f"loaded {len(data)} bytes from {in_path}")
    out = inject_mech(data, new_chassis)
    print(f"writing {len(out)} bytes to {out_path}")

    with open(out_path, "wb") as f:
        f.write(out)

    print("done. Verifying round-trip parse of the new file...")
    r = Reader(out)
    read_property_list(r)
    print(f"OK: new save parses cleanly ({r.pos} of {len(out)} bytes consumed)")


if __name__ == "__main__":
    main()
