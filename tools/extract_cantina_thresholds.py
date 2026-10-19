"""Read factual tier thresholds from extracted stock UE4 career packages.

Usage: python tools/extract_cantina_thresholds.py <folder of .uasset/.uexp pairs>
Extract only MW5Mercs/Content/Careers/*CareerPath.{uasset,uexp} from an
unmodified installed game pak. Does not modify game assets or save files.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys


def thresholds(asset):
    data = asset.read_bytes()
    if data[:4] != bytes.fromhex("c1832a9e") or struct.unpack_from("<i", data, 4)[0] != -7:
        raise ValueError("Unsupported cooked package header")
    # Observed package header version -7 with no custom versions and FolderName None.
    if data[28:37] != b"\x05\x00\x00\x00None\x00":
        raise ValueError("Unsupported package header layout")
    count, position = struct.unpack_from("<ii", data, 41)
    names = []
    for _ in range(count):
        size = struct.unpack_from("<i", data, position)[0]
        if not 0 < size < 4096:
            raise ValueError("Unsupported name table entry")
        raw = data[position+4:position+4+size]
        if not raw.endswith(b"\0"):
            raise ValueError("Truncated name table")
        names.append(raw[:-1].decode("ascii"))
        position += 4 + size + 4  # FString + name hashes
    export = asset.with_suffix(".uexp").read_bytes()
    array_tag = struct.pack("<IIII", names.index("CareerPathLevels"), 0,
                            names.index("ArrayProperty"), 0)
    array_at = export.index(array_tag)
    array_count = struct.unpack_from("<i", export, array_at + 33)[0]
    tag = struct.pack("<IIII", names.index("CareerPoints"), 0,
                      names.index("IntProperty"), 0)
    points = []
    rewards = []
    start = array_at
    while True:
        at = export.find(tag, start)
        if at < 0:
            break
        if struct.unpack_from("<q", export, at + 16)[0] != 4 or export[at+24] != 0:
            raise ValueError("Unsupported CareerPoints property")
        points.append(struct.unpack_from("<i", export, at + 25)[0])
        end = export.find(tag, at + len(tag))
        end = end if end >= 0 else len(export)
        reward_tag = struct.pack("<IIII", names.index("MechTraitReward"), 0,
                                 names.index("StructProperty"), 0)
        reward_at = export.index(reward_tag, at, end)
        reward_size = struct.unpack_from("<q", export, reward_at + 16)[0]
        if names[struct.unpack_from("<i", export, reward_at + 24)[0]] != "MechTraitDataAssetId":
            raise ValueError("Unsupported career reward struct")
        reward = export[reward_at + 49:reward_at + 49 + reward_size]
        name_tag = struct.pack("<IIII", names.index("PrimaryAssetName"), 0,
                               names.index("NameProperty"), 0)
        name_at = reward.index(name_tag)
        if struct.unpack_from("<q", reward, name_at + 16)[0] != 8:
            raise ValueError("Unsupported reward asset name")
        name, number = struct.unpack_from("<ii", reward, name_at + 25)
        if number or not names[name].endswith(("_Trait1", "_Trait2")):
            raise ValueError("Unexpected career reward asset")
        rewards.append(names[name])
        start = at + len(tag)
    if len(points) != array_count or array_count != 10 or points != sorted(points):
        raise ValueError("Unexpected tier count/order")
    return {"points": points, "rewards": rewards,
            "uasset_sha256": hashlib.sha256(data).hexdigest(),
            "uexp_sha256": hashlib.sha256(export).hexdigest()}


if __name__ == "__main__":
    print(json.dumps({p.stem: thresholds(p) for p in Path(sys.argv[1]).glob("*CareerPath.uasset")}, indent=2))
