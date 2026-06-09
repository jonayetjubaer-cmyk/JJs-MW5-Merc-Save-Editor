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

import copy
import struct
import uuid
from dataclasses import dataclass, field

from ue_property import (
    Reader, Writer, read_property_list, write_property_list,
    Property, PropertyList, ArrayValue,
)


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
        m = _re.match(r"^([EBM])H\d+$", tok)
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
        # Structure: many saves only store CurrentStructure; if there's an
        # "InstalledStructure" use it, else max out from CurrentStructure's own
        # values is impossible, so leave structure if no install reference.
        if ld.get("InstalledStructure") is not None:
            copy_struct("InstalledStructure", "CurrentStructure", ARMOR_PARTS)

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

    def max_armor(self):
        """Set CurrentArmor = InstalledArmor for every location (front + rear)."""
        for loc in ARMOR_PARTS:
            self.set_armor(loc, self.armor_value(loc, installed=True))
        for loc in REAR_PARTS:
            self.set_armor(loc, self.armor_value(loc, installed=True))

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

    def mechs(self) -> list[Mech]:
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
        for m in self.mechs():
            scan(m.nested)
        return {ch: (v[1], v[2], v[3]) for ch, v in best.items()}

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

    def add_mech(self, chassis: str | None = None, *, donor_index: int = 0,
                 repair: bool = True) -> tuple[bytes, str]:
        """Add a mech, returning (new_guid, status).

        Hybrid strategy:
        - If you already OWN a mech of `chassis` that has a real loadout, clone
          THAT (an exact, fully-working duplicate)             -> status "exact".
        - Otherwise clone a donor mech, rename it to `chassis`, repair it, and
          STRIP its loadout (clear_loadout) so it doesn't carry the donor's
          stale weapon groups; the player refits it in the Mech Lab
                                                                -> status "approx".
        `chassis` is the MechDataAsset PrimaryAssetName, e.g. "AS7-D_MDA"."""
        wrappers = self._wrappers_array()
        storage = self._storage_array()
        new_guid = uuid.uuid4().bytes
        status = "approx"
        src_index = donor_index

        want = (chassis if chassis.endswith("_MDA") else chassis + "_MDA") if chassis else None

        # Tier 1: an owned mech of the exact chassis, with a non-empty loadout,
        # is a perfect template -- duplicate it verbatim.
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
            if repair:
                mech.repair()
            # If the save has a REAL layout for this chassis (from a market /
            # mission record), use it so the mech gets correct hardpoints.
            # Otherwise keep the donor's hardpoints, emptied (no stale groups).
            layout = self.chassis_layouts().get(want) if want else None
            if layout is not None and layout[0] is not None and \
                    len(layout[0].elements) > mech.installed_weapon_count():
                mech.apply_layout(*layout)
                status = "real-layout"
            else:
                mech.strip_weapons()
        mech.flush()

        wrappers.elements.append(clone_el)
        wrappers.count += 1

        slot = copy.deepcopy(storage.elements[0])
        slot.get("Value").raw_payload = new_guid
        storage.elements.append(slot)
        storage.count += 1
        return new_guid, status

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
