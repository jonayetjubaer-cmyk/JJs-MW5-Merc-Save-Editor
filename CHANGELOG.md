# Changelog

## v1.20.0
- **Publisher metadata:** Windows file properties now identify **Jonaex LTD**
  as the company and copyright holder. The editor's product name is unchanged.
- **Choose the editor language.** English, French, German, Russian, Japanese,
  and Latin American Spanish match MW5's supported interface languages.
  The new **Language (restart)** selector remembers the choice. Save your
  changes and restart to apply it; changing the selection never rebuilds forms
  or discards pending edits. First launch follows the supported Windows display
  language, falling back to English.
- **Translated interface.** Tabs, buttons, filters, editing dialogs, loadout
  location labels, confirmations and status messages have translation catalogs.
  Asset names/IDs, existing pilot biographies and technical diagnostic details
  retain their original text. These are initial AI-assisted translations;
  native-speaker corrections are welcome.
- **Save operations retain their original identifiers.** Translated choices for
  inventory categories, pilot filters, sorting and empty loadout slots map back
  to the same internal values. No save-format or catalog-format changes.
- **Translations are bundled with the Windows download.** Missing or invalid
  translation entries fall back to English. The larger default window and
  wrapped inventory hint accommodate translated text.
- 122 regression tests pass, including catalog coverage and placeholder
  validation for all six languages, canonical filter/sort/empty-slot values,
  preference persistence and preservation of pending edits. The compiled Windows
  build was opened with bundled Japanese translations; Russian pilot, inventory
  and faction layouts were visually checked. Translation wording still benefits
  from native-speaker review.

## v1.19.1
- **Cantina paths can be edited before earning points (issue #43).** All five
  built-in paths now appear, including not-started paths at zero. Reading a save
  creates nothing; Set points/tier or Max all paths creates only the required
  career-progress records, using the observed native save structures.
- **Cantina edits now update upgrade unlocks too.** Career points and unlocked
  mech upgrades live in separate models. Setting points/tier adds the built-in
  upgrade rewards through the resulting tier. Max all paths includes all 50
  career rewards, mapped directly from the unmodified DLC9 game assets.
- **Repair earlier edits with Sync upgrade unlocks.** This adds missing upgrades
  for the current points without changing career progress. Repeated use does not
  add duplicates. Lowering points never revokes existing upgrades; existing and
  mod-added upgrades and career paths are preserved. Built-in mappings may differ
  from mods that change career thresholds or rewards.
- **Edits are staged before either model is changed.** Unsupported career or
  unlock layouts abort the operation without partially applying points. Jobs,
  offers, pending claims and campaign unlocks are preserved.
- 113 automated tests pass. Validated against the issue #43 attachment: 8 upgrade unlocks became 50, with
  only MechTraitModel changed. Save As/reload and repeat repair pass. Unchanged
  browsing and edited-save checks pass on 16 real saves, including creation of
  missing progress in 14 saves. In-game upgrade availability and subsequent job
  progression still need confirmation from testing in MW5.

## v1.19.0
- **Arrange the saved pilot roster (issue #42).** Move Up, Move Down, Move to
  Top and Move to Bottom persist your custom order in the save. Player/commander
  slots stay fixed; regular pilots move around them. Moving a pilot keeps the
  selection and any unfinished form edits on that pilot. Click the relevant
  Apply/Set buttons for field edits, then Save to keep the roster order.
  The order survives save/reload in the editor; MW5's deployment-screen sorting
  still needs in-game confirmation.
- **Change a pilot's portrait and voice.** The Pilots tab has a new Appearance
  section with searchable portrait and voice pickers (385 portraits, 342 voices
  from the game), a male/female filter, and a persona picker that copies a
  scripted character's portrait and voice (optionally name and bio too).
  Hireable and hero personas are listed by default; "Show all personas" lists
  every persona asset. Assets already in your save stay selectable. Each row has
  its own **Set** / **Apply** button (like the trait Add button) that writes to
  the pilot immediately.
- **Portrait and voice pickers name who uses them.** Entries read like
  `MaleAlly9 -- Raptor`, so you can tell what a voice or portrait belongs to
  without hearing it. Placeholder names shared by many personas are left out.
  The Bio box has a caption saying whether the pilot currently has a bio.
- **Pilot bios are editable.** The Appearance section shows the pilot's bio and
  a **Set** button writes it. A bio is stored as up to three texts (Bio, Bio1,
  Bio2); setting it writes the whole text into Bio and empties the others.
  Applying a persona copies all three. Generic template personas have no name
  or bio of their own, so applying one keeps the pilot's name and bio.
- **New `pilot_catalog` data file.** Generated by Scarab (personas, portraits,
  voices) and bundled with the editor. It is optional, so catalog folders from
  older Scarab versions still work.
- **Pending pilot edits are preserved.** Applying a persona updates only the
  appearance and any explicitly requested name/bio fields. Apply to Pilot leaves
  pending appearance and bio entries intact. Thanks to **altNightHawk** for the
  appearance editor and this fix in PR #41.
- 99 automated tests pass. Roster reordering was saved and reloaded in 13 real
  saves with every pilot record, player slot and unrelated field preserved;
  reversing the move restored the original bytes. Unchanged-save checks pass
  byte-for-byte on 15 real saves. In-game appearance and deployment behaviour
  have not been independently verified.

## v1.18.2
- **Searchable pilot-trait and inventory pickers.** Browse opens an owned window
  with a search field, selectable results and both scrollbars. This replaces
  the floating dropdowns for those controls; typing exact asset names still works.
- **Faction editing targets the clicked row.** Double-click selects that row
  explicitly and opens a dialog owned by the editor. Inventory count dialogs
  also use an explicit parent.
- **UI stability improvements.** Background update/catalog results are delivered
  through a queue on Tk's main thread. Loadout and mech scrolling no longer
  installs/removes application-wide wheel handlers. Python callback errors are
  recorded locally in `%LOCALAPPDATA%/MW5SaveEditor/errors.log`.
- **Backups on Open and overwrite.** Opening a valid save now creates its
  `.sav.bak` immediately, keeping an existing original backup. Save As also
  protects an existing destination. Saves are written through a temporary file
  and atomically replaced after serialization and writing succeed.
- **Experimental Cantina progression (issue #40).** An optional Cantina tab can
  set points or tier for existing career paths, or max all existing built-in
  paths. Thresholds were extracted from the installed game assets. It changes
  only progress integers, preserves jobs/offers/reward claims and campaign
  unlocks, and refuses to invent missing records. In-game reward/unlock behaviour
  remains unverified: use Save As on a test copy.
- 61 automated tests pass, including actual picker selection/cancellation,
  faction routing, backup/failed-write checks and Cantina edits. A real Cantina
  save round-trip changed just 10 bytes for maxing five paths; all other models,
  offers and reward claims remained unchanged. These changes address reports
  from Leyasu and sagggas; Leyasu's intermittent crash is not yet reproduced.

## v1.18.1
- **Pilot selection stays on the edited pilot.** Apply no longer reloads the
  first pilot's fields, making XP and cap edits appear to have been lost.
- **Unchanged pilot names retain their game text.** Applying XP, caps or salary
  preserves the original localized/formatted name payload instead of replacing
  it with an extracted string. Unicode names also display correctly.
- **Invalid input is checked before editing.** Salary, all XP fields and all
  caps are validated together before changing the pilot; caps must be 0–10.
- **Pilot traits remain reachable in small windows.** The pilot form now has
  vertical and horizontal scrollbars for smaller screens and display scaling.
- Validated with 47 automated tests and a real-save edit/save/reopen check:
  XP and caps persist, names remain unchanged, and other pilots are untouched.
  Reports from redlunatic and Leyasu prompted these fixes. In-game confirmation
  with the reported affected save remains outstanding.

## v1.18.0
- **Ashes & Ascension (DLC9) and its free update:** refreshed all four built-in
  catalogs from the installed game assets using Scarab v1.9.8 with mods excluded.
  Includes 639 mech variants with stock loadouts, 928 weapons, 49 equipment
  entries, 108 ammo entries, and 241 pilot/mech traits. Adds 79 mech variants,
  including the 13 new Clan chassis and three Inner Sphere OmniMech chassis.
- **Sort dropdowns:** choose A–Z or Z–A alongside the mech and inventory filters.
  The mech list also supports Save order; inventory column sorting remains
  available. Sorting changes display order without rearranging the save's slots.

## v1.17.4
- **Missing inventory frameworks are recovered safely.** Saves that omit an
  empty `WeaponInventory` or `EquipmentInventory` now open without the
  `NoneType`/`decoded` error. Adding an item reconstructs only the missing empty
  framework, while undecodable non-empty inventory data is preserved instead of
  being overwritten. Older exports without inventory donor templates can also
  import into an empty inventory. Confirmed against the affected save and an
  additional fully empty inventory save. (issue #35, PR #36, TheSwedishNash)

## v1.17.3
- **Mech storage now matches the game's slot model.** Adding a mech reuses the
  first vacant active-bay slot instead of continually growing the storage array,
  and removing a mech vacates its slot in place. This prevents inaccessible
  empty positions and repeated add/remove failures. (issue #32, PR #33,
  FiendishDrWu)
- **Buyback listings are no longer treated as owned mechs.** Sold mechs awaiting
  buyback stay out of the active roster and exports. Imports made by older editor
  versions also skip market and buyback wrappers while preserving genuine cold
  storage mechs. (issue #32, PR #33, FiendishDrWu)
- **Added mechs receive the correct stock variant name.** Exact clones and
  stock-template rebuilds no longer inherit a donor mech's custom name; the
  target variant is written and preserved through save round-trips. (issue #32,
  PR #33, FiendishDrWu)

## v1.17.2
- **Trait pickers are easier to read and browse.** Pilot and mech trait dropdowns
  now show the friendly name first, expand for long stock or mod-added entries,
  and sort labeled traits by their friendly names. Traits without a friendly
  label remain selectable at the bottom in alphabetical order. The save still
  receives the exact engine asset name. (issue #27, TimeDiver0)
- **Left and right arm hardpoints are separated correctly.** The body loadout
  view now groups ranged arm mounts by side while retaining their detailed
  clavicle, shoulder, upper-arm, forearm, and lower-arm regions. Melee and
  actuator mounts appear in dedicated hand panels, and the same detail is
  preserved in the list view and fire-group labels. (issue #29, PR #30,
  FiendishDrWu)
- **Built-in Scarab catalogs refreshed.** Adds `ClanEndoSteelStructure` and
  `ClanFerroFibrousArmor`, corrects spacing for Ebon Jaguar, Mad Dog, and Night
  Gyr chassis names, and removes placeholder hero-name mappings. (issue #26,
  PR #28, FiendishDrWu)

## v1.17.1
- **Empty inventories can now receive imports.** New `.mw5export` files carry one
  validated weapon/equipment donor structure, allowing imports into saves whose
  inventory arrays are completely empty. Older exports remain compatible and show
  the existing workaround when no donor is available. Tested successfully in-game
  by Volt-Ampere. (issue #21)
- **Imported commanders no longer create duplicate protected pilots.** A commander
  transferred from another save is now converted to a regular pilot while receiving
  a fresh ID, so importing Mason cannot create additional `Player1` records that
  cannot be assigned or removed. (issue #17)
- **Loadout names stay readable.** Weapon and equipment fields are wider, and their
  dropdowns expand to fit long stock or mod-added asset names while preserving the
  compact body-location layout. (issue #22, Mad5555)
- **Duncan Fisher's Warhammer display fix is permanent again.** Both
  `WHM-DNC_MDA` and `WHM-DNC_PLAYABLE_MDA` resolve to Warhammer (70t, Heavy)
  without exposing either campaign-only asset in Add Mech. The fallback now lives
  in editor code so generated Scarab catalog refreshes cannot remove it.
  (issue #24, Volt-Ampere and FiendishDrWu)

## v1.17.0
- **Experimental mod catalog support through Scarab.** The new **Catalogs...**
  dialog can run FiendishDrWu's standalone catalog generator against the user's
  MW5 install and enabled mods, validate the complete output, and load it on the
  next editor launch. Scarab runs without a console window and remains a
  separate, optional download. Scarab v1.7.4 or newer is required. Automatic
  regeneration is still future work; generation is currently user-triggered.
  (issue #18)
- **Correct armor meanings and chassis maximums.** The loadout editor now shows
  current armor, installed armor, and MDA chassis caps separately. The old
  misleading max-armor action is now **Repair armor (= installed)**, and edited
  current armor is validated against the installed allocation. Torso chassis
  caps are identified as shared front-plus-rear limits. (PR #19, FiendishDrWu)
- **Campaign date editing.** The campaign's current date can now be edited while
  preserving the save's starting date and correctly updating elapsed campaign
  days. (PR #20, FiendishDrWu)

## v1.16.1
- **Catalog data refresh + two fixes (FiendishDrWu).** The mech, item, stock-template and
  trait catalogs were regenerated from FiendishDrWu's extraction tool. Two data errors are
  corrected: the **Bullshark** was misclassified as the Berserker (now correctly 95t
  Assault), and the **King Crab KGC-001's large pulse laser** was on the wrong hardpoint
  (now at the correct right-torso EH3 slot). No functional or interface changes; coverage
  is unchanged (552 mechs, 791 weapons, 552 stock templates, 224 traits).

## v1.16.0
- **Full pilot & mech trait catalog.** The Add-Trait dropdowns (Pilots tab, and mech
  traits in Edit Loadout) now list all **224** known traits — **167 pilot** traits and
  **57 Cantina mech** traits — each with a friendly name (e.g.
  `Specialist_Laser_PilotTrait — Laser Specialist`), instead of only the traits your save
  had already encountered. So academy Graduate traits, the Specialist/Affinity lines, and
  the Cantina mech quirks are now selectable directly. Trait data contributed by
  **FiendishDrWu** (issue #15). Mod-added traits your save references are still harvested
  from the save and merged in, and any trait can still be typed in by asset name.

## v1.15.2
- **Fix: added mechs now come out at the correct tonnage.** When building an added mech
  from its chassis's factory-stock template, the editor wasn't applying the stock **rear**
  armor — a location-key mismatch (`CenterTorsoRear` vs `CenterTorso`) meant the rear
  values were never read, so the added mech kept the *donor* mech's rear armor instead.
  That left every stock-built add slightly under or over weight (e.g. a Stormcrow
  SCR-PRIME came out ~0.9t light). Rear armor is now read from the template, so an added
  mech matches its real factory-stock tonnage. Front armor, weapons and equipment were
  already correct. (issues #12 DallasSukerkin, #14 eXFDA)

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
