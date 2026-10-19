"""Cantina progress and its separate persistent mech-upgrade unlock list.

Tier thresholds are factual CareerPoints values extracted from the five
CareerPathLevels arrays in the installed, unmodified DLC9 game assets.
"""
from bisect import bisect_right
from copy import deepcopy
from dataclasses import dataclass

from savefile import (_path, _set_leaf, _int_property, read_fstring_payload,
                      read_int, write_int, write_fstring_payload)
from ue_property import ArrayValue, Property, PropertyList, Writer, Reader

TIERS = {
    "EquipmentCollectorCareerPath": (5, 17, 32, 50, 70, 95, 124, 175, 249, 349),
    "MechCollectorCareerPath": (5, 17, 50, 70, 95, 95, 124, 175, 249, 349),
    "MechHunterCareerPath": (5, 17, 32, 50, 70, 95, 124, 175, 249, 349),
    "TreasureHunterCareerPath": (5, 17, 32, 50, 70, 95, 124, 175, 249, 349),
    "WarDogCareerPath": (5, 17, 32, 50, 70, 95, 124, 175, 249, 349),
}
LABELS = {
    "EquipmentCollectorCareerPath": "Equipment Collector",
    "MechCollectorCareerPath": "Mech Collector",
    "MechHunterCareerPath": "Mech Hunter",
    "TreasureHunterCareerPath": "Treasure Hunter",
    "WarDogCareerPath": "War Dog",
}

# MechTraitReward, in tier order, from the same unmodified DLC9 career assets.
# Reproduce with tools/extract_cantina_thresholds.py; these are 50 career rewards,
# not every mech trait in the catalog. Mod-only traits are never guessed.
REWARDS = {
    "EquipmentCollectorCareerPath": (
        "IncreasedJJFuelBurnTime_Trait1", "IncreasedTurnSpeed_Trait1",
        "IncreasedEnergyRangeAndSpeed_Trait1", "ReducedLaserDuration_Trait1",
        "IncreasedArmor_Trait1", "IncreasedWeaponRangeAndSpeed_Trait1",
        "IncreasedSensorRange_Trait2", "IncreasedBallisticRangeAndSpeed_Trait2",
        "ReducedEnergyCooldown_Trait2", "ReducedWeaponCooldown_Trait1"),
    "MechCollectorCareerPath": (
        "ReducedEnergyCooldown_Trait1", "IncreasedBallisticDamage_Trait1",
        "IncreasedHeatCapacity_Trait1", "IncreasedWeaponDamage_Trait1",
        "ReducedMissileHeat_Trait1", "IncreasedEnergyDamage_Trait2",
        "ReducedBallisticHeat_Trait2", "IncreasedMissileDamage_Trait2",
        "ReducedEnergyHeat_Trait2", "ReducedHeatGeneration_Trait1"),
    "MechHunterCareerPath": (
        "IncreasedJJFuelRegenTime_Trait1", "IncreasedStructure_Trait1",
        "IncreasedBallisticRangeAndSpeed_Trait1", "ReducedMissileSpread_Trait1",
        "IncreasedEnergyDamage_Trait1", "ReducedBallisticHeat_Trait1",
        "IncreasedAccelerationDeceleration_Trait2", "IncreasedMissileRangeAndSpeed_Trait2",
        "ReducedBallisticCooldown_Trait2", "IncreasedHeatCapacity_Trait2"),
    "TreasureHunterCareerPath": (
        "IncreasedMissileRangeAndSpeed_Trait1", "ReducedBallisticCooldown_Trait1",
        "IncreasedMissileDamage_Trait1", "IncreasedHeatCooling_Trait1",
        "ReducedEnergyHeat_Trait1", "ReducedMissileCooldown_Trait2",
        "IncreasedArmor_Trait2", "IncreasedBallisticDamage_Trait2",
        "ReducedMissileHeat_Trait2", "ReducedWeaponHeat_Trait1"),
    "WarDogCareerPath": (
        "IncreasedSensorRange_Trait1", "IncreasedLockRetentionAndLoseLockTime_Trait1",
        "IncreasedJJAccelXYZ_Trait1", "IncreasedAccelerationDeceleration_Trait1",
        "IncreasedTorsoTwistRate_Trait1", "ReducedMissileCooldown_Trait1",
        "IncreasedTurnSpeed_Trait2", "IncreasedStructure_Trait2",
        "IncreasedEnergyRangeAndSpeed_Trait2", "IncreasedTopSpeed_Trait1"),
}


@dataclass
class CantinaPath:
    asset: str
    progress: object = None
    save: object = None

    @property
    def label(self):
        return LABELS.get(self.asset, self.asset)

    @property
    def points(self):
        progress = (_records(self.save.model("ErrandModel").plist).get(self.asset)
                    if self.save is not None else self.progress)
        return read_int(progress.raw_payload) if progress is not None else 0

    @property
    def tier(self):
        thresholds = TIERS.get(self.asset)
        return bisect_right(thresholds, self.points) if thresholds else None

    def set_points(self, value):
        if type(value) is not int or not 0 <= value <= 2147483647:
            raise ValueError("Cantina points must be a non-negative 32-bit integer.")
        if self.save is not None:
            _apply(self.save, {self.asset: value})
            self.progress = _records(self.save.model("ErrandModel").plist)[self.asset]
        else:
            if self.progress is None:
                raise ValueError("This Cantina path is not attached to a save.")
            _set_leaf(self.progress, write_int(value))

    def set_tier(self, tier):
        thresholds = TIERS.get(self.asset)
        if thresholds is None:
            raise ValueError("This path has no verified built-in tier thresholds.")
        if type(tier) is not int or not 0 <= tier <= len(thresholds):
            raise ValueError("Cantina tier must be between 0 and 10.")
        self.set_points(thresholds[tier-1] if tier else 0)


def _struct(name, kind, properties):
    header = Writer()
    header.i64(0)  # serializer recomputes this from the property list
    header.fstring(kind)
    header.write(bytes(16))
    return Property(name, "StructProperty", header.bytes(), b"",
                    PropertyList(properties), struct_leading_byte=b"\0")


def _name(name, value):
    payload = write_fstring_payload(value)
    header = Writer()
    header.i64(len(payload))
    header.byte(0)
    return Property(name, "NameProperty", header.bytes(), payload)


def _asset_id(kind, asset):
    return _struct("ID", "PrimaryAssetId", [
        _struct("PrimaryAssetType", "PrimaryAssetType", [_name("Name", kind)]),
        _name("PrimaryAssetName", asset)])


def _array(name, kind):
    header = Writer()
    header.i64(0)
    header.fstring("StructProperty")
    return Property(name, "ArrayProperty", header.bytes(), b"",
                    ArrayValue("StructProperty", 0, [], inner_tag_name=name,
                               inner_struct_name=kind, inner_struct_guid=bytes(16),
                               elements_leading_byte=b"\0"), array_leading_byte=b"\0")


def _struct_kind(prop):
    try:
        reader = Reader(prop.raw_header)
        reader.i64()
        return reader.fstring()
    except (EOFError, ValueError):
        raise ValueError("The save's Cantina struct header could not be decoded safely.")


def _checked_array(prop, kind):
    array = prop.decoded
    if (prop.type != "ArrayProperty" or not isinstance(array, ArrayValue)
            or array.element_type != "StructProperty" or array.inner_struct_name != kind
            or array.count != len(array.elements)
            or any(not isinstance(el, PropertyList) for el in array.elements)):
        raise ValueError("The save's Cantina data uses an unsupported array layout.")
    return array


def _progress(plist, create=False):
    wrapper = plist.get("CareerPathList")
    if wrapper is None:
        if not create:
            return None
        wrapper = _struct("CareerPathList", "CareerPathProgressList", [])
        plist.properties.append(wrapper)
    if (wrapper.type != "StructProperty" or not isinstance(wrapper.decoded, PropertyList)
            or _struct_kind(wrapper) != "CareerPathProgressList"):
        raise ValueError("The save's Cantina progression uses an unsupported layout.")
    progress = wrapper.decoded.get("Progress")
    if progress is None:
        if not create:
            return None
        progress = _array("Progress", "CareerPathProgress")
        wrapper.decoded.properties.append(progress)
    return _checked_array(progress, "CareerPathProgress")


def _asset_name(element, kind, *prefix):
    name = _path(element, *prefix, "ID", "PrimaryAssetName")
    asset_type = _path(element, *prefix, "ID", "PrimaryAssetType", "Name")
    if (name is None or name.type != "NameProperty" or asset_type is None
            or asset_type.type != "NameProperty"
            or read_fstring_payload(asset_type.raw_payload) != kind):
        raise ValueError("A Cantina asset ID could not be decoded safely.")
    value = read_fstring_payload(name.raw_payload)
    if not value or value == "None":
        raise ValueError("A Cantina asset ID is empty.")
    return value


def _records(plist):
    array = _progress(plist)
    result = {}
    for element in array.elements if array else []:
        asset = _asset_name(element, "MWCareerPathAsset", "Career")
        points = element.get("Progress")
        if (asset in result or (points is not None and (points.type != "IntProperty"
                or len(points.raw_payload) != 4 or read_int(points.raw_payload) < 0))):
            raise ValueError("A Cantina career record could not be decoded safely.")
        result[asset] = points
    return result


def paths(save):
    """Show missing stock paths at zero without changing the loaded save."""
    try:
        model = save.model("ErrandModel").plist
    except KeyError:
        return []
    records = _records(model)
    assets = list(records) + [name for name in TIERS if name not in records]
    return [CantinaPath(asset, records.get(asset), save) for asset in assets]


def _apply(save, changes, sync_all=False):
    """Stage both models before committing; malformed unlocks cannot leave XP edited."""
    original = save.model("ErrandModel")
    errand = deepcopy(original.plist)
    records = _records(errand)
    for asset, value in changes.items():
        if type(value) is not int or not 0 <= value <= 2147483647:
            raise ValueError("Cantina points must be a non-negative 32-bit integer.")
        if asset not in records and asset not in TIERS:
            raise ValueError("Missing mod-added career paths cannot be created.")
    if changes:
        array = _progress(errand, create=True)
        for asset, value in changes.items():
            if asset not in records:
                element = PropertyList([
                    _struct("Career", "CareerPathAssetId", [_asset_id("MWCareerPathAsset", asset)]),
                    _int_property("Progress", value)])
                array.elements.append(element)
                array.count += 1
                records[asset] = element.get("Progress")
            elif records[asset] is None:
                element = next(el for el in array.elements
                               if _asset_name(el, "MWCareerPathAsset", "Career") == asset)
                records[asset] = _int_property("Progress", value)
                element.properties.append(records[asset])
            else:
                _set_leaf(records[asset], write_int(value))
    wanted = []
    for asset in records if sync_all else changes:
        if asset in TIERS:
            points = read_int(records[asset].raw_payload) if records[asset] is not None else 0
            tier = bisect_right(TIERS[asset], points)
            wanted.extend(REWARDS[asset][:tier])
    added = 0
    trait_model = None
    if wanted:
        try:
            trait_model = save.model("MechTraitModel")
        except KeyError:
            raise ValueError("This save has no mech-upgrade model; Cantina edits were not applied.")
        traits = deepcopy(trait_model.plist)
        unlocked = traits.get("UnlockedMechTraitsList")
        if unlocked is None:
            unlocked = _array("UnlockedMechTraitsList", "MechTraitDataAssetId")
            traits.properties.append(unlocked)
        array = _checked_array(unlocked, "MechTraitDataAssetId")
        existing = {_asset_name(el, "MWMechTraitDataAsset") for el in array.elements}
        for asset in wanted:
            if asset not in existing:
                array.elements.append(PropertyList([_asset_id("MWMechTraitDataAsset", asset)]))
                array.count += 1
                existing.add(asset)
                added += 1
    if changes:
        original.plist = errand
    if added:
        trait_model.plist = traits
    return added


def sync_unlocks(save):
    """Repair missing upgrades for current stock-path points; never remove unlocks."""
    return _apply(save, {}, sync_all=True)


def max_paths(records):
    """Max all stock paths and repair their unlocks, keeping mod data intact."""
    if records and records[0].save is not None:
        save = records[0].save
        if any(record.save is not save for record in records):
            raise ValueError("Cantina paths must belong to the same save.")
        changes = {record.asset: max(record.points, TIERS[record.asset][-1])
                   for record in records if record.asset in TIERS}
        _apply(save, changes)
        return len(changes)
    changes = [(record, max(record.points, TIERS[record.asset][-1]))
               for record in records if record.asset in TIERS]
    for record, points in changes:
        record.set_points(points)
    return len(changes)
