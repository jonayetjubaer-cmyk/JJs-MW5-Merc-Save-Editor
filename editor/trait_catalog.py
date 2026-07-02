"""Curated pilot / mech trait asset-name catalog (issue #15).

The Add-Trait dropdowns are otherwise limited to traits the loaded save has
already referenced (SaveFile.referenced_traits), so traits the save has never
seen -- academy Graduate traits, Laser Master, the AC-x Masters, etc. -- can
only be typed in by exact asset name. This catalog merges known-good asset
names into those dropdowns, with a friendly label so traits are searchable
by their in-game name.

Naming convention (confirmed from community sources, see issue #15): vanilla
pilot-trait assets end in `_PilotTrait`, e.g. `Expert_AC10_PilotTrait`.
The definitive full list is tracked in issue #15 -- extend PILOT_TRAITS /
MECH_TRAITS with (asset_name, friendly_label) pairs as entries are confirmed.
Only add names confirmed from real game data / reputable extractions; the game
silently ignores unknown asset ids, so a wrong entry is inert but misleading.

Trait types: pilot traits are MWPilotTraitDataAsset, mech (Cantina) traits are
MWMechTraitDataAsset -- both are added by asset name only, so this catalog
needs no type column.
"""

# (asset_name, friendly_label). Confirmed verbatim from the vanilla assets the
# "Weapon Expert Trait Fix" mod overrides (mod overrides must match vanilla
# asset names exactly). Full list pending -- issue #15.
PILOT_TRAITS = [
    ("Expert_AC10_PilotTrait", "AC/10 Expert"),
    ("Expert_AC20_PilotTrait", "AC/20 Expert"),
]

MECH_TRAITS = []

_SEP = " — "  # " — " (asset names never contain this)


def display(asset: str, label: str | None = None) -> str:
    """Dropdown display string for a trait: 'Asset — Friendly Label'."""
    return f"{asset}{_SEP}{label}" if label else asset


def dropdown_values(save_names, catalog) -> list[str]:
    """Merge save-harvested asset names with the curated catalog into sorted
    display strings (catalog entries get their friendly label)."""
    labels = dict(catalog)
    names = set(save_names) | set(labels)
    return sorted((display(n, labels.get(n)) for n in names), key=str.lower)


def resolve(text: str) -> str:
    """A dropdown display string (or raw typed name) -> bare asset name."""
    return text.split(_SEP, 1)[0].strip()
