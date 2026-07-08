"""Where the editor's asset catalogs load from.

Default: the built-in catalogs bundled with the editor (which are themselves
Scarab output -- same data, same source). For mod support, Scarab (FiendishDrWu's
catalog generator, issue #18) reads a user's MW5 install plus enabled mods and
writes a catalog folder. Pointing the editor at that folder makes it load those
catalogs instead, so modded items / mechs / traits are known to the editor.

IN-HOUSE TESTING SCOPE: this loads Scarab's *Python-format* output by prepending
the chosen folder to sys.path, which works when running the editor from source
(the current, source-based testing model). A data-file (JSON / json.gz) loader
for the shipped binary is the planned follow-up, once Scarab's JSON format is
finalized -- at which point the built-in catalogs move to accessible data files
(the "Solution B" end state discussed in issue #18).

`activate()` MUST run before any catalog module (item_catalog / mech_catalog /
trait_catalog / stock_templates) is imported, so it is called at the very top of
gui.py before those imports.
"""
from __future__ import annotations

import json
import os
import sys

_CONFIG = os.path.join(os.path.expanduser("~"), ".jjmw5_save_editor.json")
# Scarab's python-format catalog set; all must be present for a folder to count.
REQUIRED = ("item_catalog.py", "mech_catalog.py", "trait_catalog.py",
            "stock_templates.json.gz")
# env var the stock-template loader reads to find an external stock_templates.json.gz
ACTIVE_ENV = "MW5EDITOR_ACTIVE_CATALOG_DIR"

# This mechanism prepends a folder to sys.path so Python imports the catalog
# *modules* from it. That works from source, but NOT in the Nuitka-built exe,
# where the catalog modules are compiled into the binary and take precedence
# over sys.path. So when running compiled we do nothing -- the data-file (JSON)
# loader is the path there (Solution B, issue #18). This keeps the shipped
# binary honest: it never claims an external catalog it can't actually load.
_IS_COMPILED = "__compiled__" in globals() or bool(getattr(sys, "frozen", False))

_active: str | None = None


def configured_dir() -> str | None:
    """The external catalog folder from the env var (highest priority, handy for
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
    """True if `d` is a folder containing a complete Scarab python catalog set."""
    return bool(d) and os.path.isdir(d) and all(
        os.path.exists(os.path.join(d, f)) for f in REQUIRED)


def activate() -> str | None:
    """If a valid external catalog folder is configured, prepend it to sys.path
    (so the catalog modules import from there) and record it for the
    stock-template loader. Returns the active folder, or None for built-in.
    Falls back to built-in silently on any problem."""
    global _active
    if _IS_COMPILED:
        return None  # data-file loader handles the shipped binary (see above)
    try:
        d = configured_dir()
        if is_valid(d):
            d = os.path.abspath(d)
            if d not in sys.path:
                sys.path.insert(0, d)
            os.environ[ACTIVE_ENV] = d
            _active = d
    except Exception:
        _active = None
    return _active


def active_dir() -> str | None:
    """The external catalog folder currently in use this session, or None."""
    return _active


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
