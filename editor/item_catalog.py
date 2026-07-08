"""MW5 Mercs inventory item catalog (loader).

The item data lives in `item_catalog.json.gz` (Scarab's format). This module
loads it through catalog_source -- from an active external Scarab folder if one
is configured (mod support, issue #18), otherwise the built-in bundle -- and
exposes it in the shapes the editor uses.

Category -> inventory array: weapon -> WeaponInventory; equipment & ammo ->
EquipmentInventory.
"""
import catalog_source

_d = catalog_source.load_catalog("item_catalog") or {}


def _pairs(key):
    return [(x["asset_name"], x["data_asset_type"]) for x in _d.get(key, [])]


WEAPONS = _pairs("weapons")
EQUIPMENT = _pairs("equipment")
AMMO = _pairs("ammo")
CATALOG = {"weapon": WEAPONS, "equipment": EQUIPMENT, "ammo": AMMO}
CATEGORY_INVENTORY = _d.get("category_inventory",
                            {"weapon": "weapon", "equipment": "equipment", "ammo": "equipment"})
