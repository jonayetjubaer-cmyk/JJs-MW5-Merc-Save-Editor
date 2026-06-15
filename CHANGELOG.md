# Changelog

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
