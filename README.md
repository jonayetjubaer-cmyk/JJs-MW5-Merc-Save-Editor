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

## 🛡️ "Windows protected your PC" / antivirus warning

Because this is a small indie tool that isn't code-signed (signing costs money),
Windows SmartScreen or your antivirus may warn you the first time you run it.
This is normal for tools like this — it does **not** mean there's anything wrong.

To run it: click **More info → Run anyway**.

---

## ❓ FAQ

**Does it work with all the DLC?**
Yes — the mech and item lists include vanilla + DLC content. The game safely
ignores anything from a DLC you don't own.

**I added a heavier mech (e.g. an Atlas) and it shows "needs repair" — why?**
A swapped chassis keeps the armor amount of the mech it was based on. Just refit
it in the in-game Mech Lab to load its proper armor.

**Will this corrupt my save?**
It's built around a lossless save format — saving without making changes produces
a byte-for-byte identical file. Still: **keep a backup.**

---

<p align="center"><i>Not affiliated with Piranha Games or Microsoft. MechWarrior is a registered trademark of its respective owners.</i></p>
