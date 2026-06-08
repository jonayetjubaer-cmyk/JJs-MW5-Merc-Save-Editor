#!/usr/bin/env python3
"""Binary-diff two MW5 Mercs save files to locate changed byte ranges.

Usage:
    python diff_saves.py <old_save> <new_save>

Auto-detects gzip/zlib compression (common for Unreal Engine SaveGame files)
and diffs the decompressed bytes when possible, falling back to raw bytes.
"""
import sys
import gzip
import zlib


def load_bytes(path):
    with open(path, "rb") as f:
        raw = f.read()

    # gzip magic
    if raw[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(raw), "gzip"
        except OSError:
            pass

    # zlib header (common: 0x78 0x9c / 0x78 0x01 / 0x78 0xda)
    if raw[:1] == b"\x78":
        try:
            return zlib.decompress(raw), "zlib"
        except zlib.error:
            pass

    return raw, "raw"


def hex_context(data, offset, width=16):
    start = max(0, offset - width)
    end = min(len(data), offset + width)
    chunk = data[start:end]
    hex_str = " ".join(f"{b:02x}" for b in chunk)
    ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    return f"  offset {start:#08x}: {hex_str}\n  ascii:  {ascii_str}"


def diff(a, b):
    ranges = []
    i = 0
    min_len = min(len(a), len(b))
    while i < min_len:
        if a[i] != b[i]:
            start = i
            while i < min_len and a[i] != b[i]:
                i += 1
            ranges.append((start, i))
        else:
            i += 1
    if len(a) != len(b):
        ranges.append((min_len, max(len(a), len(b))))
    return ranges


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    old_path, new_path = sys.argv[1], sys.argv[2]
    old_data, old_kind = load_bytes(old_path)
    new_data, new_kind = load_bytes(new_path)

    print(f"old: {old_path} ({len(old_data)} bytes, decoded as {old_kind})")
    print(f"new: {new_path} ({len(new_data)} bytes, decoded as {new_kind})")

    if old_kind != new_kind:
        print("WARNING: files decoded differently; diff may be misleading")

    ranges = diff(old_data, new_data)
    if not ranges:
        print("\nNo differences found in overlapping region.")
        return

    print(f"\nFound {len(ranges)} changed range(s):\n")
    for start, end in ranges:
        print(f"--- changed bytes [{start:#x}, {end:#x}) ---")
        print("old:")
        print(hex_context(old_data, start))
        print("new:")
        print(hex_context(new_data, start))
        print()


if __name__ == "__main__":
    main()
