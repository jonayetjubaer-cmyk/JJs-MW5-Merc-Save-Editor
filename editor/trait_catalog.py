"""MW5 Mercs pilot / mech trait catalog (loader).

The trait data lives in `trait_catalog.json.gz` (Scarab's format). This module
loads it through catalog_source -- from an active external Scarab folder if one
is configured (mod support, issue #18), otherwise the built-in bundle -- and
exposes it for the Add-Trait dropdowns.

Pilot traits use MWPilotTraitDataAsset; mech traits use MWMechTraitDataAsset.
Both are added by asset name only, so this catalog needs no type column. The
dropdowns merge these with the traits a loaded save already references, and any
trait can still be typed in by asset name.
"""
import catalog_source

_d = catalog_source.load_catalog("trait_catalog") or {}

PILOT_TRAITS = [(x["asset_name"], x["friendly_label"]) for x in _d.get("pilot_traits", [])]
MECH_TRAITS = [(x["asset_name"], x["friendly_label"]) for x in _d.get("mech_traits", [])]

_SEP = " -- "


def display(asset: str, label: str | None = None) -> str:
    """Dropdown display string for a trait: 'Asset -- Friendly Label'."""
    return f"{asset}{_SEP}{label}" if label else asset


def dropdown_values(save_names, catalog) -> list[str]:
    """Merge save-harvested asset names with the catalog into sorted display
    strings (catalog entries get their friendly label)."""
    labels = dict(catalog)
    names = set(save_names) | set(labels)
    return sorted((display(n, labels.get(n)) for n in names), key=str.lower)


def resolve(text: str) -> str:
    """A dropdown display string (or raw typed name) -> bare asset name."""
    return text.split(_SEP, 1)[0].strip()
