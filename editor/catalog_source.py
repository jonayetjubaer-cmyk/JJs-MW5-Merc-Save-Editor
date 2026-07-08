"""Where the editor's asset catalogs load from.

The catalogs are data files (Scarab's `.json.gz` format): `item_catalog`,
`mech_catalog`, `trait_catalog`, and `stock_templates`. The editor bundles a
trusted built-in set; the catalog loader modules (item_catalog / mech_catalog /
trait_catalog) and the stock-template loader read them through here.

For mod support (issue #18), Scarab -- FiendishDrWu's catalog generator -- can
read a user's MW5 install plus enabled mods (using the editor's built-in
catalogs as its base layer via `--catalog-input-dir`) and write an updated
catalog folder. Pointing the editor at that folder makes it load those catalogs
instead, so modded items / mechs / traits are known to the editor.

Because these are *data files* read at runtime (not Python modules), this works
identically from source and in the compiled binary. `activate()` records the
chosen folder; `load_catalog()` resolves and parses a catalog, preferring an
active external folder then the built-in bundle.
"""
from __future__ import annotations

import gzip
import json
import os
import sys

_CONFIG = os.path.join(os.path.expanduser("~"), ".jjmw5_save_editor.json")
# Catalogs the editor needs; a folder must provide all of them (as .json.gz,
# or plain .json) to count as a usable external catalog source.
REQUIRED = ("item_catalog", "mech_catalog", "trait_catalog", "stock_templates")
# env var the stock-template loader also reads to find an external folder
ACTIVE_ENV = "MW5EDITOR_ACTIVE_CATALOG_DIR"

_active: str | None = None


def _builtin_dirs() -> list[str]:
    """Dirs the bundled catalogs may live in (source dir, and the exe dir /
    _MEIPASS for a frozen build)."""
    out = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        out.append(meipass)
    out.append(os.path.dirname(os.path.abspath(__file__)))
    out.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    return out


def _find(dirs, basename) -> str | None:
    for d in dirs:
        for ext in (".json.gz", ".json"):
            p = os.path.join(d, basename + ext)
            if os.path.exists(p):
                return p
    return None


def configured_dir() -> str | None:
    """External catalog folder from the env var (highest priority, handy for
    testing) or the config file, or None to use the built-in catalogs."""
    d = os.environ.get("MW5EDITOR_CATALOG_DIR")
    if d:
        return d
    try:
        with open(_CONFIG, encoding="utf-8") as f:
            return json.load(f).get("catalog_dir") or None
    except Exception:
        return None


def is_valid(d: str | None) -> bool:
    """True if `d` is a folder providing all required catalogs (.json.gz/.json)."""
    return bool(d) and os.path.isdir(d) and all(
        _find([d], b) for b in REQUIRED)


def activate() -> str | None:
    """If a valid external catalog folder is configured, record it so the
    catalog loaders read from it. Returns the active folder, or None for
    built-in. Falls back to built-in silently on any problem."""
    global _active
    try:
        d = configured_dir()
        if is_valid(d):
            _active = os.path.abspath(d)
            os.environ[ACTIVE_ENV] = _active
    except Exception:
        _active = None
    return _active


def active_dir() -> str | None:
    """The external catalog folder currently in use this session, or None."""
    return _active


def catalog_path(basename: str) -> str | None:
    """Resolve a catalog data file by basename (e.g. 'item_catalog'), preferring
    the active external folder, then the built-in bundle. Accepts .json.gz then
    .json. Returns the path, or None if not found anywhere."""
    dirs = ([_active] if _active else []) + _builtin_dirs()
    return _find(dirs, basename)


def load_catalog(basename: str):
    """Parse a catalog data file to a Python object (dict), or None if missing
    or unreadable. Handles both .json.gz and .json."""
    p = catalog_path(basename)
    if not p:
        return None
    try:
        if p.endswith(".gz"):
            with gzip.open(p, "rt", encoding="utf-8") as f:
                return json.load(f)
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def set_dir(path: str | None) -> bool:
    """Persist the external catalog folder to config (or None to clear it and
    revert to built-in). Takes effect on the next launch. Returns True on
    success."""
    try:
        data = {}
        if os.path.exists(_CONFIG):
            with open(_CONFIG, encoding="utf-8") as f:
                data = json.load(f)
        if path:
            data["catalog_dir"] = path
        else:
            data.pop("catalog_dir", None)
        with open(_CONFIG, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return True
    except Exception:
        return False
