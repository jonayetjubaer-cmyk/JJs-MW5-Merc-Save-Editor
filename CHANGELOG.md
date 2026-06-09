# Changelog

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
