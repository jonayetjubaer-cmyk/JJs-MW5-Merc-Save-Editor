"""Vanilla + DLC MW5 Mercs mech chassis catalog.

Asset names follow `<VARIANT>_MDA` (confirmed from save data). Originally sourced
from the Sarna roster, then filtered against the game's real asset list (the
UnifiedDataCache + per-DLC tables contributed by FiendishDrWu in GitHub issue #2) so every entry
is a chassis the game can actually spawn. Tabletop-only variants that MW5 Mercs
does not ship were removed -- adding one used to write a mech the game silently
dropped on load. The game still ignores assets from DLC you do not own.
"""

CHASSIS = {
    'Adder': ['ADR-A', 'ADR-B', 'ADR-D', 'ADR-PRIME', 'ADR-S'],
    'Annihilator': ['ANH-1A', 'ANH-1E', 'ANH-1X', 'ANH-2A', 'ANH-IR'],
    'Archer': ['ARC-2K', 'ARC-2P', 'ARC-2R', 'ARC-2RB', 'ARC-2S', 'ARC-2W', 'ARC-AGC', 'ARC-T'],
    'Assassin': ['ASN-101', 'ASN-21', 'ASN-25', 'ASN-26', 'ASN-27', 'ASN-DD'],
    'Atlas': ['AS7-BH', 'AS7-D', 'AS7-D-H', 'AS7-K', 'AS7-KR', 'AS7-P', 'AS7-RS'],
    'Awesome': ['AWS-8Q', 'AWS-8R', 'AWS-8T', 'AWS-8V', 'AWS-9M', 'AWS-PB'],
    'Banshee': ['BNC-2P', 'BNC-3E', 'BNC-3M', 'BNC-3P', 'BNC-3S', 'BNC-LM', 'BNC-SR'],
    'Battlemaster': ['BLR-1D', 'BLR-1G', 'BLR-1G-S', 'BLR-1GHE', 'BLR-1M', 'BLR-1P', 'BLR-1S', 'BLR-3M'],
    'Berserker': ['BSK-1', 'BSK-2', 'BSK-3', 'BSK-5', 'BSK-6', 'BSK-7', 'BSK-BT'],
    'Black Knight': ['BL-6-KNT', 'BL-6B-KNT', 'BL-7-KNT', 'BL-7-KNT-L', 'BL-7-KNT-P', 'BL-P-KNT', 'BL-P-KNT2'],
    'Blackjack': ['BJ-1', 'BJ-1DB', 'BJ-1DC', 'BJ-1X', 'BJ-3', 'BJ-A'],
    'Cataphract': ['CTF-0X', 'CTF-0XP', 'CTF-1X', 'CTF-2P', 'CTF-2X', 'CTF-4X', 'CTF-IM', 'CTF-VE1'],
    'Catapult': ['CPLT-A1', 'CPLT-BB', 'CPLT-C1', 'CPLT-C1B', 'CPLT-C4', 'CPLT-J', 'CPLT-K2', 'CPLT-K2-S'],
    'Centurion': ['CN9-A', 'CN9-AH', 'CN9-AL', 'CN9-D', 'CN9-P', 'CN9-YLW', 'CN9-YLW2'],
    'Champion': ['CHP-1N', 'CHP-1N2', 'CHP-1NB', 'CHP-2N', 'CHP-BF'],
    'Charger': ['CGR-1A1', 'CGR-1A5', 'CGR-1P5', 'CGR-3K', 'CGR-3K-S', 'CGR-N7'],
    'Cicada': ['CDA-2A', 'CDA-2B', 'CDA-3C', 'CDA-3M', 'CDA-RCX', 'CDA-X5'],
    'Commando': ['COM-1B', 'COM-1D', 'COM-2D', 'COM-2P', 'COM-3A', 'COM-TDK'],
    'Corsair': ['COR-LZ', 'COR-PVT'],
    'Crab': ['CRB-20', 'CRB-27', 'CRB-27B', 'CRB-27SL', 'CRB-FL'],
    'Crusader': ['CRD-2R', 'CRD-3D', 'CRD-3K', 'CRD-3L', 'CRD-3R', 'CRD-4D', 'CRD-4K', 'CRD-4L', 'CRD-5M', 'CRD-5S', 'CRD-CR', 'CRD-SA2'],
    'Cyclops': ['CP-10-P', 'CP-10-Q', 'CP-10-Z', 'CP-11-A', 'CP-11-P', 'CP-S'],
    'Dervish': ['DV-6M', 'DV-7D', 'DV-FR'],
    'Dire Wolf': ['DWF-A', 'DWF-B', 'DWF-P', 'DWF-PRIME', 'DWF-S', 'DWF-W'],
    'Dragon': ['DRG-1C', 'DRG-1G', 'DRG-1G-S', 'DRG-1N', 'DRG-5N', 'DRG-FANG', 'DRG-FLAME', 'DRG-SDW'],
    'Enforcer': ['ENF-4P', 'ENF-4R', 'ENF-5P', 'ENF-GH'],
    'Executioner': ['EXE-A', 'EXE-B-A', 'EXE-B-B', 'EXE-B-C', 'EXE-B-PRIME', 'EXE-D', 'EXE-PRIME'],
    'Fire Moth': ['FMT-1', 'FMT-A', 'FMT-B', 'FMT-C', 'FMT-D', 'FMT-PRIME'],
    'Firestarter': ['FS9-A', 'FS9-E', 'FS9-FS', 'FS9-H', 'FS9-K', 'FS9-M', 'FS9-S', 'FS9-S1', 'FS9-X1'],
    'Flea': ['FLE-15', 'FLE-16', 'FLE-17', 'FLE-RCX'],
    'Gargoyle': ['GAR-A', 'GAR-D', 'GAR-P', 'GAR-PRIME'],
    'Grasshopper': ['GHR-4P', 'GHR-5H', 'GHR-5J', 'GHR-5M', 'GHR-5N', 'GHR-5P', 'GHR-MJ'],
    'Griffin': ['GRF-1E', 'GRF-1N', 'GRF-1P', 'GRF-1S', 'GRF-2N', 'GRF-3M', 'GRF-AR'],
    'Hatamoto-Chi': ['HTM-26P', 'HTM-26T', 'HTM-26T-S', 'HTM-27T', 'HTM-27W', 'HTM-ON'],
    'Hatchetman': ['HCT-3F', 'HCT-5S', 'HCT-MA', 'HCT-RCX'],
    'Hellbringer': ['HBR-A', 'HBR-B', 'HBR-F', 'HBR-P', 'HBR-PRIME'],
    'Highlander': ['HGN-732', 'HGN-732B', 'HGN-733', 'HGN-733C', 'HGN-733P', 'HGN-733PP', 'HGN-HM', 'HGN-RS', 'HGN-VEST'],
    'Hunchback': ['HBK-4G', 'HBK-4H', 'HBK-4HP', 'HBK-4J', 'HBK-4P', 'HBK-4SP', 'HBK-GI', 'HBK-RCX', 'HBK-VEST'],
    'JagerMech': ['JM6-A', 'JM6-B2', 'JM6-DD', 'JM6-FB', 'JM6-S'],
    'Javelin': ['JVN-10F', 'JVN-10N', 'JVN-10P', 'JVN-HT'],
    'Jenner': ['JR7-D', 'JR7-F', 'JR7-K', 'JR7-O', 'JR7-P'],
    'King Crab': ['KGC-000', 'KGC-0000', 'KGC-000B', 'KGC-CAR', 'KGC-KJ'],
    'Kintaro': ['KTO-18', 'KTO-18P', 'KTO-19', 'KTO-19b', 'KTO-20', 'KTO-GB'],
    'Kit Fox': ['KFX-C', 'KFX-D', 'KFX-E', 'KFX-P', 'KFX-PRIME', 'KFX-S'],
    'Loader King': ['LDK-IDM', 'LDK-SA5', 'LDK-X1A', 'LDK-X1B', 'LDK-X2A', 'LDK-X3A'],
    'Locust': ['LCT-1E', 'LCT-1M', 'LCT-1S', 'LCT-1V', 'LCT-3S', 'LCT-3V', 'LCT-PB'],
    'Longbow': ['LGB-0W', 'LGB-0W2', 'LGB-7Q', 'LGB-8C', 'LGB-HS', 'LGB-RCX', 'LGB-WD1'],
    'Mad Dog': ['MDD-A', 'MDD-B', 'MDD-C', 'MDD-PRIME', 'MDD-S'],
    'Marauder': ['MAD-2R', 'MAD-3D', 'MAD-3L', 'MAD-3M', 'MAD-3R', 'MAD-4A', 'MAD-5A', 'MAD-5D', 'MAD-AH', 'MAD-BH', 'MAD-BH2'],
    'Mauler': ['MAL-1P', 'MAL-1R', 'MAL-2P', 'MAL-KO', 'MAL-MX90', 'MAL-MX90-S'],
    'Mist Lynx': ['MLX-A', 'MLX-B', 'MLX-C', 'MLX-D', 'MLX-P', 'MLX-PRIME'],
    'Nightstar': ['NSR-9J'],
    'Nova': ['NVA-A', 'NVA-B', 'NVA-C', 'NVA-D', 'NVA-PRIME', 'NVA-S'],
    'Orion': ['ON1-K', 'ON1-M', 'ON1-P', 'ON1-V', 'ON1-VA', 'ON1-XM1', 'ON1-YAJ'],
    'Panther': ['PNT-10P', 'PNT-8Z', 'PNT-9R', 'PNT-KK'],
    'Phoenix Hawk': ['PXH-1', 'PXH-1B', 'PXH-1K', 'PXH-1P', 'PXH-2', 'PXH-3S', 'PXH-KB', 'PXH-KK'],
    'Quickdraw': ['QKD-4G', 'QKD-4H', 'QKD-4P', 'QKD-5A', 'QKD-5K', 'QKD-5P', 'QKD-IV4', 'QKD-SC'],
    'Raven': ['RVN-1X', 'RVN-2X', 'RVN-3L', 'RVN-4X', 'RVN-H'],
    'Rifleman': ['RFL-3C', 'RFL-3N', 'RFL-4D', 'RFL-DB', 'RFL-DNA', 'RFL-LK', 'RFL-RCX'],
    'Shadow Cat': ['SHC-A', 'SHC-B', 'SHC-M', 'SHC-P', 'SHC-PRIME'],
    'Shadow Hawk': ['SHD-1P', 'SHD-2D', 'SHD-2D2', 'SHD-2H', 'SHD-2K', 'SHD-2P', 'SHD-5M', 'SHD-GD'],
    'Spider': ['SDR-5D', 'SDR-5K', 'SDR-5V', 'SDR-A', 'SDR-RCX'],
    'Stalker': ['STK-3F', 'STK-3FB', 'STK-3H', 'STK-4N', 'STK-M'],
    'Stormcrow': ['SCR-A', 'SCR-C', 'SCR-D', 'SCR-PRIME'],
    'Summoner': ['SMN-B', 'SMN-C', 'SMN-D', 'SMN-F', 'SMN-M', 'SMN-PRIME'],
    'Thunderbolt': ['TDR-5S', 'TDR-5S-T', 'TDR-5SD', 'TDR-5SE', 'TDR-5SS', 'TDR-9SE'],
    'Timber Wolf': ['TBR-A', 'TBR-C', 'TBR-D', 'TBR-PRIME', 'TBR-S'],
    'Trebuchet': ['TBT-3C', 'TBT-5J', 'TBT-5N', 'TBT-5P', 'TBT-7K', 'TBT-7M', 'TBT-LG'],
    'UrbanMech': ['UM-K9', 'UM-R60', 'UM-R60L', 'UM-SA1', 'UM-SC'],
    'Victor': ['VTR-9A1', 'VTR-9B', 'VTR-9K', 'VTR-9P', 'VTR-9S', 'VTR-BSK', 'VTR-DS'],
    'Vindicator': ['VND-1AA', 'VND-1P', 'VND-1R', 'VND-1SIB', 'VND-1SIC', 'VND-1X'],
    'Viper': ['VPR-A', 'VPR-B', 'VPR-C', 'VPR-D', 'VPR-P', 'VPR-PRIME'],
    'Vulcan': ['VL-2P', 'VL-2T', 'VL-5T', 'VL-BL'],
    'Warhammer': ['WHM-6D', 'WHM-6K', 'WHM-6L', 'WHM-6R', 'WHM-6RB', 'WHM-BW', 'WHM-DNC'],
    'Warhawk': ['WHK-A', 'WHK-B', 'WHK-C', 'WHK-PRIME'],
    'Wolfhound': ['WLF-1', 'WLF-1A', 'WLF-1B', 'WLF-GR'],
    'Wolverine': ['WVR-6K', 'WVR-6M', 'WVR-6P', 'WVR-6R', 'WVR-7H', 'WVR-Q'],
    'Zeus': ['ZEU-5S', 'ZEU-5T', 'ZEU-6S', 'ZEU-6T', 'ZEU-9S', 'ZEU-SA3', 'ZEU-SK'],
}

ALL_VARIANTS = sorted(v for vs in CHASSIS.values() for v in vs)

# variant code -> chassis display name (e.g. "AS7-D" -> "Atlas")
VARIANT_TO_CHASSIS = {v: name for name, vs in CHASSIS.items() for v in vs}

# Well-known hero / named variants (high-confidence MW5 names only).
HERO_NAMES = {
    "AS7-BH": "Boar's Head", "AS7-D-H": "Hero", "CN9-YLW": "Yen-Lo-Wang",
    "CN9-YLW2": "Yen-Lo-Wang", "HBK-GI": "Grid Iron", "LCT-PB": "Pirate's Bane",
    "COM-TDK": "The Death's Knell", "PNT-KK": "Katana Kat", "AWS-PB": "Pretty Baby",
    "MAD-BH": "Bounty Hunter", "MAD-BH2": "Bounty Hunter", "WHM-BW": "Black Widow",
    "RFL-DNA": "Diana", "CPLT-J": "Jester", "HGN-HM": "Heavy Metal", "STK-M": "Misery",
    "VTR-DS": "Dragon Slayer", "CP-S": "Sleipnir", "KGC-KJ": "Kaiju", "JR7-O": "Oxide",
    "CDA-X5": "X-5", "ON1-YAJ": "Yajima", "DRG-FANG": "Fang", "DRG-FLAME": "Flame",
    "DRG-SDW": "Shadow", "LGB-HS": "Hailstorm", "LDK-IDM": "Indomitable",
    "MAL-MX90": "MX90", "BLR-1GHE": "Hellslinger", "VL-BL": "Bloodlust",
    "GHR-MJ": "Mjolnir", "CGR-N7": "N7",
}


# Per-chassis tonnage (public MW5 roster facts, used only for display: weight-
# class colour-coding and a tonnage badge -- no game assets involved).
CHASSIS_TONNAGE = {
    # Light
    "Adder": 35, "Commando": 25, "Fire Moth": 20, "Firestarter": 35, "Flea": 20,
    "Javelin": 30, "Jenner": 35, "Kit Fox": 30, "Locust": 20, "Mist Lynx": 25,
    "Panther": 35, "Raven": 35, "Spider": 30, "UrbanMech": 30, "Wolfhound": 35,
    # Medium
    "Assassin": 40, "Blackjack": 45, "Centurion": 50, "Cicada": 40, "Crab": 50,
    "Dervish": 55, "Enforcer": 50, "Griffin": 55, "Hatchetman": 45, "Hunchback": 50,
    "Kintaro": 55, "Nova": 50, "Phoenix Hawk": 45, "Shadow Cat": 45, "Shadow Hawk": 55,
    "Stormcrow": 55, "Trebuchet": 50, "Vindicator": 45, "Viper": 40, "Vulcan": 40,
    "Wolverine": 55,
    # Heavy
    "Archer": 70, "Black Knight": 75, "Cataphract": 70, "Catapult": 65, "Champion": 60,
    "Crusader": 65, "Dragon": 60, "Grasshopper": 70, "Hellbringer": 65, "JagerMech": 65,
    "Loader King": 65, "Mad Dog": 60, "Marauder": 75, "Orion": 75, "Quickdraw": 60,
    "Rifleman": 60, "Summoner": 70, "Thunderbolt": 65, "Timber Wolf": 75, "Warhammer": 70,
    # Assault
    "Annihilator": 100, "Atlas": 100, "Awesome": 80, "Banshee": 95, "Battlemaster": 85,
    "Berserker": 100, "Charger": 80, "Corsair": 95, "Cyclops": 90, "Dire Wolf": 100,
    "Executioner": 95, "Gargoyle": 80, "Hatamoto-Chi": 80, "Highlander": 90,
    "King Crab": 100, "Longbow": 85, "Mauler": 90, "Nightstar": 95, "Stalker": 85,
    "Victor": 80, "Warhawk": 85, "Zeus": 80,
}


def weight_class(tons) -> str:
    """Tonnage -> Light / Medium / Heavy / Assault (empty if unknown)."""
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
    """(tonnage, weight_class) for a variant code or asset name; (None, '') if
    the chassis isn't in the roster."""
    chassis = VARIANT_TO_CHASSIS.get(variant_code(name))
    tons = CHASSIS_TONNAGE.get(chassis) if chassis else None
    return (tons, weight_class(tons))


def asset_name(variant: str) -> str:
    """Variant code -> MechDataAsset PrimaryAssetName."""
    return variant if variant.endswith("_MDA") else variant + "_MDA"


def variant_code(name: str) -> str:
    """Strip a trailing _MDA (and accept either form)."""
    return name[:-4] if name.endswith("_MDA") else name


def display(name: str) -> str:
    """Friendly label for a variant code or asset name, e.g.:
        'AS7-BH_MDA' -> 'Atlas “Boar's Head” (AS7-BH)'
        'JVN-10F'    -> 'Javelin (JVN-10F)'
        unknown code -> the code itself (so nothing ever breaks)."""
    code = variant_code(name)
    chassis = VARIANT_TO_CHASSIS.get(code)
    if not chassis:
        return code
    hero = HERO_NAMES.get(code)
    if hero:
        return f'{chassis} "{hero}" ({code})'
    return f"{chassis} ({code})"


# (label, variant) pairs for dropdowns. Heroes get their nickname inline so they
# are searchable by name too, e.g. ("Atlas  AS7-BH  “Boar's Head”", "AS7-BH").
def _label(name, code):
    hero = HERO_NAMES.get(code)
    return f"{name}  {code}" + (f'  "{hero}"' if hero else "")

LABELED = [(_label(n, v), v) for n in sorted(CHASSIS) for v in sorted(CHASSIS[n])]
