# Changelog

## v1.15.1
- **Update notifications.** On startup the editor now quietly checks GitHub for a newer
  release and, if one exists, shows a dismissible banner with **GitHub** and **Nexus**
  download links. A new **Check for Updates** button in the toolbar does the same on
  demand. The check runs in a background thread and is silent when you're offline — it
  only contacts GitHub's public API and sends no information about you. It can be turned
  off via `check_updates` in the config file.

## v1.15.0
- **Dark mode.** New Theme selector in the toolbar: **System / Light / Dark**. System
  follows the Windows app theme automatically (and a manual choice is remembered between
  sessions). Added for readers who find the bright white UI hard on the eyes. (user request)
- **Stock structure/armor type on mech cards.** Each chassis now shows its factory
  structure and armor type when it isn't plain Standard — e.g. *Endo-Steel · Ferro-Fibrous*
  (Clan variants labelled too). Read-only display; nothing is written to the save.
- **Templates: armor/structure type data merged** for all 552 chassis, from FiendishDrWu's
  updated extraction (issue #12). Note: vanilla MW5 saves don't store structure/armor type
  at all — the game derives it from the chassis asset — so this is informational; it also
  independently re-confirmed every stock armor/structure value the editor ships.

## v1.14.10
- **Fix: an exact-copy added mech no longer inherits the donor's damage / under-repair
  look.** When you Add Mech for a chassis you already own, the editor duplicates one of
  your existing mechs. If that donor was damaged or in the repair bay, the copy kept the
  donor's reduced structure and spawned looking battle-damaged. The repair step now also
  restores internal structure (MW5 saves store no max-structure reference, so it's
  restored from the chassis's factory-stock template), so an added copy always arrives
  fully patched up regardless of the donor's condition. The fresh GUID already keeps the
  copy out of the original's repair queue. (issue #13, DallasSukerkin)
- Also corrects the title-bar version, which still read v1.14.6 through the 1.14.7-1.14.9
  releases (those didn't touch `gui.py`).

## v1.14.9
- **Fix: Duncan Fisher's Warhammer now shows its weight and class.** The hero
  Warhammer (`WHM-DNC_PLAYABLE`) displayed as `?t` / `?` weight class because the
  `_PLAYABLE` asset suffix wasn't recognised and the variant wasn't mapped to its
  chassis. It now resolves to Warhammer (70t, Heavy). Other `_PLAYABLE` hero/campaign
  mechs are handled the same way. (issue #11, Volt-Ampere)

## v1.14.8
- **Fix: cold-storage mechs are now included in export/import.** The portable
  `.mw5export` export only wrote active-bay mechs, so mechs in Cold Storage were
  silently dropped and couldn't be moved to another save. Export now includes
  cold-storage mechs as well, and import puts them back into Cold Storage (rather
  than the active bay), preserving where they were. (issue #10, Volt-Ampere)

## v1.14.7
- **Updated item catalog.** Refreshed the weapons/equipment/ammo asset catalog with the
  revised dataset from FiendishDrWu: adds DLC8 items and targeting computers (Mk1-Mk7),
  Clan Active Probe, X-Pulse / Large X-Pulse lasers, Arrow IV, Light Autocannon, MRM and
  melee variants, plus matching ammo; removes battle-armor weapon variants from DLC7 and a
  handful of entries that don't exist in the `.pak` files. Totals: weapons 712 -> 791,
  equipment 45 -> 47, ammo 86 -> 92. (issue #9, FiendishDrWu)

## v1.14.6
- **Filter the mech list by location.** A new **Show: All / Active Bay / Cold Storage**
  toggle at the top of the Mechs tab, handy when you have a lot of mechs in cold storage.
- **Chain fire vs salvo per group.** Edit Loadout now shows a **Chain fire** toggle for
  each fire group (1-6): on = the group's weapons fire one after another, off = salvo (all
  at once). It's saved/restored and carried in exported `.mw5loadout` files. (issue #7)

## v1.14.5
- **Fix: AMS hardpoints are now editable.** Anti-Missile System slots showed nothing
  selectable in Edit Loadout (only the currently-mounted AMS), because AMS hardpoints
  weren't recognised as a weapon class. They now offer AMS weapons like any other slot.
  (issue #7, TimeDiver0)
- **Fix: all DLC mechs are in the Add Mech list now.** Later-DLC and Clan chassis (Chaos
  Reign, plus Ebon Jaguar, Kodiak, Incubus, Bushwacker, Naga, Night Gyr, Linebacker, the
  Sunder, and the Clan "C" rebuilds) were missing because an earlier catalog filter used a
  pre-DLC asset list. The roster is now the full game asset list (552 chassis), so any
  chassis the game has can be added. (issue #8, eXFDA)

## v1.14.4
- **Fix: every equipment type is now selectable in Edit Loadout.** Equipment slots used to
  filter their dropdown by slot type, which hid valid gear — most notably jump jets and
  Active Probes (ECCM), which on modded mechs (e.g. YAML with flexible crit slots) sit in
  general/omni slots rather than dedicated ones. Each equipment slot now lists every
  equipment type (jump jets, Active Probe/BAP, ECM, MASC, heat sinks, ammo, armor/structure
  upgrades). (issue #5, reported by TimeDiver0)

## v1.14.3
- **Reset to Stock.** A new button on the Mechs tab resets the selected mech to its
  chassis's factory-stock loadout (armor, weapons, weapon groups, equipment), using the
  same stock data added in v1.14.0. Handy for undoing a botched loadout.
- **Export / Import Loadout.** Save a single mech's loadout to a small `.mw5loadout` file
  and apply it to another mech (best on the same chassis), without exporting the whole
  mech. Good for reusing a custom build across mechs or saves.

## v1.14.0
- **Added mechs now come out as the real factory-stock variant.** When you add a chassis
  you don't own, the editor builds it from that chassis's actual game data — correct stock
  armor, internal structure, weapons, weapon groups, **and** equipment (heat sinks, the
  right class of jump jets, ammo, ECM, etc.) — instead of an approximate clone of an
  unrelated mech. This fixes the wrong armor, the "invisible" jump jets, and the wrong
  tonnage on added mechs. Works for both the active bay and cold storage, for all 554
  chassis. (Stock mech data contributed by **FiendishDrWu** in GitHub issue #6 — thank you!)
- **More equipment types recognised:** Beagle Active Probe (`MWBAPDataAsset`) and Targeting
  Computer (`MWTargetingComputerDataAsset`), alongside the ECM added in 1.13.1.

## v1.13.1
- **Fix (regression in 1.13.0):** the Edit Loadout screen no longer hides hardpoints or
  equipment that fall outside the 8 standard body locations. On heavily-modded mechs (e.g.
  YAML with extra crit slots) some weapons — and their fire groups — were not showing. The
  editor now renders **every** hardpoint, with any non-standard ones under an "Other
  hardpoints" section.
- **New: Body / List view toggle in Edit Loadout.** "Body" is the silhouette layout;
  "List" shows every hardpoint in one dense column with inline fire groups — best for mechs
  that use a lot of slots. Your selection is kept when switching views.
- **Fix:** ECM (`MWECMDataAsset`) is now recognised, so ECM/ECCM you own (including
  mod-added types) shows up in the equipment lists.

## v1.13.0
- **Visual overhaul of the Mechs tab.** The mech bay is now a list of **cards** with a
  weight-class icon, the mech's name, tonnage, Active Bay / Cold Storage location, and a
  colour-coded class badge (Light / Medium / Heavy / Assault). Click to select,
  double-click to edit the loadout.
- **Edit Loadout is now a body-location layout.** Weapons and equipment are shown on a
  "paper-doll" of the mech (Head up top; arms, torsos across the middle; legs below), like
  the in-game Mech Lab, with fire groups in an aligned table underneath.
- **Edit Loadout scrolls** (scrollbar + mouse wheel), and Apply / Cancel are always
  visible, so nothing gets cut off on tall mechs or smaller screens.

## v1.12.2
- **Add Mech can now place a mech directly into Cold Storage.** When you add a mech you
  pick **Cold Storage** (recommended, always works) or **Active Bay**. This fixes added
  mechs vanishing / triggering an "invalid loadout" warning when the active bay is full:
  active-bay adds need a free bay slot in-game, whereas cold storage always works and you
  can move the mech to the bay in-game later.
- **Fix: approximate added mechs no longer inherit the donor's equipment.** Adding a
  chassis you don't own used to carry over the template mech's heat sinks and jump jets,
  which showed up as "invisible" jump jets that ate tonnage but didn't appear in the Mech
  Lab. Those are now stripped, so you start from a clean chassis and fit gear yourself.
- Note: an approximate mech of a chassis you don't own still borrows that template's
  internals (engine, max armor, jump-jet capacity), since those live in the game files and
  not the save. Max its armor and refit it in the Mech Lab.

## v1.12.1
- Renamed the executable from `MW5SaveEditor.exe` to `JJsaveEditor.exe` (the folder in
  the download is now `JJsaveEditor` too). No functional changes from v1.12.0.

## v1.12.0
- **Active Bay vs Cold Storage are now shown separately.** The Mechs tab adds a
  **Location** column (Active Bay / Cold Storage) and a count summary at the top, so
  you can see at a glance how many mechs are in each. Cold-storage rows are dimmed.
  This makes it clear where your mechs actually live, including ones the game has put
  into cold storage when your active bay is full. All the mech actions (Edit Loadout,
  Repair, Change Chassis, Remove) work on cold-storage mechs too.

## v1.11.2
- **Much bigger item lists.** The weapon/equipment/ammo catalogs now cover the game's
  full asset list — weapons jump from ~70 to **712** (every tier variant), plus more
  equipment and ammo — so far more gear is selectable in the Inventory and Loadout
  pickers up front. (Asset data contributed by **FiendishDrWu** in GitHub issue #2 — thank you!)
- **Fix: Add Mech only lists mechs the game actually has.** The chassis list previously
  carried 74 tabletop-only variants that aren't in MW5; adding one wrote a mech the game
  silently dropped on load, so it "didn't appear". Those are gone, and a mis-cased entry
  (Kintaro KTO-19b) is corrected. If a mech you add still doesn't show, it's from a DLC
  you don't own. (Reported by **DallasSukerkin**.)
- **Fix: AMS now appears in the item lists.** Anti-Missile System is a weapon-type asset,
  so it now shows under weapons (and AMS you already own is picked up too). (Reported by
  **DallasSukerkin**.)
- **Fix: market-listing mechs no longer show up as owned mechs.** Mechs for sale in a
  market share the same internal list as your bay; they're now correctly excluded from
  the Mechs tab (they're identified by their loadout type). Cold-storage mechs are
  excluded the same way (a proper Cold Storage view is planned).

## v1.11.0
- **Pilot traits** are now editable. The Pilots tab has a Traits panel: add a trait from a
  dropdown of every trait your save has encountered (or type an asset name), or remove one.
  Great for skipping the save-scum hunt for the traits you want.
- **Mech traits (experimental).** The Edit Loadout dialog can add/remove Cantina-style mech
  quirks (e.g. Faster Cooling). This is best-effort and **untested in-game** — it's clearly
  labelled in the app. Back up your save before relying on it.

## v1.10.0
- Inventory quality-of-life: filter/search box, sortable columns (click a header),
  multi-select rows (shift/ctrl-click) to set count or remove in bulk, and double-click an
  item to set its count.

## v1.9.0
- Export / Import: transfer mechs, pilots, inventory, C-Bills and faction standings between
  saves. "Export..." writes a portable .mw5export file; "Import..." adds it all into another
  loaded save (e.g. moving a career lineup into a fresh campaign). Imported mechs/pilots get
  fresh IDs so they coexist with what's already there.

## v1.8.0
- Rare / DLC weapons and gear now appear in the dropdowns. On load, the editor harvests
  every weapon/equipment/ammo your save references (markets, missions, enemy mechs, your
  own gear) and merges them into the Inventory and Loadout pickers — so anything you've
  encountered (Clan ER PPCs, pulse/chem lasers, Inferno/Hotloaded ammo, etc.) is
  selectable, with guaranteed-valid asset names.

## v1.7.0
- Pilot **skill caps** are now editable. Each skill in the Pilots tab has a Cap (1–10)
  field next to its XP, plus a "Max caps (10)" button — set a pilot to full potential and
  train them up in-game. (Gunnery/Piloting don't use the cap system.)

## v1.6.0
- Builds and releases are now automated via GitHub Actions: a version tag compiles the
  Nuitka EXE and publishes it to the GitHub release (and Nexus Mods). No functional
  changes from v1.5.0.

## v1.5.0
- Now built with **Nuitka** (compiled to a native binary) instead of PyInstaller, so it
  no longer triggers antivirus/"malware" false positives the way the PyInstaller build
  did. Functionally identical to v1.4.0. (The v1.4.0 PyInstaller build stays available.)

## v1.4.0
- **Edit Loadout** now also edits **equipment** — heat sinks, ammo, jump jets, MASC —
  per slot, alongside weapons, fire groups, and armor. Options are filtered to each
  slot's type (ammo/heat sinks in general slots, jump jets in jump-jet slots).

## v1.3.0
- New **Set Hardpoints…** button: apply a real hardpoint layout to a mech, then fit
  weapons in Edit Loadout. Layouts are harvested from your save (owned mechs, market,
  mission records) — a same-chassis layout is exact; others are "borrowed".
- **Add Mech** now uses a chassis's real hardpoint layout automatically when your save
  has one on record, so added mechs come out with correct, ready-to-fit hardpoints.

## v1.2.0
- You can now build a loadout on a mech that has **no hardpoints**. Hit Edit Loadout on
  an empty mech and pick a mech to copy a hardpoint layout from, then fit weapons.
- Approximate added mechs keep their (emptied) hardpoints instead of being fully
  stripped, so they're editable right away.

## v1.1.0
- **Mech loadout editor!** Edit a mech's weapons per hardpoint (class-filtered), set
  each weapon's fire group (1–6), and edit armor per location with a Max-armor button.

## v1.0.2
- **Smarter Add Mech.** If you already own a mech of the chosen chassis, it adds an
  exact, fully-working duplicate (weapons + groups intact). For a chassis you don't own,
  it adds an approximate clone with its weapons stripped — so it no longer carries stale
  weapon groups (which caused added mechs' fire groups to reset to 1). Refit in the Mech Lab.

## v1.0.1
- Mech list and the Add-Mech picker now show friendly names (e.g. *Javelin (JVN-10F)*)
  and hero nicknames (*Atlas "Boar's Head"*, *Centurion "Yen-Lo-Wang"*…) instead of raw
  asset codes. Version now shown in the window title.

## v1.0.0
- Initial release. Edit mechs (add / change chassis / repair / remove), pilots (callsign,
  name, salary, skill XP, add/remove), inventory (weapons / equipment / ammo + counts),
  C-Bills, and faction standings — in a simple Windows app.
