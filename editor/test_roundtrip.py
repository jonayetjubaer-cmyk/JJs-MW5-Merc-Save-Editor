"""Round-trip test: read a .sav into the property model, write it back out,
and confirm the bytes match exactly. This is how the byte layout is validated (or disproven) against
assumptions about the UE tagged-property byte layout against real game data.

Usage:
    python test_roundtrip.py <path_to_save.sav>
"""
import sys
from ue_property import Reader, Writer, read_property_list, write_property_list


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "rb") as f:
        data = f.read()

    print(f"loaded {len(data)} bytes from {path}")

    r = Reader(data)
    plist = read_property_list(r)
    consumed = r.pos
    print(f"parsed top-level property list: {len(plist.properties)} properties, "
          f"consumed {consumed} of {len(data)} bytes "
          f"({len(data) - consumed} bytes remain after terminator)")

    w = Writer()
    write_property_list(w, plist)
    out = w.bytes()

    print(f"re-serialized to {len(out)} bytes")

    # Compare only the region that was parsed (trailing bytes after the top-level
    # property list, if any, are not yet modeled).
    original_region = data[:consumed]
    if out == original_region:
        print("ROUND TRIP OK: re-serialized bytes match original exactly.")
    else:
        n = min(len(out), len(original_region))
        first_diff = next((i for i in range(n) if out[i] != original_region[i]), n)
        print(f"ROUND TRIP MISMATCH at byte offset {first_diff:#x}")
        print(f"  original len={len(original_region)} new len={len(out)}")
        lo = max(0, first_diff - 16)
        print("  original:", original_region[lo:first_diff + 16].hex(" "))
        print("  rewritten:", out[lo:first_diff + 16].hex(" "))


if __name__ == "__main__":
    main()
