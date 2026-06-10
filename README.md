<p align="center">
  <img src="assets/logo.png" alt="JJ's MW5 Merc Save Editor" width="180">
</p>

<h1 align="center">JJ's MW5 Merc Save Editor</h1>

<p align="center">
  A free save editor for <b>MechWarrior 5: Mercenaries</b> — edit your mechs,
  pilots, inventory, C-Bills and faction standings in a simple Windows app.
</p>

---

## ⬇️ Download

**[➡️ Download the latest version from the Releases page](../../releases/latest)**

Grab `MW5SaveEditor.exe`, double-click it, and you're in. No install, no Python,
nothing else needed.

> 💡 The first launch takes a few seconds (the app unpacks itself). That's normal.

---

## ✨ What you can edit

- **Mechs** — add any chassis (full vanilla + DLC roster), swap a mech's chassis,
  repair armor (single or *all* mechs at once), or remove mechs.
- **Pilots** — edit callsign, name, salary, and all skill XP; add brand-new
  pilots or remove them.
- **Inventory** — add weapons, equipment, and ammo (with searchable lists), set
  counts, or remove items.
- **C-Bills** — set your money to anything (one-click max).
- **Factions** — edit your standing with all 17 factions and your company
  reputation.

---

## 📸 Screenshots

| Mechs | Loadout editor (weapons · equipment · armor) |
|:---:|:---:|
| ![Mechs tab](assets/screenshot-mechs.png) | ![Loadout editor](assets/screenshot-loadout.png) |
| **Pilots** | **Inventory** |
| ![Pilots tab](assets/screenshot-pilots.png) | ![Inventory tab](assets/screenshot-inventory.png) |
| **Factions** | **Set Hardpoints** |
| ![Factions tab](assets/screenshot-factions.png) | ![Set Hardpoints](assets/screenshot-sethardpoints.png) |

---

## 🕹️ How to use

1. **Back up your save first** (seriously — see below).
2. Open `MW5SaveEditor.exe`.
3. Click **Open…** — it points straight at your MW5 saves folder
   (`%LOCALAPPDATA%\MW5Mercs\Saved\SaveGames`).
4. Edit what you like across the **Mechs / Pilots / Inventory / Factions** tabs.
5. Click **Save**, then load the save in-game.

---

## ⚠️ Please read — back up your saves

This tool edits your save files directly. **Always keep a backup** before editing.

- The editor automatically writes a `.bak` copy the first time it saves over a
  file — but you should keep your own copy too.
- Use at your own risk. Save editing is not supported by the game's developers.

---

## 🛡️ "Windows protected your PC" / antivirus / "malware" flag

Because this is a small indie tool that isn't code-signed (signing costs money),
Windows SmartScreen or your antivirus may warn you the first time you run it.
This is normal for tools like this — it does **not** mean there's anything wrong.
To run it: click **More info → Run anyway**.

**About "malware" detections (e.g. `W32.Malware.*`) — this is a false positive.**
The app is built with [PyInstaller](https://pyinstaller.org/), which wraps Python
apps in a small self-extracting launcher. That launcher's behaviour trips some
antivirus engines' *heuristics*, so they flag the **launcher**, not this code —
a well-documented PyInstaller issue affecting many legitimate tools. Windows
Defender reports it clean, and the full source is right here in this repo so you
can verify exactly what it does. If your scanner is strict, use the
**`-folder` (one-folder) download**, which doesn't self-extract and generally
isn't flagged.

---

## ❓ FAQ

**Does it work with all the DLC?**
Yes — the mech and item lists include vanilla + DLC content. The game safely
ignores anything from a DLC you don't own.

**What's the difference between an "exact" and "approximate" added mech?**
If you already own a mech of that chassis, Add Mech makes a perfect duplicate.
If you don't, a mech's true layout (engine, hardpoints, max armor) lives in the
*game's* files, not the save — so it can't be built perfectly. In that case you
get an **approximate** clone with its weapons stripped: open it in the Mech Lab
and refit it, and everything (including weapon groups) works correctly.

**My added mech's weapon groups won't stick / weapons won't fire.**
Two things: (1) In the Mech Lab's **Weapon Groups** tab, make sure each weapon is
assigned to a group (1–6) — unassigned weapons don't fire. (2) For an
*approximate* added mech, **strip and refit it** first; it ships with no weapons
so you start from a clean, correct loadout.

**Will this corrupt my save?**
It's built around a lossless save format — saving without making changes produces
a byte-for-byte identical file. Still: **keep a backup.**

---

## 🛠️ Build / run from source

The editor is pure Python + Tkinter (Tkinter ships with Python on Windows), so
there are no dependencies to run it from source:

```bash
python editor/gui.py
```

To rebuild the standalone EXE (requires [PyInstaller](https://pyinstaller.org/)):

```bash
pip install pyinstaller pillow
python -m PyInstaller --noconfirm --onefile --windowed --name "MW5SaveEditor" ^
  --icon editor/app_icon.ico ^
  --add-data "editor/app_icon.ico;." --add-data "editor/app_icon.png;." ^
  editor/gui.py
```

### Project layout

| Path | What it is |
|---|---|
| `editor/ue_property.py` | Generic, lossless Unreal Engine tagged-property reader/writer |
| `editor/savefile.py` | High-level save API (`SaveFile`, `Mech`, `Pilot`, inventory, factions) |
| `editor/gui.py` | The Tkinter GUI |
| `editor/mech_catalog.py` / `item_catalog.py` | Chassis + item asset-name catalogs |
| `editor/inject_mech.py` | Standalone CLI proof-of-concept for adding a mech |
| `editor/test_roundtrip.py` | Round-trip validation harness |
| `tools/diff_saves.py` | Binary diff helper used while reverse-engineering |
| `notes/format_notes.md` | Reverse-engineered save format notes (the two big gotchas live here) |

## 🤝 Contributing

PRs and issues welcome! Good first contributions:

- **More mech / weapon / equipment asset names** — the catalogs are seeded from
  real save data + community lists but aren't exhaustive.
- **A "Mech Cold Storage" tab** (stored/mothballed mechs).
- **Per-chassis max armor values** so added/swapped mechs spawn fully armored
  instead of needing an in-game refit.

The golden rule of this codebase: **a no-op save must stay byte-for-byte
identical to the original.** `editor/test_roundtrip.py` and the model sweep in
`notes/format_notes.md` are how that's validated — please keep it lossless.

## 📝 Changelog

**v1.8.0**
- **Rare / DLC weapons & gear** now appear in the dropdowns. When a save loads,
  the editor harvests every weapon/equipment/ammo your save references (from
  markets, missions, enemy mechs, your own gear) and adds them to the Inventory
  and Loadout pickers — so anything you've encountered (Clan ER PPCs, pulse
  lasers, chem lasers, Inferno/Hotloaded ammo, etc.) is selectable, with
  guaranteed-valid names.

**v1.7.0**
- **Pilot skill caps** are now editable! Each skill in the Pilots tab has a
  **Cap (1–10)** field next to its XP, plus a **Max caps (10)** button — set a
  pilot to full potential, then train them up in-game. (Gunnery/Piloting don't
  use the cap system, so those fields are disabled.)

**v1.6.0**
- Builds and releases are now **automated via GitHub Actions** — a version tag
  compiles the Nuitka EXE and publishes it to the GitHub release (and Nexus).
  No functional changes from v1.5.0.

**v1.5.0**
- Now built with **Nuitka** (compiled to a native binary) instead of PyInstaller.
  Same app, but it no longer trips antivirus/"malware" false positives the way
  the PyInstaller build did. (v1.4.0 remains available as the PyInstaller build.)

**v1.4.0**
- **Edit Loadout** now also edits **equipment** — heat sinks, **ammo**, jump
  jets, MASC — per slot, alongside weapons, fire groups, and armor. The options
  are filtered to each slot's type (e.g. ammo/heat sinks go in general slots,
  jump jets in jump-jet slots).

**v1.3.0**
- New **Set Hardpoints…** button: apply a real hardpoint layout to a mech, then
  fit weapons in Edit Loadout. Layouts are harvested from your save (owned mechs,
  market, mission records) — a same-chassis layout is exact; others are
  "borrowed".
- **Add Mech** now uses a chassis's *real* hardpoint layout automatically when
  your save has one on record (e.g. a mech you've seen in a mission), so added
  mechs come out with correct, ready-to-fit hardpoints.

> ℹ️ A chassis's true hardpoints live in the game's files, not the save, so the
> editor can only show/apply layouts it has actually seen. To get a chassis's
> real hardpoints when none exist in your save, fit that mech once in the in-game
> Mech Lab and save — the editor will then show them all.

**v1.2.0**
- You can now build a loadout on a mech that has **no hardpoints** (an
  approximate added mech). Hit **Edit Loadout…** on an empty mech and pick a mech
  to copy a hardpoint layout from — then fit weapons and set groups as usual.
- Approximate added mechs now keep their (emptied) hardpoints instead of being
  fully stripped, so they're editable right away.

**v1.1.0**
- **Mech loadout editor!** Select a mech → **Edit Loadout…** to:
  - Swap, remove, or fill weapons per hardpoint (the list is filtered to each
    slot's class — energy/ballistic/missile/melee — so you can't put an
    autocannon in a laser slot).
  - Set each weapon's **fire group** (1–6) directly — no Mech Lab needed.
  - Edit **armor** per location, with a one-click "Max armor" button.

**v1.0.2**
- **Smarter Add Mech.** If you already own a mech of the chosen chassis, it now
  adds an **exact, fully-working duplicate** (weapons + weapon groups intact).
  For a chassis you don't own, it adds an **approximate** clone with its weapons
  stripped — so it no longer carries stale weapon groups (which caused added
  mechs' fire groups to reset to 1). Refit it in the Mech Lab and groups stick.

**v1.0.1**
- Mech list and the Add-Mech picker now show **friendly names** (e.g. *Javelin
  (JVN-10F)*) and **hero nicknames** (*Atlas "Boar's Head"*, *Centurion
  "Yen-Lo-Wang"*, …) instead of raw asset codes.
- Version now shown in the window title.

**v1.0.0**
- Initial release: Mechs, Pilots, Inventory, C-Bills, and Faction Standings.

## 📄 License

[MIT](LICENSE) — do whatever you like, just keep the copyright notice.

---

<p align="center"><i>Not affiliated with Piranha Games or Microsoft. MechWarrior is a registered trademark of its respective owners.</i></p>
