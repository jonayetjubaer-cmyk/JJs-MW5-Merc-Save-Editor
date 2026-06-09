# MW5 Mercs Save Format Notes

Working notes from reverse-engineering. Fill in as findings come in from
`tools/diff_saves.py` runs.

## Known so far

- Save location: `%LOCALAPPDATA%\MW5Mercs\Saved\SaveGames\<profile-id>\`
  - `Campaign.json` — plain JSON, lists save slots/metadata (human readable, no work needed)
  - `<hash>.sav` — the actual save data, one per slot

### `.sav` format — CONFIRMED: Unreal Engine tagged property archive (uncompressed)

NOT gzip/zlib. Raw bytes start directly with UE4/UE5 "tagged property" serialization
(the same property-list format used inside `GVAS` SaveGame archives for many UE
games — Palworld, Satisfactory, etc. — just without the outer `GVAS` magic/header
wrapper, or possibly the header lives elsewhere).

Observed pattern (all little-endian):

```
[int32 length][ASCII string, NUL-terminated]   -- e.g. "GameModeClass"
```

This is a length-prefixed string (`FString`): `0e 00 00 00` = 14, followed by
14 bytes of "GameModeClass\0".

Then properties follow the standard UE "tagged property" shape:

```
[name: FString][type: FString][size: int64][... type-specific payload ...]
```

Confirmed property type tags seen in the first 600 bytes of
`985EACE145F8E01AA55AB29C02FBAD84.sav`:
- `ObjectProperty` — references like `/Game/Modes/CavalierCampaignMode.CavalierCampaignMode_C`
  and `/Script/MechWarrior.MWScenarioModel`
- `ArrayProperty` (e.g. `PersistentModelData`, element type `ByteProperty`)
- `StructProperty` (e.g. `CurrentScenario` → struct `MWScenarioSpecification`,
  `ScenarioDetails` → struct `ScenarioDetails`, `MissionSpec` → struct `MWMissionSpecification`)
- `StrProperty` (e.g. `Name` = "Leopard Dropship", `"None"` terminator strings)
- `ByteProperty` (used as array element type / enums)

Readable plaintext is everywhere (class paths, struct names, property names,
string values) — confirms no encryption and no compression on top.

### Full structure mapped so far (985EACE...sav, "AutoSave (Entered System)")

```
[top level]
├─ GameModeClass : ObjectProperty  (e.g. "/Game/Modes/.../CavalierCampaignMode_C")
└─ PersistentModelData : ArrayProperty<ByteProperty>   (2.5MB blob -- THE entire game state)
   │  Quirk: actual size = declared_size + 1 (extra leading byte not counted in FPropertyTag.size)
   │  Inner = nested tagged-property archive:
   ├─ ScenarioModel, OperationsModel, StarMapModel, TravelModel, InventoryModel,
   │  MarketModel, TimelineModel, ContractModel, PostMissionModel, MercCompanyModel,
   │  FinanceModel, UnitProgressionModel, RosterModel, ToiModel, ErrandModel,
   │  MechStorageModel, CampaignArcModel, DialogueModel, MetagameObjectiveModel,
   │  SaveStateModel, DataCacheModel, EventLogModel, CodexModel, NewsTickerModel,
   │  MechTraitModel, AchievementModel, BountyHunterModel, ArenaFameModel,
   │  UnitObservationModel        (all : ObjectProperty, 29 total)
   │
   │  Each "Model" payload = [class path FString, e.g. "/Script/MechWarrior.MWMechStorageModel"]
   │  followed by a table of bound delegates/events (MulticastInlineDelegateProperty
   │  entries — noise, not game data) THEN the model's own tagged-property list with
   │  the actual gameplay data.
   │
   └─ MechStorageModel → property "MechStorageList" : ArrayProperty<StructProperty>
        each element struct has fields: ItemId (Guid), Value (StructProperty, likely
        a reference/handle). This looks like a GUID-keyed map of owned-mech instance
        IDs — the actual mech definitions (chassis/variant/tonnage/loadout/paint) are
        most likely in InventoryModel (33KB), looked up by these GUIDs.
```

### BREAKTHROUGH: mech identity & full definition location (from buy-FS9-H diff)

Clean diff (saves "Before2"/"After2", 27s apart, same reload-context to cancel
out "Owner"-reference noise) showed exactly ONE meaningful change:

`MechStorageModel.MechStorageList[slot].ItemId.Value.Guid` flips from
all-zeros (`00...00`) to a real GUID (`72aa68e4-a91e-bb4a-8bb4-497775c2036d`).
**=> The array is pre-allocated with empty/placeholder slots (hangar capacity);
buying a mech claims a slot by writing its GUID, it does not grow the array.**

Searching for that GUID elsewhere in the save finds it again inside
`SaveStateModel`, in a `MarketItemMech` struct (looks like a market-purchase
record):

```
MarketItemMech : StructProperty
├─ Item.ItemMech.ItemId.Value.Guid  = <same GUID>
└─ ItemData.MechLoadout : StructProperty
    ├─ MechDataAssetId.ID.PrimaryAssetId : StructProperty
    │   ├─ PrimaryAssetType.Name (NameProperty) = "MWMechDataAsset"
    │   └─ PrimaryAssetName.Name (NameProperty) = "FS9-H_MDA"   <-- chassis+variant id!
    └─ SkinCustomization.UnitSkinCustomization.MechSkinAssetId : StructProperty ...
```

**Mechs ARE identified by readable names** — the standard UE `FPrimaryAssetId`
pattern: `{Type: "MWMechDataAsset", Name: "<ChassisCode>-<Variant>_MDA"}`,
e.g. `"FS9-H_MDA"` for the Firestarter FS9-H. (Earlier searches missed this
because the definition lives in SaveStateModel, not Inventory/MechStorage.)

### Full MechLoadout schema (readable, self-describing -- great news!)

```
MechLoadout : StructProperty
├─ MechDataAssetId.ID.PrimaryAssetId
│    {PrimaryAssetType.Name: "MWMechDataAsset", PrimaryAssetName.Name: "FS9-H_MDA"}
├─ SkinCustomization.UnitSkinCustomization
│    ├─ MechSkinAssetId.ID.PrimaryAssetId
│    │    {Type: "MWUnitSkinAsset", Name: "Firestarter_Kurita_SKN"}
│    └─ CustomMechSkinId (NameProperty) = "Firestarter_Kurita_SKN"
├─ CurrentStructure   : MechPartsHealth {Head, CenterTorso, LeftTorso, RightTorso,
│                                         LeftArm, RightArm, LeftLeg, RightLeg} (FloatProperty)
├─ CurrentArmor       : MechPartsHealth {...same 8 fields...}
├─ CurrentRearArmor   : MechRearArmorValues {CenterTorsoRear, LeftTorsoRear, RightTorsoRear} (Float)
├─ InstalledArmor     : MechPartsHealth {...}
├─ InstalledRearArmor : MechRearArmorValues {...}
└─ InstalledWeapons : ArrayProperty<StructProperty of MechLoadoutWeapons>
     each element:
       ├─ HardpointSlotID (NameProperty) e.g. "Torso_Left_BH1_machinegun"
       └─ WeaponData.WeaponId.WeaponDataAssetId.ID.PrimaryAssetId
            {Type: "MWTraceWeaponDataAsset" | "MWMissileWeaponDataAsset" | "MWProjectileWeaponDataAsset",
             Name: <weapon asset id>}
            (+ more fields per weapon, not yet fully captured)
```

KEY INSIGHT: mechs are fully described via human-readable `FPrimaryAssetId`
{Type, Name} pairs (e.g. "FS9-H_MDA", "Firestarter_Kurita_SKN",
"MWTraceWeaponDataAsset"). No opaque hashes/IDs to reverse engineer for
chassis/skin/weapon identity -- just need the right asset name strings
(obtainable from game files / community wikis / by examining more mechs).

This makes "construct a MechLoadout for an arbitrary chassis" very tractable:
build the struct tree with sensible default health/armor values (e.g. copy an
existing mech's values, or derive from chassis tonnage) and the desired
PrimaryAssetId names.

### CONFIRMED: canonical mech record format & location (resolved open question)

Traced all 6 owned-mech GUIDs (5 pre-existing + the new FS9-H purchase) — every
single one resolves into `SaveStateModel`, each wrapped IDENTICALLY:

```
MWMechLoadoutWrapper : ObjectProperty (or nested struct)
└─ ByteData : ArrayProperty<ByteProperty>     <-- nested byte-blob sub-archive
                                                  (SAME recursive pattern as the
                                                   outer PersistentModelData!)
   └─ MarketItemMech : StructProperty
       ├─ Item.ItemMech.ItemId.Value.Guid  = <mech instance GUID>
       └─ ItemData.MechLoadout : StructProperty   (full schema documented above)
```

So "MarketItemMech" is just the generic internal struct name for "an item
record describing a mech" — used uniformly for owned mechs AND market listings,
not a one-off transaction log. **This is THE canonical, persistent format.**

=> "Add a mech" = build one `MWMechLoadoutWrapper`/`ByteData`/`MarketItemMech`
blob (with a fresh GUID + desired MechDataAssetId/skin/armor/weapons), AND
write that same fresh GUID into an empty `MechStorageList` slot in
MechStorageModel. Two writes, one shared GUID, both inside PersistentModelData.

### CRITICAL GOTCHA: every nested archive has a 4-byte FOOTER after "None"

Discovered the hard way: first injection attempt produced a save that loaded
fine (no error) but showed a **completely empty mech bay** — all mechs gone,
new one included. Root cause: at every level where a region is structured as
"[framing][tagged-property list]", the property list's `None` terminator does
NOT mark the end of the region — there are **4 extra bytes (observed: all
zero, `00 00 00 00`)** still WITHIN the declared length, after the terminator.
Confirmed present at ALL FOUR nested-archive levels:

1. Top-level file (already known — `test_roundtrip.py`'s "trailing bytes")
2. `PersistentModelData`'s inner archive: `[int32 len][PROPLIST][4-byte footer]`
3. Each `Model` UObject (`raw_payload` of the `ObjectProperty` entries):
   `[class_path FString][PROPLIST][4-byte footer]`
4. Each `MechLoadoutWrapper.ByteData` nested archive:
   `[int32 len][PROPLIST][4-byte footer]`

The generic round-trip sweep never caught this because it only compared
`raw_payload[:consumed]` (deliberately excluding the unmodeled tail) — so the
parser "passing" at 29/29 only proved the decode works UP TO the
terminator correctly, not that it would correctly preserve what comes after when
**rebuilding** a region from its decoded form (as opposed to copying
`raw_payload` verbatim, which is what normal round-trip does and why it never
showed up there).

**RULE: any time you parse `[[framing] + property-list]` out of a byte region
with a known total length/size and intend to MODIFY + REBUILD it, you must
capture `region[terminator_end:]` as a "footer" and re-emit it verbatim.**
`inject_mech.py`'s `get_nested_archive`/`set_nested_archive` and the
`ss_footer`/`ms_footer`/`pmd_footer` plumbing in `inject_mech()` show the
pattern. Likely meaning: a `UObject`/`SaveGame` archive serialization always
writes some fixed trailing field (export count? GUID? flags?) that happens to
be zero in single-player saves — but treat it as an opaque footer, not as
"zero padding to skip", since its value might matter in other saves/contexts.

### Remaining smaller unknowns (not blocking, can refine iteratively)

- A few trailing fields of `MechLoadoutWeapons` not fully captured (likely ammo
  count / weapon level / hardpoint group — minor, can copy from a donor mech)
- Exact byte layout/location of `MWMechLoadoutWrapper` as an object (vs struct)
  — need to read its header bytes precisely to clone correctly
- `MechStorageList` capacity: confirmed pre-allocated with empty slots; what
  happens when all slots are full (does it grow, or does the game block the
  purchase via `CheckHangarFull`?) — only matters if hangar is already full

### Plan for "add a mech"

1. Locate the mech definition struct inside `InventoryModel` (likely `MechDef` /
   `MWMechSpecification` or similar — search for chassis names like "Centurion",
   "Atlas", tonnage values, etc, or diff two saves where a mech was bought/sold).
2. Once the struct schema is known, "adding a mech" = appending a new GUID entry
   to `MechStorageModel.MechStorageList` AND a matching mech-def entry to whatever
   array in `InventoryModel` holds them, with a fresh GUID linking the two.
3. Because this changes array length (and therefore every enclosing size field —
   StructProperty/ArrayProperty/ByteProperty-blob/top-level), the writer must
   recompute sizes bottom-up, which `ue_property.py` is designed to do via the
   `decoded` tree (raw blobs are kept verbatim; decoded structures resync sizes).

### Implication for the build plan

Because this is the well-documented standard UE tagged-property format (not a
custom MW5-specific encoding), there's no need to byte-diff a parser into existence.
Plan: adapt/port a generic UE property-tree reader+writer (prior art exists for
other UE games, e.g. `palworld-save-tools`' GVAS reader, `uesave-rs`) to get
a structured dump (JSON-like tree of name/type/value) of the whole save, edit
values in that structure, and re-serialize back to bytes preserving exact
layout/sizes. Byte-diffing is still useful later to map *semantic* meaning
(which struct/field = which in-game stat), but not for cracking the encoding
itself — the encoding is already known.

## Diff log

Record each experiment here: what you changed in-game, the file pair, and the
byte offset(s) that changed plus your interpretation of the encoding
(int32 LE, UTF-16LE string, FProperty tag, etc).

### Experiment 1: <description, e.g. "changed C-Bills from X to Y">
- Files: `<old>`, `<new>`
- Changed offset(s): `<from diff_saves.py output>`
- Interpretation: `<TBD>`
