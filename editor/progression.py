"""Saved objective, Arena Fame and Rival Intel records.

Stock level thresholds come from ArenaFameProgressionTable and
BountyHunterProgressionData in the DLC9-era game packages.
"""
from bisect import bisect_right
from datetime import datetime, timezone
import struct

from catalog_source import load_catalog
from savefile import (
    _checked_struct_array, _int_property, _new_asset_id, _new_struct_array,
    _new_struct_property, _path, _set_leaf, read_fstring_payload, read_int,
    write_int,
)
from ue_property import PropertyList

POINT_TRACKS = {
    "arena": ("ArenaFameModel", "ArenaFamePoints",
              (0, 100, 225, 375, 550, 750, 975, 1225, 1500, 1800, 2125)),
    "rival": ("BountyHunterModel", "BountyHunterPoints",
              (0, 100, 750, 1850, 3000, 4500, 6250, 9200, 13000, 18000, 24000)),
}
RIVALS = {
    "BlackHeartsData": "Blackhearts",
    "BrionsLegionData": "Brion's Legion",
    "CraterCobrasData": "Crater Cobras",
    "EridaniLightHorseData": "Eridani Light Horse",
    "FilthyLucreData": "Filthy Lucre",
    "GrayDeathLegionData": "Gray Death Legion",
    "GreggsLongstridersData": "Gregg's Longstriders",
    "HansensRoughridersData": "Hansen's Roughriders",
    "HarlocksWarriorsData": "Harlock's Warriors",
    "KellHoundsData": "Kell Hounds",
    "LindonsCompanyData": "Lindon's Company",
    "McCarronsArmoredCavalryData": "McCarron's Armored Cavalry",
    "MobileFireData": "Mobile Fire",
    "NorthwindHighlandersData": "Northwind Highlanders",
    "TheBadDreamData": "The Bad Dream",
    "ThumpersData": "Thumpers",
    "WacoRangersData": "Waco Rangers",
    "WolfsDragoonsData": "Wolf's Dragoons",
}


def _point_property(save, track):
    model, field, _ = POINT_TRACKS[track]
    plist = save.model(model).plist
    prop = plist.get(field)
    if prop is not None and (prop.type != "IntProperty" or len(prop.raw_payload) != 4):
        raise ValueError(f"Unsupported {field} value.")
    return plist, field, prop


def points(save, track):
    _, _, prop = _point_property(save, track)
    return read_int(prop.raw_payload) if prop is not None else 0


def stock_level(track, value):
    return max(0, bisect_right(POINT_TRACKS[track][2], value) - 1)


def set_points(save, track, value):
    if not 0 <= value <= 2_147_483_647:
        raise ValueError("Points must be between 0 and 2,147,483,647.")
    plist, field, prop = _point_property(save, track)
    if prop is None:
        if value:
            plist.properties.append(_int_property(field, value))
    else:
        _set_leaf(prop, write_int(value))


def set_level(save, track, level):
    thresholds = POINT_TRACKS[track][2]
    if not 0 <= level < len(thresholds):
        raise ValueError("Stock level must be between 0 and 10.")
    if stock_level(track, points(save, track)) != level:
        set_points(save, track, thresholds[level])


def _asset_name(record, asset_type, *path):
    name = _path(record, *path, "ID", "PrimaryAssetName")
    kind = _path(record, *path, "ID", "PrimaryAssetType", "Name")
    if (name is None or kind is None or name.type != "NameProperty"
            or kind.type != "NameProperty" or read_fstring_payload(kind.raw_payload) != asset_type):
        raise ValueError(f"Unsupported {asset_type} reference.")
    value = read_fstring_payload(name.raw_payload)
    if not value or value == "None":
        raise ValueError(f"Missing {asset_type} asset name.")
    return value


def _records(plist, field, struct_name, asset_type, *path):
    prop = plist.get(field)
    if prop is None:
        return {}
    records = {}
    for element in _checked_struct_array(prop, struct_name).elements:
        name = _asset_name(element, asset_type, *path)
        key = name.casefold()
        if key in records:
            raise ValueError(f"Duplicate asset in {field}: {name}.")
        records[key] = (name, element)
    return records


def _remove_record(plist, field, record):
    prop = plist.get(field)
    array = prop.decoded
    array.elements.remove(record)
    array.count = len(array.elements)
    if not array.count:
        plist.properties.remove(prop)


def _append_record(plist, field, struct_name, record):
    prop = plist.get(field)
    if prop is None:
        prop = _new_struct_array(field, struct_name)
        plist.properties.append(prop)
    array = prop.decoded
    array.elements.append(record)
    array.count = len(array.elements)


def _rival_records(plist, field):
    return _records(plist, field, "RivalMercEntry", "MWRivalMercDataAsset", "RivalMercDataId")


def rival_states(save):
    plist = save.model("BountyHunterModel").plist
    encountered = _rival_records(plist, "RivalMercsEncountered")
    defeated = _rival_records(plist, "RivalMercsDefeated")
    names = {key.casefold(): key for key in RIVALS}
    names.update({key: value[0] for key, value in (encountered | defeated).items()})
    return [(name, key in encountered, key in defeated) for key, name in names.items()]


def set_encountered(save, name, enabled):
    plist = save.model("BountyHunterModel").plist
    field = "RivalMercsEncountered"
    encountered = _rival_records(plist, field)
    defeated = _rival_records(plist, "RivalMercsDefeated")
    key = name.casefold()
    if key in encountered:
        if not enabled:
            _remove_record(plist, field, encountered[key][1])
        return
    if not enabled:
        return
    stock = next((asset for asset in RIVALS if asset.casefold() == key), None)
    if key not in defeated and stock is None:
        raise ValueError("Unknown rival mercenary asset.")
    name = defeated[key][0] if key in defeated else stock
    elapsed = datetime.now(timezone.utc) - datetime(1, 1, 1, tzinfo=timezone.utc)
    ticks = ((elapsed.days * 86400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds) * 10
    date = _new_struct_property("Date", "DateTime", [])
    date.decoded = None
    date.raw_payload = struct.pack("<q", ticks)
    _append_record(plist, field, "RivalMercEntry", PropertyList([
        _new_asset_id("RivalMercDataId", "RivalMercDataAssetId", "MWRivalMercDataAsset", name),
        date,
    ]))


QUEST_STRUCT = "MetagameObjectiveAssetId"
QUEST_ASSET = "MWMetagameObjectiveAsset"
# Screen titles from stock MWMetagameObjectiveAsset packages and Game.locres.
_QUEST_TITLES = load_catalog("quest_titles")


def quest_title(asset_id: str, language: str) -> str:
    if not isinstance(_QUEST_TITLES, dict):
        return asset_id
    key = asset_id.casefold()
    for code in (language, "en"):
        titles = _QUEST_TITLES.get(code)
        title = titles.get(key) if isinstance(titles, dict) else None
        if isinstance(title, str) and title.strip():
            return title
    return asset_id


def _quest_records(plist, field):
    return _records(plist, field, QUEST_STRUCT, QUEST_ASSET)


def quest_states(save):
    plist = save.model("MetagameObjectiveModel").plist
    active = _quest_records(plist, "ObjectiveList")
    completed = _quest_records(plist, "CompletedList")
    if active.keys() & completed.keys():
        raise ValueError("The save lists an objective as both active and completed.")
    return [(name, key in completed) for key, (name, _) in (active | completed).items()]


def set_quest_completed(save, name, enabled):
    """Move a saved objective between its active and completed log lists."""
    plist = save.model("MetagameObjectiveModel").plist
    active = _quest_records(plist, "ObjectiveList")
    completed = _quest_records(plist, "CompletedList")
    key = name.casefold()
    if key in active and key in completed:
        raise ValueError("The save lists this objective as both active and completed.")
    source, target = ("ObjectiveList", "CompletedList") if enabled else ("CompletedList", "ObjectiveList")
    old, new = (active, completed) if enabled else (completed, active)
    if key in new:
        return
    if key not in old:
        raise ValueError("The objective is missing from the saved log.")
    if key in _quest_records(plist, "ClaimList"):
        raise ValueError("Claim this objective's pending reward in the game before editing it.")
    if key in _quest_records(plist, "OfferedList"):
        raise ValueError("This objective also has an open offer. Resolve it in the game first.")
    unread = _quest_records(plist, "NewList")
    tracked = plist.get("TrackedObjectiveId")
    tracked_name = _path(plist, "TrackedObjectiveId", "ID", "PrimaryAssetName")
    clear_tracked = (enabled and tracked_name is not None
                     and read_fstring_payload(tracked_name.raw_payload).casefold() == key)
    record = old[key][1]
    _remove_record(plist, source, record)
    _append_record(plist, target, QUEST_STRUCT, record)
    if enabled and key in unread:
        _remove_record(plist, "NewList", unread[key][1])
    if clear_tracked:
        plist.properties.remove(tracked)

