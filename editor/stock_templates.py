"""Stock mech loadout templates (factual game data extracted from the game's
MWMechDataAsset / MWMechLoadoutAsset assets, contributed in GitHub issue #6).

One template per chassis (keyed by MDA asset name, e.g. 'CN9-A_MDA') giving the
chassis's real stock armor, structure, weapons, weapon groups and equipment.
Used to populate an added/cold-storage mech's ItemData with correct stock data
instead of an approximate clone of an unrelated donor chassis.

Only asset names + numeric stats are stored (facts about the game), the same
clean-room category as the item/chassis catalogs. Lazy-loaded on first use.
"""
from __future__ import annotations

import gzip
import json
import os
import sys

_DATA = None
_FILE = "stock_templates.json.gz"


def _candidates():
    out = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        out.append(meipass)
    out.append(os.path.dirname(os.path.abspath(__file__)))
    out.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    return out


def _load() -> dict:
    global _DATA
    if _DATA is None:
        _DATA = {}
        for base in _candidates():
            p = os.path.join(base, _FILE)
            if os.path.exists(p):
                try:
                    with gzip.open(p, "rb") as f:
                        _DATA = json.loads(f.read().decode("utf-8"))
                except Exception:
                    _DATA = {}
                break
    return _DATA


def stock_template(chassis: str):
    """Stock template dict for a chassis (accepts 'CN9-A' or 'CN9-A_MDA'),
    or None if there isn't one."""
    if not chassis:
        return None
    mda = chassis if chassis.endswith("_MDA") else chassis + "_MDA"
    return _load().get(mda)


def available() -> bool:
    return bool(_load())


# Asset-name -> human label for the structure/armor types recorded in the
# templates (issue #12 data from FiendishDrWu). Clan variants are flagged so a
# user can tell a Clan Endo/Ferro chassis from the Inner Sphere kind.
_TYPE_LABELS = {
    "StandardArmor": "Standard",
    "FerroFibrousArmor": "Ferro-Fibrous",
    "ClanFerroFibrousArmor": "Ferro-Fibrous (Clan)",
    "StandardStructure": "Standard",
    "EndoSteelStructure": "Endo-Steel",
    "ClanEndoSteelStructure": "Endo-Steel (Clan)",
}


def type_label(asset_name: str | None) -> str:
    """Human label for an armor/structure type asset name (e.g.
    'FerroFibrousArmor' -> 'Ferro-Fibrous'). Falls back to the raw name."""
    if not asset_name:
        return "Standard"
    return _TYPE_LABELS.get(asset_name, asset_name)


def stock_types(chassis: str) -> tuple[str, str] | None:
    """(armor_label, structure_label) for a chassis, or None if no template."""
    tpl = stock_template(chassis)
    if tpl is None:
        return None
    return type_label(tpl.get("armorType")), type_label(tpl.get("structureType"))
