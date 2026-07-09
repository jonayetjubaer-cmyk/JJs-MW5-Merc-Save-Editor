"""High-level, reusable API over a MW5 Mercs .sav file.

Wraps the low-level tagged-property reader/writer (ue_property.py) and the hard-
won format quirks (the universal "+1 leading byte" and, critically, the 4-byte
FOOTER that follows the 'None' terminator inside every nested archive -- see
notes/format_notes.md) behind a clean object model:

    save = SaveFile.load(path)
    for mech in save.mechs(): ...      # chassis, repair, remove
    save.add_mech("AS7-D_MDA")
    for pilot in save.pilots(): ...    # callsign, name, skills, salary
    save.save(out_path)

Everything that isn't explicitly edited is preserved byte-for-byte: only the
models that get touched (SaveStateModel / MechStorageModel / RosterModel) are rebuilt,
and they are rebuilt by re-serializing their decoded property list and re-
appending their captured footer, so sizes resync but layout is exact.
"""
from __future__ import annotations

import base64
import copy
import json
import struct
import uuid
from dataclasses import dataclass, field

from ue_property import (
    Reader, Writer, read_property_list, write_property_list,
    Property, PropertyList, ArrayValue,
)
from stock_templates import stock_template


# ---------------------------------------------------------------------------
# Scalar payload helpers (payloads of leaf properties are plain values)
# ---------------------------------------------------------------------------

def read_fstring_payload(payload: bytes) -> str:
    """StrProperty / NameProperty payloads are just an FString."""
    return Reader(payload).fstring()


def write_fstring_payload(s: str) -> bytes:
    w = Writer()
    w.fstring(s)
    return w.bytes()


def read_int(payload: bytes) -> int:
    return struct.unpack("<i", payload[:4])[0]


def write_int(v: int) -> bytes:
    return struct.pack("<i", v)


def read_float(payload: bytes) -> float:
    return struct.unpack("<f", payload[:4])[0]


def write_float(v: float) -> bytes:
    return struct.pack("<f", v)


def read_text_property(payload: bytes) -> str:
    """Best-effort extraction of the display string from a TextProperty payload.

    Two forms occur in MW5 pilot names:
      * simple base/invariant:  [flags i32][0xff][i32=1][FString]
      * formatted ("{rank} {name}" with arg substitutions): a richer tree.
    Pulls out the LAST embedded FString, which is the human-readable value in
    both cases (the final resolved/source string)."""
    r = Reader(payload)
    last = None
    # Scan for FString-shaped runs: an int32 length followed by that many bytes
    # ending in NUL. Simpler + robust than fully modelling FText history types.
    data = payload
    i = 0
    while i + 4 <= len(data):
        n = struct.unpack("<i", data[i:i + 4])[0]
        if 0 < n < 1024 and i + 4 + n <= len(data) and data[i + 4 + n - 1] == 0:
            try:
                s = data[i + 4:i + 4 + n - 1].decode("ascii")
                if all(32 <= ord(c) < 127 for c in s):
                    last = s
                    i += 4 + n
                    continue
            except UnicodeDecodeError:
                pass
        i += 1
    return last or ""


def build_text_property(s: str) -> bytes:
    """Build a simple culture-invariant TextProperty payload (matches the form
    MW5 uses for hand-set pilot callsigns/names: flags=2, history=0xff base,
    bHasCultureInvariantString=1, then the FString)."""
    w = Writer()
    w.i32(2)            # flags
    w.write(b"\xff")    # history type: -1 (base/None)
    w.i32(1)            # bHasCultureInvariantString
    w.fstring(s)
    return w.bytes()


def _set_leaf(prop: Property, new_payload: bytes):
    """Replace a leaf property's payload and rewrite its size field in
    raw_header (raw_header = [size:int64][...maybe sub-tag/trailing...])."""
    if prop is None:
        return
    rr = Reader(prop.raw_header)
    _old_size = rr.i64()
    rest = prop.raw_header[rr.pos:]
    w = Writer()
    w.i64(len(new_payload))
    w.write(rest)
    prop.raw_header = w.bytes()
    prop.raw_payload = new_payload
    prop.decoded = None


def _path(plist: PropertyList, *names):
    """Walk nested StructProperty decoded lists by name; return final Property."""
    cur = plist
    prop = None
    for nm in names:
        if cur is None:
            return None
        prop = cur.get(nm)
        if prop is None:
            return None
        cur = prop.decoded
    return prop


# ---------------------------------------------------------------------------
# Model wrapper
# ---------------------------------------------------------------------------

@dataclass
class ParsedModel:
    """One of the 29 gameplay models inside PersistentModelData. Each lives as
    an ObjectProperty whose raw_payload = [class_path FString][PROPLIST][FOOTER]."""
    name: str
    obj_prop: Property
    class_path: str
    plist: PropertyList
    footer: bytes

    def reserialize(self):
        w = Writer()
        w.fstring(self.class_path)
        write_property_list(w, self.plist)
        w.write(self.footer)
        self.obj_prop.raw_payload = w.bytes()
        self.obj_prop.decoded = None


# ---------------------------------------------------------------------------
# Mech wrapper
# ---------------------------------------------------------------------------

ARMOR_PARTS = ["Head", "CenterTorso", "LeftTorso", "RightTorso",
               "LeftArm", "RightArm", "LeftLeg", "RightLeg"]
REAR_PARTS = ["CenterTorsoRear", "LeftTorsoRear", "RightTorsoRear"]

NONE_ASSET = "None"

# A MechLoadoutWrapper's MechLoadoutType (EnumProperty) tells active-bay mechs
# apart from market listings and cold storage -- ALL three live in the same
# SaveStateModel.MechLoadoutWrappers array and all carry a MarketItemMech, so a
# wrapper must NOT be treated as an owned/active mech just because it has one.
# Active-bay mechs have no MechLoadoutType (or an active value); these two are
# the ones to exclude from the owned list. (Format facts from FiendishDrWu, issue #2.)
MARKET_LOADOUT_TYPE = "EMechLoadoutType::MarketLoadout"
COLD_STORAGE_LOADOUT_TYPE = "EMechLoadoutType::ColdStorageLoadout"
NON_OWNED_LOADOUT_TYPES = (MARKET_LOADOUT_TYPE, COLD_STORAGE_LOADOUT_TYPE)
import re as _re


def hardpoint_class(slot_id: str) -> str | None:
    """Hardpoint class from a weapon slot id, e.g.
    'Torso_Left_EH1_mediumlaser' -> 'EH' (energy), 'BH' (ballistic),
    'MH' (missile), or 'Melee'. The slot id is a FIXED hardpoint identity --
    any weapon of the matching class can go in it (the trailing weapon name is
    just the hardpoint's default and does NOT need to match what's installed)."""
    if "Melee" in slot_id:
        return "Melee"
    for tok in slot_id.split("_"):
        # E/B/M/A H<n>: energy, ballistic, missile, anti-missile (AMS) hardpoints
        m = _re.match(r"^([EBMA])H\d+$", tok)
        if m:
            return m.group(1) + "H"
    return None


def weapon_class(asset_name: str, asset_type: str) -> str | None:
    """Which hardpoint class a weapon fits into. Note asset TYPE (Trace/
    Projectile/Missile/Melee) doesn't map 1:1 to hardpoint class: PPC is a
    Projectile but goes in an Energy hardpoint; the MachineGun is a Trace but
    goes in a Ballistic hardpoint."""
    if asset_type == "MWMissileWeaponDataAsset":
        return "MH"
    if asset_type == "MWMeleeWeaponDataAsset":
        return "Melee"
    if asset_type == "MWAMSWeaponDataAsset":
        return "AH"   # anti-missile system goes in an AMS hardpoint
    if asset_type == "MWTraceWeaponDataAsset":
        return "BH" if "MachineGun" in asset_name else "EH"
    if asset_type == "MWProjectileWeaponDataAsset":
        return "EH" if "PPC" in asset_name else "BH"
    return None


def _bool_value(prop: Property) -> bool:
    # BoolProperty stores its value inline at raw_header[8] (after int64 size=0).
    return bool(prop.raw_header[8]) if prop and len(prop.raw_header) > 8 else False


def _set_bool(prop: Property, value: bool):
    if prop is None or len(prop.raw_header) <= 8:
        return
    hdr = bytearray(prop.raw_header)
    hdr[8] = 1 if value else 0
    prop.raw_header = bytes(hdr)


# -- stock-template element setters (operate on cloned scaffold elements) -----

def _set_weapon_slot_element(el: PropertyList, slot_id: str, wtype: str, wname: str):
    """Overwrite a cloned InstalledWeapons element's hardpoint id and weapon."""
    sid = el.get("HardpointSlotID")
    if sid is not None:
        _set_leaf(sid, write_fstring_payload(slot_id))
    tp = _path(el, "WeaponData", "WeaponId", "ID", "PrimaryAssetType", "Name")
    nm = _path(el, "WeaponData", "WeaponId", "ID", "PrimaryAssetName")
    if tp is not None:
        _set_leaf(tp, write_fstring_payload(wtype))
    if nm is not None:
        _set_leaf(nm, write_fstring_payload(wname))


def _set_group_element(el: PropertyList, slot_id: str, bools):
    """Overwrite a cloned WeaponGroups element's hardpoint id and group flags."""
    sid = el.get("HardpointSlotID")
    if sid is not None:
        _set_leaf(sid, write_fstring_payload(slot_id))
    for i in range(1, 7):
        _set_bool(el.get(f"bWeaponGroup{i}"), bool(bools[i - 1]) if i - 1 < len(bools) else False)


def _set_equip_item_element(el: PropertyList, etype, ename, slot_id_int, slot_type_name):
    """Overwrite a cloned SlottedEquipment element (SlotId / SlotTypeAssetId /
    EquipmentData) with a stock-template equipment item."""
    sid = el.get("SlotId")
    if sid is not None:
        _set_leaf(sid, write_int(int(slot_id_int)))
    tp = _path(el, "EquipmentData", "EquipmentId", "ID", "PrimaryAssetType", "Name")
    nm = _path(el, "EquipmentData", "EquipmentId", "ID", "PrimaryAssetName")
    if tp is not None:
        _set_leaf(tp, write_fstring_payload(etype))
    if nm is not None:
        _set_leaf(nm, write_fstring_payload(ename))
    stp = _path(el, "SlotTypeAssetId", "ID", "PrimaryAssetName")
    if stp is not None and slot_type_name:
        _set_leaf(stp, write_fstring_payload(slot_type_name))


class WeaponSlot:
    """One entry of a mech's InstalledWeapons, linked to its WeaponGroups entry."""

    def __init__(self, element: PropertyList, group_element: PropertyList | None):
        self.element = element
        self.group_element = group_element  # matching WeaponGroups[] entry (by slot id)

    @property
    def slot_id(self) -> str:
        p = self.element.get("HardpointSlotID")
        return read_fstring_payload(p.raw_payload) if p else ""

    @property
    def hardpoint_class(self) -> str | None:
        return hardpoint_class(self.slot_id)

    def _type_prop(self):
        return _path(self.element, "WeaponData", "WeaponId", "ID",
                     "PrimaryAssetType", "Name")

    def _name_prop(self):
        return _path(self.element, "WeaponData", "WeaponId", "ID", "PrimaryAssetName")

    @property
    def weapon_type(self) -> str:
        p = self._type_prop()
        return read_fstring_payload(p.raw_payload) if p else NONE_ASSET

    @property
    def weapon_name(self) -> str:
        p = self._name_prop()
        return read_fstring_payload(p.raw_payload) if p else NONE_ASSET

    @property
    def is_empty(self) -> bool:
        return self.weapon_name in ("", NONE_ASSET)

    def set_weapon(self, asset_type: str, asset_name: str):
        _set_leaf(self._type_prop(), write_fstring_payload(asset_type))
        _set_leaf(self._name_prop(), write_fstring_payload(asset_name))

    def clear(self):
        self.set_weapon(NONE_ASSET, NONE_ASSET)

    def groups(self) -> set[int]:
        out = set()
        if self.group_element is not None:
            for n in range(1, 7):
                if _bool_value(self.group_element.get(f"bWeaponGroup{n}")):
                    out.add(n)
        return out

    def set_group(self, n: int, on: bool):
        if self.group_element is not None:
            _set_bool(self.group_element.get(f"bWeaponGroup{n}"), on)


class EquipmentSlot:
    """One SlottedEquipment entry inside a mech part (Equipment.MechPartEquipment).
    Holds heat sinks, ammo, jump jets, MASC, etc. The slot's `slot_type`
    constrains what fits (e.g. 'General_SlotType' takes heat sinks/ammo/general
    gear; 'JumpJetClass5_SlotType' takes class-5 jump jets)."""

    def __init__(self, element: PropertyList, mech_part: str):
        self.element = element
        self.mech_part = mech_part   # e.g. "EMechParts::CenterTorso"

    @property
    def slot_type(self) -> str:
        p = _path(self.element, "SlotTypeAssetId", "ID", "PrimaryAssetName")
        return read_fstring_payload(p.raw_payload) if p else ""

    def _type_prop(self):
        return _path(self.element, "EquipmentData", "EquipmentId", "ID",
                     "PrimaryAssetType", "Name")

    def _name_prop(self):
        return _path(self.element, "EquipmentData", "EquipmentId", "ID", "PrimaryAssetName")

    @property
    def equip_type(self) -> str:
        p = self._type_prop()
        return read_fstring_payload(p.raw_payload) if p else NONE_ASSET

    @property
    def equip_name(self) -> str:
        p = self._name_prop()
        return read_fstring_payload(p.raw_payload) if p else NONE_ASSET

    @property
    def is_empty(self) -> bool:
        return self.equip_name in ("", NONE_ASSET)

    @property
    def part_label(self) -> str:
        return self.mech_part.split("::")[-1]

    def set_equipment(self, asset_type: str, asset_name: str):
        _set_leaf(self._type_prop(), write_fstring_payload(asset_type))
        _set_leaf(self._name_prop(), write_fstring_payload(asset_name))

    def clear(self):
        self.set_equipment(NONE_ASSET, NONE_ASSET)


class Mech:
    """A MechLoadoutWrapper element. Its real data lives in a nested archive
    (ByteData) -> MarketItemMech struct."""

    def __init__(self, element: PropertyList, byte_data_prop: Property,
                 nested: PropertyList, footer: bytes):
        self.element = element
        self._byte_data = byte_data_prop
        self.nested = nested
        self._footer = footer
        self.market_item = nested.get("MarketItemMech")

    @property
    def guid(self) -> bytes:
        p = _path(self.market_item.decoded, "Item", "ItemId", "Value")
        return p.raw_payload if p else b""

    @guid.setter
    def guid(self, value: bytes):
        p = _path(self.market_item.decoded, "Item", "ItemId", "Value")
        if p is not None:
            p.raw_payload = value

    @property
    def loadout_type(self) -> str:
        """The wrapper's MechLoadoutType enum value, e.g.
        'EMechLoadoutType::MarketLoadout' / '::ColdStorageLoadout'. Empty for
        active-bay owned mechs (which carry no MechLoadoutType in the saves
        seen so far)."""
        p = self.nested.get("MechLoadoutType")
        return read_fstring_payload(p.raw_payload) if p else ""

    @property
    def is_owned(self) -> bool:
        """True for an active-bay owned mech (excludes market listings and
        cold-storage records)."""
        return self.loadout_type not in NON_OWNED_LOADOUT_TYPES

    def set_cold_storage(self, marker_template=None):
        """Mark this mech as a cold-storage record by setting its nested-archive
        MechLoadoutType to ColdStorageLoadout. Active-bay mechs have no
        MechLoadoutType property, so if it's absent we graft one (deep-copied
        from `marker_template`, an EnumProperty harvested from any market/cold
        wrapper) as the first property -- matching the real cold-storage layout
        [MechLoadoutType, MarketItemMech, Owner]."""
        p = self.nested.get("MechLoadoutType")
        if p is None:
            if marker_template is None:
                raise RuntimeError("No MechLoadoutType template available to graft.")
            p = copy.deepcopy(marker_template)
            p.name = "MechLoadoutType"
            self.nested.properties.insert(0, p)
        _set_leaf(p, write_fstring_payload(COLD_STORAGE_LOADOUT_TYPE))

    def clear_loadout_type(self):
        """Drop any MechLoadoutType property so the mech is treated as an
        active-bay mech (used when an added mech was cloned from a cold/market
        donor but should land in the active bay)."""
        self.nested.properties = [p for p in self.nested.properties
                                  if p.name != "MechLoadoutType"]

    @property
    def chassis(self) -> str:
        p = _path(self.market_item.decoded, "Item", "ItemData",
                  "MechDataAssetId", "ID", "PrimaryAssetName")
        return read_fstring_payload(p.raw_payload) if p else ""

    @chassis.setter
    def chassis(self, name: str):
        p = _path(self.market_item.decoded, "Item", "ItemData",
                  "MechDataAssetId", "ID", "PrimaryAssetName")
        if p is not None:
            _set_leaf(p, write_fstring_payload(name))

    def repair(self):
        """Set CurrentStructure/CurrentArmor (and rear) to the Installed values
        -> a fully patched-up mech."""
        item_data = _path(self.market_item.decoded, "Item", "ItemData")
        if item_data is None or item_data.decoded is None:
            return
        ld = item_data.decoded

        def copy_struct(src_name, dst_name, parts):
            src = ld.get(src_name)
            dst = ld.get(dst_name)
            if src is None or dst is None or src.decoded is None or dst.decoded is None:
                return
            for part in parts:
                sp = src.decoded.get(part)
                dp = dst.decoded.get(part)
                if sp is not None and dp is not None:
                    dp.raw_payload = sp.raw_payload  # float, fixed 4 bytes

        copy_struct("InstalledArmor", "CurrentArmor", ARMOR_PARTS)
        copy_struct("InstalledRearArmor", "CurrentRearArmor", REAR_PARTS)
        # Structure: in practice MW5 saves only store CurrentStructure (no
        # "InstalledStructure"), so there is no in-save max to copy from. If the
        # donor was damaged/under repair its reduced CurrentStructure would carry
        # into an exact-copy add and the new mech would spawn looking damaged
        # (issue #13). Restore from this chassis's stock-template structure, which
        # is the factory-max value per location.
        if ld.get("InstalledStructure") is not None:
            copy_struct("InstalledStructure", "CurrentStructure", ARMOR_PARTS)
        else:
            cs = ld.get("CurrentStructure")
            tpl = stock_template(self.chassis)
            if cs is not None and cs.decoded is not None and tpl is not None:
                struct = tpl.get("structure", {})
                for part in ARMOR_PARTS:
                    v = struct.get(part)
                    dp = cs.decoded.get(part)
                    if v is not None and dp is not None:
                        dp.raw_payload = write_float(float(v))

    def installed_weapon_count(self) -> int:
        iw = _path(self.market_item.decoded, "Item", "ItemData", "InstalledWeapons")
        if iw is None or iw.decoded is None or not hasattr(iw.decoded, "count"):
            return 0
        return iw.decoded.count

    # -- loadout editing ---------------------------------------------------
    def _loadout(self):
        return _path(self.market_item.decoded, "Item", "ItemData")

    def weapon_slots(self) -> list[WeaponSlot]:
        ld = self._loadout()
        if ld is None or ld.decoded is None:
            return []
        iw = ld.decoded.get("InstalledWeapons")
        if iw is None or iw.decoded is None:
            return []
        # index WeaponGroups by slot id
        groups_by_id = {}
        wgi = ld.decoded.get("WeaponGroupInfo")
        if wgi is not None and wgi.decoded is not None:
            wg = wgi.decoded.get("WeaponGroups")
            if wg is not None and wg.decoded is not None:
                for gel in wg.decoded.elements:
                    sid_p = gel.get("HardpointSlotID")
                    if sid_p is not None:
                        groups_by_id[read_fstring_payload(sid_p.raw_payload)] = gel
        out = []
        for el in iw.decoded.elements:
            sid_p = el.get("HardpointSlotID")
            sid = read_fstring_payload(sid_p.raw_payload) if sid_p else ""
            out.append(WeaponSlot(el, groups_by_id.get(sid)))
        return out

    def equipment_slots(self) -> list[EquipmentSlot]:
        ld = self._loadout()
        if ld is None or ld.decoded is None:
            return []
        eq = ld.decoded.get("Equipment")
        if eq is None or eq.decoded is None:
            return []
        mpe = eq.decoded.get("MechPartEquipment")
        if mpe is None or mpe.decoded is None:
            return []
        out = []
        for part in mpe.decoded.elements:
            mp = part.get("MechPart")
            part_name = read_fstring_payload(mp.raw_payload) if mp else ""
            se = part.get("SlottedEquipment")
            if se is None or se.decoded is None:
                continue
            for el in se.decoded.elements:
                out.append(EquipmentSlot(el, part_name))
        return out

    def armor_value(self, location: str, installed: bool = False) -> float:
        ld = self._loadout()
        if ld is None or ld.decoded is None:
            return 0.0
        rear = location in REAR_PARTS
        struct_name = ("InstalledRearArmor" if rear else "InstalledArmor") if installed \
            else ("CurrentRearArmor" if rear else "CurrentArmor")
        s = ld.decoded.get(struct_name)
        if s is None or s.decoded is None:
            return 0.0
        p = s.decoded.get(location)
        return read_float(p.raw_payload) if p else 0.0

    def set_armor(self, location: str, value: float, installed: bool = False):
        ld = self._loadout()
        if ld is None or ld.decoded is None:
            return
        rear = location in REAR_PARTS
        struct_name = ("InstalledRearArmor" if rear else "InstalledArmor") if installed \
            else ("CurrentRearArmor" if rear else "CurrentArmor")
        s = ld.decoded.get(struct_name)
        if s is None or s.decoded is None:
            return
        p = s.decoded.get(location)
        if p is not None:
            p.raw_payload = write_float(value)  # FloatProperty payload is fixed 4 bytes

    def repair_armor(self):
        """Restore CurrentArmor to InstalledArmor for every location."""
        for loc in ARMOR_PARTS:
            self.set_armor(loc, self.armor_value(loc, installed=True))
        for loc in REAR_PARTS:
            self.set_armor(loc, self.armor_value(loc, installed=True))

    def max_armor(self):
        """Backward-compatible alias for repair_armor().

        Historical name only: this does not apply the chassis's MDA maxArmor
        caps. Current armor may never exceed installed armor.
        """
        self.repair_armor()

    def clear_loadout(self):
        """Empty the hardpoint-keyed loadout arrays (installed weapons + weapon
        groups + chain-fire groups). Used when adding an *approximate* mech of a
        chassis with no exact template: stripping these avoids carrying
        the donor's stale, wrong-chassis weapon-group entries (which is what made
        added mechs' groups reset to 1). The mech keeps its core equipment/engine
        and armor, so it loads as a weaponless chassis the player refits in the
        Mech Lab -- where fresh, correct weapon groups can be set."""
        item_data = _path(self.market_item.decoded, "Item", "ItemData")
        if item_data is None or item_data.decoded is None:
            return
        ld = item_data.decoded
        for path in (("InstalledWeapons",),
                     ("WeaponGroupInfo", "WeaponGroups"),
                     ("WeaponGroupInfo", "ChainFireGroups")):
            prop = _path(ld, *path)
            if prop is not None and prop.decoded is not None and hasattr(prop.decoded, "elements"):
                prop.decoded.elements = []
                prop.decoded.count = 0

    def strip_weapons(self):
        """Keep the hardpoint slots, but empty every weapon and clear all fire-
        group flags. Unlike clear_loadout() (which deletes the slots entirely),
        this leaves an editable, group-clean loadout: an approximate added mech
        keeps its donor's hardpoint layout so you can fit weapons here in the
        editor or in the in-game Mech Lab."""
        for slot in self.weapon_slots():
            slot.clear()
            for n in range(1, 7):
                slot.set_group(n, False)

    def strip_equipment(self):
        """Empty every equipment slot (heat sinks, ammo, jump jets, MASC...).
        Used for an approximate clone of a DIFFERENT chassis: the donor's
        equipment belongs to the donor chassis, so carrying it over saddles the
        new mech with mismatched gear -- e.g. a Javelin donor's jump jets showing
        up as 'invisible' jets that consume tonnage but don't render in the Mech
        Lab. Stripping them leaves a clean chassis the player outfits from
        scratch (the Mech Lab applies the real chassis's slots on refit)."""
        for slot in self.equipment_slots():
            slot.clear()

    def has_hardpoints(self) -> bool:
        return bool(self.weapon_slots())

    def apply_layout(self, iw_av, wg_av, cfg_av):
        """Replace this mech's hardpoint layout with the given arrays (deep-
        copied), then empty the weapons and clear groups. The arrays come from
        SaveFile.chassis_layouts() -- a real layout harvested from the save."""
        ld = self._loadout()
        if ld is None or ld.decoded is None:
            return
        ld = ld.decoded
        iw = ld.get("InstalledWeapons")
        if iw is not None and iw_av is not None:
            iw.decoded = copy.deepcopy(iw_av)
        wgi = ld.get("WeaponGroupInfo")
        if wgi is not None and wgi.decoded is not None:
            wg = wgi.decoded.get("WeaponGroups")
            if wg is not None and wg_av is not None:
                wg.decoded = copy.deepcopy(wg_av)
            cfg = wgi.decoded.get("ChainFireGroups")
            if cfg is not None and cfg_av is not None:
                cfg.decoded = copy.deepcopy(cfg_av)
        self.strip_weapons()   # empty the copied weapons + zero the groups

    def _layout_bundle(self):
        """This mech's (InstalledWeapons, WeaponGroups, ChainFireGroups) decoded
        arrays, for use as a layout template."""
        ld = self._loadout()
        if ld is None or ld.decoded is None:
            return (None, None, None)
        ld = ld.decoded
        iw = ld.get("InstalledWeapons")
        wgi = ld.get("WeaponGroupInfo")
        wg = wgi.decoded.get("WeaponGroups") if wgi and wgi.decoded else None
        cfg = wgi.decoded.get("ChainFireGroups") if wgi and wgi.decoded else None
        return (iw.decoded if iw else None,
                wg.decoded if wg else None,
                cfg.decoded if cfg else None)

    def seed_hardpoints_from(self, donor: "Mech"):
        """Give a mech an editable (emptied) loadout by copying another mech's
        hardpoint layout."""
        self.apply_layout(*donor._layout_bundle())

    # -- traits (Cantina-installed mech quirks) ----------------------------
    def installed_traits_av(self):
        """The InstalledTraits ArrayValue (one element per installed mech
        trait), or None if this mech has no InstalledTraits array yet."""
        ld = self._loadout()
        if ld is None or ld.decoded is None:
            return None
        it = ld.decoded.get("InstalledTraits")
        if it is None or it.decoded is None or not hasattr(it.decoded, "elements"):
            return None
        return it.decoded

    def traits(self) -> list[str]:
        return _trait_names(self.installed_traits_av())

    def ensure_installed_traits(self, wrapper_template):
        """Return this mech's InstalledTraits ArrayValue, creating the array
        property (cloned from `wrapper_template`) if the mech doesn't have one.
        Owned mechs have no InstalledTraits until a trait is installed, so to
        add the first one we graft in a real (emptied) array wrapper."""
        ld = self._loadout()
        if ld is None or ld.decoded is None:
            return None
        it = ld.decoded.get("InstalledTraits")
        if it is None:
            if wrapper_template is None:
                return None
            it = copy.deepcopy(wrapper_template)
            it.name = "InstalledTraits"
            if it.decoded is not None and hasattr(it.decoded, "elements"):
                it.decoded.elements = []
                it.decoded.count = 0
                it.decoded.inner_tag_name = "InstalledTraits"
                it.decoded.inner_struct_name = "MechTraitDataAssetId"
            ld.decoded.properties.append(it)
        return it.decoded if (it.decoded is not None and hasattr(it.decoded, "elements")) else None

    # -- stock template (factual game data, issue #6) ----------------------
    def _apply_stock_armor(self, tpl):
        armor = tpl.get("armor", {})
        rear = tpl.get("rearArmor", {})
        struct = tpl.get("structure", {})
        for loc in ARMOR_PARTS:
            v = armor.get(loc)
            if v is not None:
                self.set_armor(loc, float(v), installed=True)
                self.set_armor(loc, float(v), installed=False)
        for loc in REAR_PARTS:
            # Stock templates key rear armor by the full location name
            # ('CenterTorsoRear'); loadouts exported by this editor strip the
            # 'Rear' suffix ('CenterTorso'). Accept either so both stock-template
            # adds and .mw5loadout imports apply rear armor. (Previously only the
            # stripped key was tried, so stock adds kept the donor's rear armor
            # and came out under/over tonnage -- issues #12, #14.)
            v = rear.get(loc)
            if v is None:
                v = rear.get(loc[:-4])
            if v is not None:
                self.set_armor(loc, float(v), installed=True)
                self.set_armor(loc, float(v), installed=False)
        ld = self._loadout()
        cs = ld.decoded.get("CurrentStructure") if ld and ld.decoded else None
        if cs is not None and cs.decoded is not None:
            for loc in ARMOR_PARTS:
                v = struct.get(loc)
                p = cs.decoded.get(loc)
                if v is not None and p is not None:
                    p.raw_payload = write_float(float(v))

    def apply_stock_template(self, tpl, weap_scaffold, group_scaffold):
        """Populate this mech's loadout from a stock template: set stock armor /
        structure and rebuild InstalledWeapons + WeaponGroups to the chassis's
        stock weapons. Each array element is a deep copy of a real scaffold
        element with only its hardpoint id + weapon/flags overwritten, so the
        UE structure stays valid. Returns True if applied."""
        ld = self._loadout()
        if ld is None or ld.decoded is None:
            return False
        ldd = ld.decoded
        self._apply_stock_armor(tpl)

        iw = ldd.get("InstalledWeapons")
        if iw is not None and iw.decoded is not None and hasattr(iw.decoded, "elements") \
                and weap_scaffold is not None:
            elems = []
            for wp in tpl.get("weapons", []):
                e = copy.deepcopy(weap_scaffold)
                _set_weapon_slot_element(e, wp.get("slot", ""),
                                         wp.get("type", "None"), wp.get("name", "None"))
                elems.append(e)
            iw.decoded.elements = elems
            iw.decoded.count = len(elems)

        wgi = ldd.get("WeaponGroupInfo")
        if wgi is not None and wgi.decoded is not None:
            wg = wgi.decoded.get("WeaponGroups")
            if wg is not None and wg.decoded is not None and hasattr(wg.decoded, "elements") \
                    and group_scaffold is not None:
                gelems = []
                for g in tpl.get("groups", []):
                    e = copy.deepcopy(group_scaffold)
                    _set_group_element(e, g.get("slot", ""), g.get("g", []))
                    gelems.append(e)
                wg.decoded.elements = gelems
                wg.decoded.count = len(gelems)
            cfg = wgi.decoded.get("ChainFireGroups")
            if cfg is not None and cfg.decoded is not None and hasattr(cfg.decoded, "elements"):
                cfg.decoded.elements = []
                cfg.decoded.count = 0
        return True

    def apply_stock_equipment(self, tpl, part_scaffold, item_scaffold):
        """Rebuild Equipment.MechPartEquipment from the stock template so the
        mech carries its chassis's real stock gear (heat sinks, jump jets, ammo,
        ECM, etc.) instead of the donor's. Each part/item is a deep copy of a
        real scaffold element with only its leaf values overwritten."""
        if part_scaffold is None or item_scaffold is None:
            return False
        ld = self._loadout()
        eq = ld.decoded.get("Equipment") if ld and ld.decoded else None
        mpe = eq.decoded.get("MechPartEquipment") if eq and eq.decoded else None
        if mpe is None or mpe.decoded is None or not hasattr(mpe.decoded, "elements"):
            return False
        parts = []
        for tp_part in tpl.get("equipment", []):
            pe = copy.deepcopy(part_scaffold)
            mp = pe.get("MechPart")
            if mp is not None:
                _set_leaf(mp, write_fstring_payload(tp_part.get("part", "")))
            se = pe.get("SlottedEquipment")
            if se is not None and se.decoded is not None and hasattr(se.decoded, "elements"):
                items = []
                for it in tp_part.get("items", []):
                    ie = copy.deepcopy(item_scaffold)
                    _set_equip_item_element(ie, it.get("type", "None"), it.get("name", "None"),
                                            it.get("slotId", 0), it.get("slotType", ""))
                    items.append(ie)
                se.decoded.elements = items
                se.decoded.count = len(items)
            parts.append(pe)
        mpe.decoded.elements = parts
        mpe.decoded.count = len(parts)
        return True

    def _chain_fire_array(self):
        wgi = _path(self.market_item.decoded, "Item", "ItemData", "WeaponGroupInfo")
        cfg = wgi.decoded.get("ChainFireGroups") if wgi and wgi.decoded else None
        return cfg.decoded if (cfg and cfg.decoded and hasattr(cfg.decoded, "elements")) else None

    def chain_fire_groups(self):
        """Per-group chain-fire flags [g1..g6]. True = that fire group chain-fires
        (weapons fire one after another); False = salvo (all at once)."""
        av = self._chain_fire_array()
        if av is None:
            return [False] * 6
        return [bool(av.elements[i][0]) if i < len(av.elements) and av.elements[i] else False
                for i in range(6)]

    def set_chain_fire_group(self, n, on):
        av = self._chain_fire_array()
        if av is None or not (1 <= n <= 6):
            return
        while len(av.elements) < 6:
            av.elements.append(b"\x00")
        av.elements[n - 1] = b"\x01" if on else b"\x00"
        av.count = len(av.elements)

    def export_loadout(self) -> dict:
        """Read this mech's current loadout into a template-shaped dict
        (weapons, groups, equipment, armor, rearArmor, structure) -- the same
        shape apply_stock_template / apply_stock_equipment consume, so a saved
        loadout can be re-applied to another mech."""
        weapons = [{"slot": w.slot_id, "type": w.weapon_type, "name": w.weapon_name}
                   for w in self.weapon_slots()]
        groups = []
        for w in self.weapon_slots():
            gs = w.groups()
            groups.append({"slot": w.slot_id, "g": [i in gs for i in range(1, 7)]})
        eqmap = {}
        for e in self.equipment_slots():
            sid = e.element.get("SlotId")
            eqmap.setdefault(e.mech_part, []).append({
                "type": e.equip_type, "name": e.equip_name,
                "slotId": read_int(sid.raw_payload) if sid else 0,
                "slotType": e.slot_type})
        equipment = [{"part": k, "items": v} for k, v in eqmap.items()]
        armor = {loc: self.armor_value(loc, installed=True) for loc in ARMOR_PARTS}
        rear = {loc[:-4]: self.armor_value(loc, installed=True) for loc in REAR_PARTS}
        struct = {}
        ld = self._loadout()
        cs = ld.decoded.get("CurrentStructure") if ld and ld.decoded else None
        if cs is not None and cs.decoded is not None:
            for loc in ARMOR_PARTS:
                p = cs.decoded.get(loc)
                if p is not None:
                    struct[loc] = read_float(p.raw_payload)
        return {"chassis": self.chassis, "weapons": weapons, "groups": groups,
                "equipment": equipment, "armor": armor, "rearArmor": rear,
                "structure": struct, "chainFire": self.chain_fire_groups()}

    def flush(self):
        """Re-serialize the nested archive back into the ByteData payload."""
        w = Writer()
        write_property_list(w, self.nested)
        w.write(self._footer)
        archive_bytes = w.bytes()
        out = Writer()
        out.i32(len(archive_bytes))
        out.write(archive_bytes)
        self._byte_data.raw_payload = out.bytes()
        self._byte_data.decoded = None


# ---------------------------------------------------------------------------
# Traits (pilot traits + Cantina-installed mech traits)
# ---------------------------------------------------------------------------
# Both kinds are stored identically: an ArrayProperty<StructProperty> where each
# element is a single `ID` struct (PrimaryAssetType.Name + PrimaryAssetName) --
# the exact shape used by inventory item ids. Pilot traits live on the roster
# pilot element (PilotTraits); mech traits live in the mech loadout
# (InstalledTraits). The only difference is the asset TYPE string.
PILOT_TRAIT_TYPE = "MWPilotTraitDataAsset"
MECH_TRAIT_TYPE = "MWMechTraitDataAsset"


def _trait_element_name(el: PropertyList) -> str:
    idp = el.get("ID")
    if idp is None or idp.decoded is None:
        return ""
    nm = idp.decoded.get("PrimaryAssetName")
    return read_fstring_payload(nm.raw_payload) if nm else ""


def _set_trait_element(el: PropertyList, name: str, type_name: str):
    idp = el.get("ID")
    if idp is None or idp.decoded is None:
        return
    t = _path(idp.decoded, "PrimaryAssetType", "Name")
    nm = idp.decoded.get("PrimaryAssetName")
    if t is not None:
        _set_leaf(t, write_fstring_payload(type_name))
    if nm is not None:
        _set_leaf(nm, write_fstring_payload(name))


def _trait_names(av: ArrayValue) -> list[str]:
    if av is None or not hasattr(av, "elements"):
        return []
    return [_trait_element_name(el) for el in av.elements]


def _trait_add(av: ArrayValue, template_el: PropertyList, name: str, type_name: str) -> bool:
    """Append a trait (cloned from `template_el`) unless it's already present."""
    if av is None or template_el is None:
        return False
    if name in _trait_names(av):
        return False
    new_el = copy.deepcopy(template_el)
    _set_trait_element(new_el, name, type_name)
    av.elements.append(new_el)
    av.count += 1
    return True


def _trait_remove(av: ArrayValue, name: str) -> bool:
    if av is None:
        return False
    for i, el in enumerate(av.elements):
        if _trait_element_name(el) == name:
            del av.elements[i]
            av.count -= 1
            return True
    return False


# ---------------------------------------------------------------------------
# Pilot wrapper
# ---------------------------------------------------------------------------

SKILLS = ["Gunnery", "Ballistics", "Energy", "Missile",
          "Piloting", "Evasiveness", "Shielding", "HeatManagement"]
# Skills that use the 1-10 cap system (Gunnery/Piloting don't -- their cap is 0).
CAPPED_SKILLS = ["Ballistics", "Energy", "Missile",
                 "Evasiveness", "Shielding", "HeatManagement"]
MAX_SKILL_CAP = 10


class Pilot:
    def __init__(self, element: PropertyList):
        self.element = element
        self.persona = element.get("PersonaData")

    @property
    def is_commander(self) -> bool:
        """True if this pilot occupies a real player/commander slot. The
        commander's LockedPlayerSlot is a Player slot (e.g. ::Player1); regular
        hireable pilots have ::None. Deleting the commander can corrupt the
        campaign, so the editor protects it -- but only the *actual* commander,
        not merely whoever happens to be first in the roster."""
        slot = self.element.get("LockedPlayerSlot")
        if slot is None or slot.raw_payload is None:
            return False
        return slot.raw_payload.find(b"::None") == -1

    @property
    def callsign(self) -> str:
        p = _path(self.persona.decoded, "Callsign")
        return read_text_property(p.raw_payload) if p else ""

    @callsign.setter
    def callsign(self, value: str):
        p = _path(self.persona.decoded, "Callsign")
        if p is not None:
            _set_leaf(p, build_text_property(value))

    @property
    def full_name(self) -> str:
        p = _path(self.persona.decoded, "FullName")
        return read_text_property(p.raw_payload) if p else ""

    @full_name.setter
    def full_name(self, value: str):
        p = _path(self.persona.decoded, "FullName")
        if p is not None:
            _set_leaf(p, build_text_property(value))

    def skill(self, name: str) -> int:
        sk = self.element.get("Skills")
        if sk is None or sk.decoded is None:
            return 0
        node = sk.decoded.get(name)
        if node is None or node.decoded is None:
            return 0
        exp = node.decoded.get("TotalExp")
        return read_int(exp.raw_payload) if exp else 0

    def set_skill(self, name: str, value: int):
        sk = self.element.get("Skills")
        if sk is None or sk.decoded is None:
            return
        node = sk.decoded.get(name)
        if node is None or node.decoded is None:
            return
        exp = node.decoded.get("TotalExp")
        if exp is not None:
            _set_leaf(exp, write_int(value))

    def skill_cap(self, name: str) -> int:
        """A skill's cap (max potential), 0-10. The 6 sub-skills (Ballistics,
        Energy, Missile, Evasiveness, Shielding, HeatManagement) use 1-10;
        Gunnery and Piloting are always 0 (they don't use the cap system)."""
        sk = self.element.get("Skills")
        if sk is None or sk.decoded is None:
            return 0
        node = sk.decoded.get(name)
        if node is None or node.decoded is None:
            return 0
        cap = node.decoded.get("SkillCap")
        return cap.raw_payload[0] if cap and cap.raw_payload else 0

    def set_skill_cap(self, name: str, value: int):
        sk = self.element.get("Skills")
        if sk is None or sk.decoded is None:
            return
        node = sk.decoded.get(name)
        if node is None or node.decoded is None:
            return
        cap = node.decoded.get("SkillCap")
        if cap is not None:
            # SkillCap is a 1-byte ByteProperty; size stays 1, so just swap the byte.
            cap.raw_payload = bytes([max(0, min(255, int(value)))])

    @property
    def salary(self) -> int:
        p = self.element.get("SalaryCBills")
        return read_int(p.raw_payload) if p else 0

    @salary.setter
    def salary(self, value: int):
        p = self.element.get("SalaryCBills")
        if p is not None:
            _set_leaf(p, write_int(value))

    @property
    def hiring_cost(self) -> int:
        p = self.element.get("HiringCostCBills")
        return read_int(p.raw_payload) if p else 0

    @hiring_cost.setter
    def hiring_cost(self, value: int):
        p = self.element.get("HiringCostCBills")
        if p is not None:
            _set_leaf(p, write_int(value))

    @property
    def persona_id(self) -> bytes:
        p = _path(self.persona.decoded, "PersonaId", "Value")
        return p.raw_payload if p else b""

    @persona_id.setter
    def persona_id(self, value: bytes):
        p = _path(self.persona.decoded, "PersonaId", "Value")
        if p is not None:
            p.raw_payload = value

    # -- traits ------------------------------------------------------------
    def traits_av(self):
        """The PilotTraits ArrayValue (present even when empty), or None."""
        pt = self.element.get("PilotTraits")
        if pt is None or pt.decoded is None or not hasattr(pt.decoded, "elements"):
            return None
        return pt.decoded

    def traits(self) -> list[str]:
        return _trait_names(self.traits_av())


# ---------------------------------------------------------------------------
# Inventory items (weapons / equipment / ammo)
# ---------------------------------------------------------------------------

def _item_id_field(item: PropertyList):
    """An ItemWeapon uses ItemData.WeaponId, an ItemEquipment uses
    ItemData.EquipmentId. Return the ID-bearing sub-property's name."""
    data = item.get("ItemData")
    if data is None or data.decoded is None:
        return None
    for cand in ("WeaponId", "EquipmentId"):
        if data.decoded.get(cand) is not None:
            return cand
    # fall back: first child that itself has an 'ID' struct
    for p in data.decoded.properties:
        if p.decoded is not None and p.decoded.get("ID") is not None:
            return p.name
    return None


class InventoryItem:
    def __init__(self, element: PropertyList):
        self.element = element
        self._idfield = _item_id_field(element)

    def _id_struct(self):
        return _path(self.element, "ItemData", self._idfield, "ID")

    @property
    def asset_type(self) -> str:
        idp = self._id_struct()
        if idp is None or idp.decoded is None:
            return ""
        nm = _path(idp.decoded, "PrimaryAssetType", "Name")
        return read_fstring_payload(nm.raw_payload) if nm else ""

    @asset_type.setter
    def asset_type(self, value: str):
        idp = self._id_struct()
        nm = _path(idp.decoded, "PrimaryAssetType", "Name")
        if nm is not None:
            _set_leaf(nm, write_fstring_payload(value))

    @property
    def asset_name(self) -> str:
        idp = self._id_struct()
        if idp is None or idp.decoded is None:
            return ""
        nm = idp.decoded.get("PrimaryAssetName")
        return read_fstring_payload(nm.raw_payload) if nm else ""

    @asset_name.setter
    def asset_name(self, value: str):
        idp = self._id_struct()
        nm = idp.decoded.get("PrimaryAssetName")
        if nm is not None:
            _set_leaf(nm, write_fstring_payload(value))

    @property
    def count(self) -> int:
        p = self.element.get("Count")
        return read_int(p.raw_payload) if p else 0

    @count.setter
    def count(self, value: int):
        p = self.element.get("Count")
        if p is not None:
            _set_leaf(p, write_int(value))

    @property
    def guid(self) -> bytes:
        p = _path(self.element, "ItemId", "Value")
        return p.raw_payload if p else b""

    @guid.setter
    def guid(self, value: bytes):
        p = _path(self.element, "ItemId", "Value")
        if p is not None:
            p.raw_payload = value


# ---------------------------------------------------------------------------
# Faction standings
# ---------------------------------------------------------------------------

class FactionStanding:
    def __init__(self, element: PropertyList):
        self.element = element

    @property
    def name(self) -> str:
        p = _path(self.element, "Faction", "ID", "PrimaryAssetName")
        return read_fstring_payload(p.raw_payload) if p else ""

    @property
    def standing(self) -> int:
        p = self.element.get("Standing")
        return read_int(p.raw_payload) if p else 0

    @standing.setter
    def standing(self, value: int):
        p = self.element.get("Standing")
        if p is not None:
            _set_leaf(p, write_int(value))


# ---------------------------------------------------------------------------
# SaveFile
# ---------------------------------------------------------------------------

class SaveFile:
    def __init__(self, data: bytes):
        self._raw = data
        r = Reader(data)
        self.top = read_property_list(r)
        self.trailer = data[r.pos:]

        self.pmd = self.top.get("PersistentModelData")
        pr = Reader(self.pmd.raw_payload)
        length = pr.i32()
        arc = pr.read(length)
        ar = Reader(arc)
        self.model_list = read_property_list(ar)
        self.pmd_footer = arc[ar.pos:]

        self._models: dict[str, ParsedModel] = {}

    @classmethod
    def load(cls, path: str) -> "SaveFile":
        with open(path, "rb") as f:
            return cls(f.read())

    # -- model access ------------------------------------------------------
    def model(self, name: str) -> ParsedModel:
        if name in self._models:
            return self._models[name]
        obj = self.model_list.get(name)
        if obj is None:
            raise KeyError(name)
        mr = Reader(obj.raw_payload)
        class_path = mr.fstring()
        plist = read_property_list(mr)
        footer = obj.raw_payload[mr.pos:]
        pm = ParsedModel(name, obj, class_path, plist, footer)
        self._models[name] = pm
        return pm

    # -- mechs -------------------------------------------------------------
    def _wrappers_array(self) -> ArrayValue:
        return self.model("SaveStateModel").plist.get("MechLoadoutWrappers").decoded

    def _storage_array(self) -> ArrayValue:
        return self.model("MechStorageModel").plist.get("MechStorageList").decoded

    def _all_mechs(self) -> list[Mech]:
        """Every MechLoadoutWrapper that holds a MarketItemMech -- active-bay
        mechs AND market listings AND cold-storage records. Used internally for
        whole-save scans (layouts, referenced items/traits)."""
        out = []
        for el in self._wrappers_array().elements:
            bd = el.get("ByteData")
            br = Reader(bd.raw_payload)
            length = br.i32()
            arc = br.read(length)
            ar = Reader(arc)
            nested = read_property_list(ar)
            footer = arc[ar.pos:]
            if nested.get("MarketItemMech") is not None:
                out.append(Mech(el, bd, nested, footer))
        return out

    def mechs(self) -> list[Mech]:
        """The player's owned, active-bay mechs. Excludes market listings and
        cold-storage records, which share the same array but carry a
        MechLoadoutType marking them as not-owned (see issue #2)."""
        return [m for m in self._all_mechs() if m.is_owned]

    def cold_storage_mechs(self) -> list[Mech]:
        """Mechs in cold storage (modern format). Active-bay mechs are excluded.
        (Legacy InventoryModel.StoredMechInventory is a separate format, not
        yet surfaced here.)"""
        return [m for m in self._all_mechs()
                if m.loadout_type == COLD_STORAGE_LOADOUT_TYPE]

    def chassis_layouts(self) -> dict:
        """Scan the WHOLE save (owned mechs, market listings, mission/post-
        mission records) and return, for each chassis, the REAL hardpoint layout
        with the most hardpoints found:
            { chassis_asset_name: (InstalledWeapons, WeaponGroups, ChainFireGroups) }
        These are genuine chassis layouts the game itself wrote, so applying one
        to a mech of that chassis gives it correct, working hardpoints."""
        best = {}  # chassis -> (count, iw, wg, cfg)

        def consider(ld_decoded):
            mda = _path(ld_decoded, "MechDataAssetId", "ID", "PrimaryAssetName")
            iw = ld_decoded.get("InstalledWeapons")
            if mda is None or iw is None or iw.decoded is None:
                return
            ch = read_fstring_payload(mda.raw_payload)
            n = len(iw.decoded.elements)
            if n > best.get(ch, (0,))[0]:
                wgi = ld_decoded.get("WeaponGroupInfo")
                wg = wgi.decoded.get("WeaponGroups") if wgi and wgi.decoded else None
                cfg = wgi.decoded.get("ChainFireGroups") if wgi and wgi.decoded else None
                best[ch] = (n, iw.decoded,
                            wg.decoded if wg and wg.decoded else None,
                            cfg.decoded if cfg and cfg.decoded else None)

        def scan(pl, depth=0):
            if depth > 60 or pl is None:
                return
            for p in pl.properties:
                if p.name in ("ItemData", "Loadout") and p.decoded is not None \
                        and p.decoded.get("MechDataAssetId") is not None:
                    consider(p.decoded)
                if p.decoded is not None and hasattr(p.decoded, "properties"):
                    scan(p.decoded, depth + 1)
                if p.decoded is not None and hasattr(p.decoded, "elements") \
                        and getattr(p.decoded, "element_type", None) == "StructProperty":
                    for el in p.decoded.elements:
                        if hasattr(el, "properties"):
                            scan(el, depth + 1)

        for name in [pp.name for pp in self.model_list.properties]:
            try:
                scan(self.model(name).plist)
            except Exception:
                pass
        for m in self._all_mechs():
            scan(m.nested)
        return {ch: (v[1], v[2], v[3]) for ch, v in best.items()}

    def referenced_items(self) -> dict:
        """Scan the WHOLE save for every weapon / equipment / ammo asset it
        references (owned mechs, inventory, market, mission records, enemy
        loadouts...) and return them grouped for the editor:

            {"weapon": [(name, type), ...],
             "equipment": [(name, type), ...],
             "ammo": [(name, type), ...]}

        Every name here is one the game itself wrote, so it's a guaranteed-valid
        asset id -- this is how rare/DLC gear becomes available to add: as soon as
        you've seen it in a market or mission, it shows up in the dropdowns."""
        WEAPON_T = {"MWTraceWeaponDataAsset", "MWProjectileWeaponDataAsset",
                    "MWMissileWeaponDataAsset", "MWMeleeWeaponDataAsset",
                    "MWAMSWeaponDataAsset"}
        EQUIP_T = {"MWHeatSinkDataAsset", "MWJumpJetDataAsset", "MWMASCDataAsset",
                   "MWECMDataAsset", "MWBAPDataAsset", "MWTargetingComputerDataAsset"}
        out = {"weapon": set(), "equipment": set(), "ammo": set()}

        def scan(pl, depth=0):
            if depth > 60 or pl is None:
                return
            for p in pl.properties:
                if p.name == "ID" and p.decoded is not None:
                    pat = p.decoded.get("PrimaryAssetType")
                    nam = p.decoded.get("PrimaryAssetName")
                    if pat is not None and nam is not None and pat.decoded is not None:
                        tn = pat.decoded.get("Name")
                        if tn is not None:
                            t = read_fstring_payload(tn.raw_payload)
                            n = read_fstring_payload(nam.raw_payload)
                            if n and n != "None":
                                if t in WEAPON_T:
                                    out["weapon"].add((n, t))
                                elif t == "MWAmmoDataAsset":
                                    out["ammo"].add((n, t))
                                elif t in EQUIP_T:
                                    out["equipment"].add((n, t))
                if p.decoded is not None and hasattr(p.decoded, "properties"):
                    scan(p.decoded, depth + 1)
                if p.decoded is not None and hasattr(p.decoded, "elements") \
                        and getattr(p.decoded, "element_type", None) == "StructProperty":
                    for el in p.decoded.elements:
                        if hasattr(el, "properties"):
                            scan(el, depth + 1)

        for name in [pp.name for pp in self.model_list.properties]:
            try:
                scan(self.model(name).plist)
            except Exception:
                pass
        for m in self._all_mechs():
            scan(m.nested)
        return {k: sorted(v) for k, v in out.items()}

    def _wrapper_chassis(self, el: PropertyList) -> str | None:
        """Read a MechLoadoutWrapper element's chassis asset name (PrimaryAssetName)."""
        bd = el.get("ByteData")
        if bd is None:
            return None
        br = Reader(bd.raw_payload)
        length = br.i32()
        nested = read_property_list(Reader(br.read(length)))
        mi = nested.get("MarketItemMech")
        if mi is None or mi.decoded is None:
            return None
        nm = _path(mi.decoded, "Item", "ItemData", "MechDataAssetId", "ID", "PrimaryAssetName")
        return read_fstring_payload(nm.raw_payload) if nm else None

    def _mech_from_element(self, el: PropertyList) -> Mech:
        bd = el.get("ByteData")
        br = Reader(bd.raw_payload)
        length = br.i32()
        arc = br.read(length)
        ar = Reader(arc)
        nested = read_property_list(ar)
        footer = arc[ar.pos:]
        return Mech(el, bd, nested, footer)

    def _mech_loadout_type_template(self):
        """A deep-copyable MechLoadoutType EnumProperty harvested from any
        market or cold-storage wrapper, used to graft the cold-storage marker
        onto a mech that doesn't have one. None if the save has neither."""
        if getattr(self, "_mlt_tmpl", "_") == "_":
            tmpl = None
            for el in self._wrappers_array().elements:
                p = self._mech_from_element(el).nested.get("MechLoadoutType")
                if p is not None:
                    tmpl = copy.deepcopy(p)
                    break
            self._mlt_tmpl = tmpl
        return self._mlt_tmpl

    def _loadout_scaffolds(self):
        """Deep-copyable scaffold elements harvested from any mech, used to
        rebuild a stock loadout: (weapon element, weapon-group element,
        equipment-part element, equipment-item element). Any may be None if no
        mech in the save provides that structure. Cached."""
        if getattr(self, "_ld_scaffold", "_") == "_":
            we = ge = pe = ie = None
            for m in self._all_mechs():
                ld = _path(m.market_item.decoded, "Item", "ItemData")
                if ld is None or ld.decoded is None:
                    continue
                iw = ld.decoded.get("InstalledWeapons")
                if we is None and iw is not None and iw.decoded is not None \
                        and getattr(iw.decoded, "elements", None):
                    we = copy.deepcopy(iw.decoded.elements[0])
                wgi = ld.decoded.get("WeaponGroupInfo")
                if ge is None and wgi is not None and wgi.decoded is not None:
                    wg = wgi.decoded.get("WeaponGroups")
                    if wg is not None and wg.decoded is not None \
                            and getattr(wg.decoded, "elements", None):
                        ge = copy.deepcopy(wg.decoded.elements[0])
                eq = ld.decoded.get("Equipment")
                mpe = eq.decoded.get("MechPartEquipment") if eq and eq.decoded else None
                if mpe is not None and mpe.decoded is not None and getattr(mpe.decoded, "elements", None):
                    if pe is None:
                        pe = copy.deepcopy(mpe.decoded.elements[0])
                    if ie is None:
                        for pel in mpe.decoded.elements:
                            se = pel.get("SlottedEquipment")
                            if se is not None and se.decoded is not None \
                                    and getattr(se.decoded, "elements", None):
                                ie = copy.deepcopy(se.decoded.elements[0])
                                break
                if we is not None and ge is not None and pe is not None and ie is not None:
                    break
            self._ld_scaffold = (we, ge, pe, ie)
        return self._ld_scaffold

    def add_mech(self, chassis: str | None = None, *, donor_index: int = 0,
                 repair: bool = True, location: str = "active") -> tuple[bytes, str]:
        """Add a mech, returning (new_guid, status).

        `location`:
        - "active": goes into the active mech bay (registered in
          MechStorageList). NOTE: if the in-game bay is full the game can't place
          it and it won't appear -- use "cold" in that case.
        - "cold": goes into Cold Storage (MechLoadoutType = ColdStorageLoadout,
          NOT in MechStorageList). Always safe regardless of bay capacity; the
          player can move it to the bay in-game if there's room.

        Hybrid clone strategy (both locations):
        - If you already OWN a mech of `chassis` with a real loadout, clone THAT
          (exact, fully-working duplicate)                       -> status "exact".
        - Otherwise clone a donor, rename to `chassis`, repair, and STRIP its
          loadout so it carries no stale weapon groups            -> status "approx".
        `chassis` is the MechDataAsset PrimaryAssetName, e.g. "AS7-D_MDA"."""
        wrappers = self._wrappers_array()
        storage = self._storage_array()
        new_guid = uuid.uuid4().bytes
        status = "approx"
        cold = (location == "cold")

        # Always clone an ACTIVE-bay donor: only active mechs carry the full
        # ItemData (InstalledWeapons, Equipment) we populate from. Cold-storage
        # records can omit those arrays, so they're useless as donors. For a cold
        # add we add the ColdStorageLoadout marker afterward (set_cold_storage).
        src_index = donor_index
        for i, el in enumerate(wrappers.elements):
            if self._mech_from_element(el).is_owned:
                src_index = i
                break

        want = (chassis if chassis.endswith("_MDA") else chassis + "_MDA") if chassis else None

        # Tier 1: an owned mech of the exact chassis with a non-empty loadout is
        # a perfect template -- duplicate it verbatim.
        if want:
            for i, el in enumerate(wrappers.elements):
                if self._wrapper_chassis(el) == want and \
                        self._mech_from_element(el).installed_weapon_count() > 0:
                    src_index = i
                    status = "exact"
                    break

        clone_el = copy.deepcopy(wrappers.elements[src_index])
        mech = self._mech_from_element(clone_el)
        mech.guid = new_guid
        if status == "exact":
            if repair:
                mech.repair()
        else:
            if chassis:
                mech.chassis = chassis
            tpl = stock_template(chassis) if chassis else None
            if tpl is not None:
                # Best: populate the chassis's REAL stock loadout (correct armor,
                # structure, weapons, weapon groups and equipment) from the
                # game-asset template, instead of an approximate clone of an
                # unrelated donor.
                we, ge, pe, ie = self._loadout_scaffolds()
                mech.apply_stock_template(tpl, we, ge)
                if not mech.apply_stock_equipment(tpl, pe, ie):
                    mech.strip_equipment()   # couldn't populate; avoid donor's gear
                status = "stock"
            else:
                if repair:
                    mech.repair()
                # If the save has a REAL layout for this chassis, use it; else keep
                # the donor's hardpoints emptied (no stale weapon groups).
                layout = self.chassis_layouts().get(want) if want else None
                if layout is not None and layout[0] is not None and \
                        len(layout[0].elements) > mech.installed_weapon_count():
                    mech.apply_layout(*layout)
                    status = "real-layout"
                else:
                    mech.strip_weapons()
                # The donor's equipment belongs to the donor chassis; carrying it
                # over produces phantom gear (tonnage-eating jump jets, etc.).
                mech.strip_equipment()

        # Normalise the wrapper to the requested location.
        if cold:
            mech.set_cold_storage(self._mech_loadout_type_template())
        else:
            mech.clear_loadout_type()   # ensure active (donor may have been cold/market)
        mech.flush()

        wrappers.elements.append(clone_el)
        wrappers.count += 1

        # Only active-bay mechs are registered in MechStorageList; cold storage
        # records are identified solely by their MechLoadoutType.
        if not cold:
            slot = copy.deepcopy(storage.elements[0])
            slot.get("Value").raw_payload = new_guid
            storage.elements.append(slot)
            storage.count += 1
        return new_guid, status

    def export_mech_loadout(self, mech: "Mech", path: str) -> dict:
        """Write a single mech's loadout to a portable .mw5loadout file."""
        data = mech.export_loadout()
        data["format"] = "mw5loadout"
        data["version"] = 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data

    def import_mech_loadout(self, mech: "Mech", path: str) -> str:
        """Apply a saved .mw5loadout onto a mech (overwrites its loadout).
        Returns the chassis the loadout was exported from (for a mismatch
        warning). Best used on the same chassis -- the hardpoint ids must match."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("format") != "mw5loadout":
            raise ValueError("Not a MW5 loadout file.")
        we, ge, pe, ie = self._loadout_scaffolds()
        mech.apply_stock_template(data, we, ge)
        if not mech.apply_stock_equipment(data, pe, ie):
            mech.strip_equipment()
        for i, on in enumerate(data.get("chainFire", []), start=1):
            mech.set_chain_fire_group(i, on)
        mech.flush()
        return data.get("chassis", "")

    def reset_mech_to_stock(self, mech: "Mech") -> bool:
        """Reset an existing mech to its chassis's factory-stock loadout (armor,
        structure, weapons, weapon groups, equipment) from the stock template.
        Returns False if there's no template for the chassis."""
        tpl = stock_template(mech.chassis)
        if tpl is None:
            return False
        we, ge, pe, ie = self._loadout_scaffolds()
        mech.apply_stock_template(tpl, we, ge)
        if not mech.apply_stock_equipment(tpl, pe, ie):
            mech.strip_equipment()
        mech.flush()
        return True

    def remove_mech(self, guid: bytes):
        wrappers = self._wrappers_array()
        for i, el in enumerate(wrappers.elements):
            bd = el.get("ByteData")
            br = Reader(bd.raw_payload)
            length = br.i32()
            arc = br.read(length)
            nested = read_property_list(Reader(arc))
            mi = nested.get("MarketItemMech")
            g = _path(mi.decoded, "Item", "ItemId", "Value") if mi else None
            if g is not None and g.raw_payload == guid:
                del wrappers.elements[i]
                wrappers.count -= 1
                break
        storage = self._storage_array()
        for j, slot in enumerate(storage.elements):
            if slot.get("Value").raw_payload == guid:
                del storage.elements[j]
                storage.count -= 1
                break

    # -- pilots ------------------------------------------------------------
    def pilots(self) -> list[Pilot]:
        roster = self.model("RosterModel").plist.get("PilotRoster").decoded
        return [Pilot(el) for el in roster.elements]

    def add_pilot(self, callsign: str, full_name: str | None = None,
                  skills: dict | None = None, salary: int = 10000,
                  hiring_cost: int = 0) -> "Pilot":
        """Add a new pilot to the roster by cloning a regular (non-commander)
        pilot, stamping a fresh PersonaId GUID, and applying name + skills.

        skills: {skill_name: total_exp}; any omitted skill keeps the donor's
        value. Returns the new Pilot."""
        roster = self.model("RosterModel").plist.get("PilotRoster").decoded
        # pick a non-commander donor (LockedPlayerSlot == ...::None)
        donor_idx = 0
        for i, el in enumerate(roster.elements):
            slot = el.get("LockedPlayerSlot")
            if slot is not None and slot.raw_payload.find(b"::None") != -1:
                donor_idx = i
                break
        clone = copy.deepcopy(roster.elements[donor_idx])
        pilot = Pilot(clone)
        pilot.persona_id = uuid.uuid4().bytes
        pilot.callsign = callsign
        pilot.full_name = full_name if full_name is not None else callsign
        if skills:
            for name, exp in skills.items():
                pilot.set_skill(name, int(exp))
        pilot.salary = salary
        pilot.hiring_cost = hiring_cost
        roster.elements.append(clone)
        roster.count += 1
        return pilot

    def remove_pilot(self, persona_id: bytes):
        roster = self.model("RosterModel").plist.get("PilotRoster").decoded
        for i, el in enumerate(roster.elements):
            if Pilot(el).persona_id == persona_id:
                del roster.elements[i]
                roster.count -= 1
                break

    # -- traits ------------------------------------------------------------
    def _find_array_prop(self, names: set[str], need_elements: bool):
        """Find the first decoded ArrayProperty whose name is in `names`
        (optionally requiring >=1 element), scanning all models then owned
        mechs. Used to harvest real trait-array structures to clone from."""
        found = [None]

        def scan(pl, depth=0):
            if found[0] is not None or pl is None or depth > 60 or not hasattr(pl, "properties"):
                return
            for p in pl.properties:
                if p.name in names and p.decoded is not None and hasattr(p.decoded, "elements"):
                    if not need_elements or p.decoded.elements:
                        found[0] = p
                        return
                d = p.decoded
                if d is not None and hasattr(d, "properties"):
                    scan(d, depth + 1)
                if d is not None and hasattr(d, "elements") \
                        and getattr(d, "element_type", None) == "StructProperty":
                    for el in d.elements:
                        if hasattr(el, "properties"):
                            scan(el, depth + 1)

        for name in [pp.name for pp in self.model_list.properties]:
            try:
                scan(self.model(name).plist)
            except Exception:
                pass
            if found[0] is not None:
                return found[0]
        for m in self._all_mechs():
            scan(m.nested)
            if found[0] is not None:
                return found[0]
        return found[0]

    def _trait_element_template(self):
        """A deep-copyable trait element (a PropertyList with one `ID` struct).
        Pilot and mech trait elements share this shape, so any one works."""
        if getattr(self, "_trait_el_tmpl", "_") == "_":
            p = self._find_array_prop({"PilotTraits", "InstalledTraits"}, True)
            self._trait_el_tmpl = copy.deepcopy(p.decoded.elements[0]) if p else None
        return self._trait_el_tmpl

    def _installed_traits_wrapper(self):
        """A deep-copyable InstalledTraits array-property wrapper, for grafting
        onto an owned mech that has none. Prefer a real (possibly empty)
        InstalledTraits from a post-mission record; fall back to a PilotTraits
        wrapper (same StructProperty-array framing, relabelled on graft)."""
        if getattr(self, "_it_wrap_tmpl", "_") == "_":
            p = (self._find_array_prop({"InstalledTraits"}, False)
                 or self._find_array_prop({"PilotTraits"}, False))
            self._it_wrap_tmpl = copy.deepcopy(p) if p else None
        return self._it_wrap_tmpl

    def referenced_traits(self) -> dict:
        """Every pilot/mech trait the save references (the player's pilots, all
        NPC/market personas, mech records...). Gives the editor a dropdown of
        guaranteed-valid trait asset names the save has actually seen:

            {"pilot": [name, ...], "mech": [name, ...]}
        """
        out = {"pilot": set(), "mech": set()}

        def scan(pl, depth=0):
            if depth > 60 or pl is None or not hasattr(pl, "properties"):
                return
            for p in pl.properties:
                if p.name == "ID" and p.decoded is not None:
                    pat = p.decoded.get("PrimaryAssetType")
                    nam = p.decoded.get("PrimaryAssetName")
                    if pat is not None and nam is not None and pat.decoded is not None:
                        tn = pat.decoded.get("Name")
                        if tn is not None:
                            t = read_fstring_payload(tn.raw_payload)
                            n = read_fstring_payload(nam.raw_payload)
                            if n and n != "None":
                                if t == PILOT_TRAIT_TYPE:
                                    out["pilot"].add(n)
                                elif t == MECH_TRAIT_TYPE:
                                    out["mech"].add(n)
                if p.decoded is not None and hasattr(p.decoded, "properties"):
                    scan(p.decoded, depth + 1)
                if p.decoded is not None and hasattr(p.decoded, "elements") \
                        and getattr(p.decoded, "element_type", None) == "StructProperty":
                    for el in p.decoded.elements:
                        if hasattr(el, "properties"):
                            scan(el, depth + 1)

        for name in [pp.name for pp in self.model_list.properties]:
            try:
                scan(self.model(name).plist)
            except Exception:
                pass
        for m in self._all_mechs():
            scan(m.nested)
        return {k: sorted(v) for k, v in out.items()}

    def add_pilot_trait(self, pilot: "Pilot", name: str,
                        type_name: str = PILOT_TRAIT_TYPE) -> bool:
        """Add a trait to a pilot (no-op if already present). Returns True if
        added. Raises if the save has no trait element anywhere to clone."""
        av = pilot.traits_av()
        if av is None:
            raise RuntimeError("This pilot has no PilotTraits array to add to.")
        tmpl = self._trait_element_template()
        if tmpl is None:
            raise RuntimeError("No trait in this save to use as a template.")
        return _trait_add(av, tmpl, name, type_name)

    def remove_pilot_trait(self, pilot: "Pilot", name: str) -> bool:
        return _trait_remove(pilot.traits_av(), name)

    def add_mech_trait(self, mech: "Mech", name: str,
                       type_name: str = MECH_TRAIT_TYPE, flush: bool = True) -> bool:
        """Best-effort: install a (Cantina-style) trait on a mech. Grafts an
        InstalledTraits array if the mech has none. Experimental -- mech traits
        couldn't be verified in-game; pass flush=False when an outer caller
        (the loadout dialog) flushes the nested archive itself."""
        av = mech.ensure_installed_traits(self._installed_traits_wrapper())
        if av is None:
            raise RuntimeError("Couldn't create an InstalledTraits array on this mech.")
        tmpl = self._trait_element_template()
        if tmpl is None:
            raise RuntimeError("No trait in this save to use as a template.")
        ok = _trait_add(av, tmpl, name, type_name)
        if ok and flush:
            mech.flush()
        return ok

    def remove_mech_trait(self, mech: "Mech", name: str, flush: bool = True) -> bool:
        ok = _trait_remove(mech.installed_traits_av(), name)
        if ok and flush:
            mech.flush()
        return ok

    # -- inventory ---------------------------------------------------------
    def _inventory_array(self, which: str) -> ArrayValue:
        """which = 'weapon' | 'equipment'."""
        inv = self.model("InventoryModel").plist
        struct_name = "WeaponInventory" if which == "weapon" else "EquipmentInventory"
        return inv.get(struct_name).decoded.get("Items").decoded

    def weapon_inventory(self) -> list[InventoryItem]:
        return [InventoryItem(el) for el in self._inventory_array("weapon").elements]

    def equipment_inventory(self) -> list[InventoryItem]:
        return [InventoryItem(el) for el in self._inventory_array("equipment").elements]

    def add_item(self, inventory: str, asset_type: str, asset_name: str,
                 count: int = 1) -> bytes:
        """Add (or top-up) an item in WeaponInventory or EquipmentInventory.

        inventory = 'weapon' | 'equipment'. If an item with the same asset
        name already exists, its count is increased instead of adding a dup.
        Returns the item's GUID."""
        arr = self._inventory_array(inventory)
        # top-up if already present
        for el in arr.elements:
            it = InventoryItem(el)
            if it.asset_name == asset_name and it.asset_type == asset_type:
                it.count = it.count + count
                return it.guid
        if not arr.elements:
            raise RuntimeError(f"{inventory} inventory is empty; no template to clone")
        clone = copy.deepcopy(arr.elements[0])
        item = InventoryItem(clone)
        new_guid = uuid.uuid4().bytes
        item.guid = new_guid
        item.asset_type = asset_type
        item.asset_name = asset_name
        item.count = count
        arr.elements.append(clone)
        arr.count += 1
        return new_guid

    def remove_item(self, inventory: str, asset_name: str):
        arr = self._inventory_array(inventory)
        for i, el in enumerate(arr.elements):
            if InventoryItem(el).asset_name == asset_name:
                del arr.elements[i]
                arr.count -= 1
                break

    # -- factions / reputation --------------------------------------------
    def factions(self) -> list[FactionStanding]:
        mc = self.model("MercCompanyModel").plist
        fsl = mc.get("FactionStandingList")
        arr = fsl.decoded.get("Standings").decoded
        return [FactionStanding(el) for el in arr.elements]

    @property
    def reputation(self) -> int:
        p = self.model("MercCompanyModel").plist.get("Reputation")
        return read_int(p.raw_payload) if p else 0

    @reputation.setter
    def reputation(self, value: int):
        p = self.model("MercCompanyModel").plist.get("Reputation")
        if p is not None:
            _set_leaf(p, write_int(value))

    # -- C-Bills -----------------------------------------------------------
    @property
    def cbills(self) -> int:
        p = _path(self.model("InventoryModel").plist, "AvailableCBills", "Value")
        return struct.unpack("<q", p.raw_payload[:8])[0] if p else 0

    @cbills.setter
    def cbills(self, value: int):
        p = _path(self.model("InventoryModel").plist, "AvailableCBills", "Value")
        if p is not None:
            _set_leaf(p, struct.pack("<q", value))

    # -- export / import (transfer between saves) --------------------------
    def _sample_owner_payload(self) -> bytes | None:
        """An existing mech wrapper's 'Owner' ObjectProperty payload (a ref to
        this save's persistent model). Used to fix imported mechs' Owner refs."""
        for el in self._wrappers_array().elements:
            owner = el.get("Owner")
            if owner is not None and owner.raw_payload:
                return owner.raw_payload
        return None

    def export_to(self, path: str, *, mechs=True, pilots=True, inventory=True,
                  cbills=True, factions=True) -> dict:
        """Write selected content to a portable .mw5export file (JSON + base64
        element blobs) that import_from() can add into another save."""
        data = {"format": "mw5export", "version": 1}
        if mechs:
            out = []
            for m in self.mechs():
                w = Writer()
                write_property_list(w, m.element)
                out.append({"chassis": m.chassis,
                            "blob": base64.b64encode(w.bytes()).decode("ascii")})
            # Cold-storage mechs live in the same wrapper array but carry a
            # ColdStorageLoadout marker, so self.mechs() (active bay only)
            # skips them. Export them too (issue #10) -- the marker rides along
            # in the blob, and import_from() detects it to restore cold status.
            for m in self.cold_storage_mechs():
                w = Writer()
                write_property_list(w, m.element)
                out.append({"chassis": m.chassis, "cold": True,
                            "blob": base64.b64encode(w.bytes()).decode("ascii")})
            data["mechs"] = out
        if pilots:
            out = []
            for p in self.pilots():
                w = Writer()
                write_property_list(w, p.element)
                out.append({"callsign": p.callsign,
                            "blob": base64.b64encode(w.bytes()).decode("ascii")})
            data["pilots"] = out
        if inventory:
            data["weapons"] = [[i.asset_name, i.asset_type, i.count] for i in self.weapon_inventory()]
            data["equipment"] = [[i.asset_name, i.asset_type, i.count] for i in self.equipment_inventory()]
        if cbills:
            data["cbills"] = self.cbills
        if factions:
            data["reputation"] = self.reputation
            data["factions"] = {f.name: f.standing for f in self.factions()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return {"mechs": len(data.get("mechs", [])), "pilots": len(data.get("pilots", [])),
                "weapons": len(data.get("weapons", [])), "equipment": len(data.get("equipment", []))}

    def import_from(self, path: str, *, mechs=True, pilots=True, inventory=True,
                    cbills=True, factions=True) -> dict:
        """Add content from a .mw5export file into THIS save. Mechs/pilots get
        fresh GUIDs (and mechs a fixed Owner ref + a storage slot), so they
        coexist with whatever's already here."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("format") != "mw5export":
            raise ValueError("Not a MW5 export file.")
        summary = {"mechs": 0, "pilots": 0, "items": 0}

        if mechs and data.get("mechs"):
            wrappers = self._wrappers_array()
            storage = self._storage_array()
            owner_payload = self._sample_owner_payload()
            for entry in data["mechs"]:
                el = read_property_list(Reader(base64.b64decode(entry["blob"])))
                new_guid = uuid.uuid4().bytes
                m = self._mech_from_element(el)
                m.guid = new_guid
                owner = el.get("Owner")
                if owner is not None and owner_payload is not None:
                    _set_leaf(owner, owner_payload)
                m.flush()
                wrappers.elements.append(el)
                wrappers.count += 1
                # Active-bay mechs are registered in MechStorageList; cold-storage
                # records are NOT (issue #10). Detect cold status from the imported
                # element itself (the ColdStorageLoadout marker rode along in the
                # blob) so an exported cold mech comes back into cold storage.
                if m.loadout_type != COLD_STORAGE_LOADOUT_TYPE:
                    slot = copy.deepcopy(storage.elements[0])
                    slot.get("Value").raw_payload = new_guid
                    storage.elements.append(slot)
                    storage.count += 1
                summary["mechs"] += 1

        if pilots and data.get("pilots"):
            roster = self.model("RosterModel").plist.get("PilotRoster").decoded
            for entry in data["pilots"]:
                el = read_property_list(Reader(base64.b64decode(entry["blob"])))
                Pilot(el).persona_id = uuid.uuid4().bytes
                roster.elements.append(el)
                roster.count += 1
                summary["pilots"] += 1

        if inventory:
            for name, atype, count in data.get("weapons", []):
                self.add_item("weapon", atype, name, count)
                summary["items"] += 1
            for name, atype, count in data.get("equipment", []):
                self.add_item("equipment", atype, name, count)
                summary["items"] += 1

        if cbills and "cbills" in data:
            self.cbills = data["cbills"]

        if factions:
            if "reputation" in data:
                self.reputation = data["reputation"]
            fmap = {f.name: f for f in self.factions()}
            for name, standing in data.get("factions", {}).items():
                if name in fmap:
                    fmap[name].standing = standing

        return summary

    # -- save --------------------------------------------------------------
    def to_bytes(self) -> bytes:
        # 1. reserialize any parsed/edited models
        for pm in self._models.values():
            pm.reserialize()
        # 2. rebuild PersistentModelData archive (+ footer)
        aw = Writer()
        write_property_list(aw, self.model_list)
        aw.write(self.pmd_footer)
        archive_bytes = aw.bytes()
        pw = Writer()
        pw.i32(len(archive_bytes))
        pw.write(archive_bytes)
        self.pmd.raw_payload = pw.bytes()
        self.pmd.decoded = None
        # 3. top level (+ trailer)
        ow = Writer()
        write_property_list(ow, self.top)
        return ow.bytes() + self.trailer

    def save(self, path: str):
        data = self.to_bytes()
        with open(path, "wb") as f:
            f.write(data)
        return data
