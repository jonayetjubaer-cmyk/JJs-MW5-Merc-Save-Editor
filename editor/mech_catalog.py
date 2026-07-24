"""MW5 Mercs mech catalog (loader).

The chassis / variant / tonnage / hero data lives in `mech_catalog.json.gz`
(Scarab's format). This module loads it through catalog_source -- from an active
external Scarab folder if one is configured (mod support, issue #18), otherwise
the built-in bundle -- and exposes the lookups and display helpers the editor
uses.
"""
import catalog_source

_d = catalog_source.load_catalog("mech_catalog") or {}

CHASSIS = _d.get("chassis", {})
CHASSIS_TONNAGE = _d.get("chassis_tonnage", {})
HERO_NAMES = dict(_d.get("hero_names", {}))
DISPLAY_ONLY_VARIANTS = dict(_d.get("display_only_variants", {}))

# Campaign-only assets can be intentionally absent from Scarab's addable mech
# catalog while still appearing in saves. Keep high-confidence display metadata
# here so a generated catalog refresh cannot regress their names/tonnage.
DISPLAY_ONLY_VARIANTS.setdefault("WHM-DNC", "Warhammer")
HERO_NAMES.setdefault("WHM-DNC", "Duncan Fisher")

# Derived (kept consistent with CHASSIS regardless of the file's own ordering).
ALL_VARIANTS = sorted(v for vs in CHASSIS.values() for v in vs)
VARIANT_TO_CHASSIS = {v: name for name, vs in CHASSIS.items() for v in vs}
VARIANT_TO_CHASSIS.update(DISPLAY_ONLY_VARIANTS)


def weight_class(tons) -> str:
    if not tons:
        return ""
    if tons <= 35:
        return "Light"
    if tons <= 55:
        return "Medium"
    if tons <= 75:
        return "Heavy"
    return "Assault"


def chassis_info(name: str):
    chassis = VARIANT_TO_CHASSIS.get(variant_code(name))
    tons = CHASSIS_TONNAGE.get(chassis) if chassis else None
    return (tons, weight_class(tons))


def asset_name(variant: str) -> str:
    return variant if variant.endswith("_MDA") else variant + "_MDA"


def variant_code(name: str) -> str:
    code = name[:-4] if name.endswith("_MDA") else name
    if code.endswith("_PLAYABLE"):
        code = code[:-len("_PLAYABLE")]
    return code


def display(name: str) -> str:
    code = variant_code(name)
    chassis = VARIANT_TO_CHASSIS.get(code)
    if not chassis:
        return code
    hero = HERO_NAMES.get(code)
    if hero:
        return f'{chassis} "{hero}" ({code})'
    return f"{chassis} ({code})"


def _label(name, code):
    hero = HERO_NAMES.get(code)
    return f"{name}  {code}" + (f'  "{hero}"' if hero else "")


LABELED = [(_label(n, v), v) for n in sorted(CHASSIS) for v in sorted(CHASSIS[n])]
