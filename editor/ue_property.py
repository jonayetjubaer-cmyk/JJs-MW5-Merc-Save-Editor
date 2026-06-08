"""Generic reader/writer for Unreal Engine "tagged property" archives.

This is the property-list format MW5 Mercs uses for its .sav files (and that
many other UE4/UE5 games use inside GVAS SaveGame archives). A property list is
a sequence of entries shaped like:

    [name: FString][type: FString][payload_size: int64][padding/extra: varies]
    [... type-specific payload, exactly payload_size bytes ...]

terminated by an entry whose name is the literal string "None".

Design goal: LOSSLESS ROUND-TRIP. Every property we don't have a specific
decoder for is kept as a raw byte blob and written back byte-for-byte. Types we
DO decode (struct/array/primitives) are turned into Python structures that can
be edited and re-serialized, with sizes recomputed on write. This lets us parse
just enough to do useful edits (e.g. add array elements) without having to
model 100% of MW5's custom struct types up front.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def read(self, n: int) -> bytes:
        chunk = self.data[self.pos:self.pos + n]
        if len(chunk) != n:
            raise EOFError(f"wanted {n} bytes at {self.pos:#x}, got {len(chunk)}")
        self.pos += n
        return chunk

    def i32(self) -> int:
        return struct.unpack("<i", self.read(4))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.read(8))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.read(8))[0]

    def f32(self) -> float:
        return struct.unpack("<f", self.read(4))[0]

    def byte(self) -> int:
        return self.read(1)[0]

    def fstring(self) -> str:
        """FString: int32 length. Positive => ASCII (NUL-terminated, len includes NUL).
        Negative => UTF-16LE (NUL-terminated, |len| chars including NUL)."""
        n = self.i32()
        if n == 0:
            return ""
        if n > 0:
            raw = self.read(n)
            return raw[:-1].decode("ascii", errors="replace")
        else:
            raw = self.read(-n * 2)
            return raw[:-2].decode("utf-16-le", errors="replace")


class Writer:
    def __init__(self):
        self.buf = bytearray()

    def write(self, data: bytes):
        self.buf += data

    def i32(self, v: int):
        self.buf += struct.pack("<i", v)

    def u32(self, v: int):
        self.buf += struct.pack("<I", v)

    def i64(self, v: int):
        self.buf += struct.pack("<q", v)

    def u64(self, v: int):
        self.buf += struct.pack("<Q", v)

    def f32(self, v: float):
        self.buf += struct.pack("<f", v)

    def byte(self, v: int):
        self.buf += bytes((v,))

    def fstring(self, s: str):
        if s == "":
            self.i32(0)
            return
        try:
            raw = s.encode("ascii") + b"\x00"
            self.i32(len(raw))
            self.write(raw)
        except UnicodeEncodeError:
            raw = s.encode("utf-16-le") + b"\x00\x00"
            self.i32(-(len(raw) // 2))
            self.write(raw)

    def bytes(self) -> bytes:
        return bytes(self.buf)


# Property type tag strings that carry a "value type" sub-tag before their size
# (ArrayProperty/SetProperty: element type; StructProperty: struct name + GUID).
NAME_TERMINATOR = "None"

# Struct types serialized as raw fixed-layout values (not nested tagged-property
# lists). Their payloads carry the same "+1 uncounted leading byte" quirk as
# array payloads (observed concretely for "Guid": declared size=16, actual
# region=17 bytes = [1 leading byte][16-byte value]).
KNOWN_RAW_STRUCTS = {
    "Vector", "Vector2D", "Rotator", "Quat", "Guid", "DateTime",
    "Timespan", "Color", "LinearColor", "Transform", "Box", "Box2D",
}


@dataclass
class Property:
    """One entry in a tagged-property list.

    `decoded` holds a structured representation when we understand the type
    (currently: Struct -> PropertyList, Array -> ArrayValue). Everything else
    is kept verbatim in `raw_payload` and written back unchanged.
    """
    name: str
    type: str
    raw_header: bytes        # bytes between the type FString and the payload (size, sub-tags, etc)
    raw_payload: bytes       # exact payload bytes (used when decoded is None)
    decoded: Any = None      # PropertyList | ArrayValue | None
    # ArrayProperty quirk: every array payload is preceded by a single byte
    # that ISN'T counted in the FPropertyTag `size` field (observed as 0x00
    # in all cases so far, but we read+store the real byte for losslessness).
    array_leading_byte: bytes | None = None
    # Same quirk for StructProperty payloads of "raw" struct types (KNOWN_RAW_STRUCTS):
    # the actual region is `size + 1` bytes = [1 leading byte][size-byte value].
    struct_leading_byte: bytes | None = None


@dataclass
class PropertyList:
    """An ordered list of properties, terminated by a 'None' name."""
    properties: list = field(default_factory=list)

    def get(self, name):
        for p in self.properties:
            if p.name == name:
                return p
        return None

    def __iter__(self):
        return iter(self.properties)


@dataclass
class ArrayValue:
    element_type: str
    count: int
    # For StructProperty arrays: list[PropertyList] (one per element, each a struct's tagged props)
    # For everything else: list[bytes] raw per-element blobs
    elements: list = field(default_factory=list)
    inner_tag_name: str | None = None
    inner_struct_name: str | None = None
    inner_struct_guid: bytes | None = None
    # StructProperty-array quirk: one more uncounted byte sits between the
    # inner tag's struct GUID and the first element (same "+1" pattern as the
    # array payload itself; observed as 0x00).
    elements_leading_byte: bytes | None = None


def read_property_list(r: Reader) -> PropertyList:
    """Reads properties until the 'None' terminator. Used for top-level save
    data and for the contents of StructProperty entries whose struct type uses
    tagged-property serialization (most gameplay structs do)."""
    props = []
    while True:
        name = r.fstring()
        if name == NAME_TERMINATOR:
            break
        ptype = r.fstring()
        prop = _read_property_body(r, name, ptype)
        props.append(prop)
    return PropertyList(props)


def _read_property_body(r: Reader, name: str, ptype: str) -> Property:
    header_start = r.pos
    size = r.i64()

    if ptype == "StructProperty":
        struct_name = r.fstring()
        guid = r.read(16)
        header_end = r.pos
        raw_header = r.data[header_start:header_end]
        payload_start = r.pos

        # CONFIRMED universal quirk: every StructProperty payload is `size + 1`
        # bytes = [1 uncounted leading byte][size-byte content], where the
        # content is either a nested tagged-property list (most gameplay
        # structs) or a raw fixed-layout value (Guid, Vector, etc.) -- same
        # "+1" pattern as array payloads, just with the content shifted by 1.
        region = r.read(size + 1)
        leading_byte, content = region[:1], region[1:]
        decoded = None
        if struct_name not in KNOWN_RAW_STRUCTS:
            decoded = _try_decode_struct_payload(content, struct_name)
        return Property(name, ptype, raw_header, content, decoded,
                        struct_leading_byte=leading_byte)

    if ptype in ("MapProperty", "SetProperty"):
        # MapProperty/SetProperty tags carry sub-type FStrings after `size`
        # (key_type+value_type, or just element_type for sets), then content
        # of `size + 1` bytes -- same universal "+1 uncounted leading byte"
        # quirk. Content = [1 leading byte][num-to-remove:int32][num-entries:
        # int32][entries...]. We don't model entry encoding (it depends on the
        # key/value property types) -- keep the whole thing as an opaque
        # verbatim blob for lossless round-trip.
        sub_types = []
        sub_types.append(r.fstring())
        if ptype == "MapProperty":
            sub_types.append(r.fstring())
        header_end = r.pos
        raw_header = r.data[header_start:header_end]
        blob = r.read(size + 1)
        return Property(name, ptype, raw_header, blob, None)

    if ptype == "ArrayProperty":
        element_type = r.fstring()
        header_end = r.pos
        raw_header = r.data[header_start:header_end]

        # Quirk observed in real saves (confirmed across ByteProperty AND
        # StructProperty arrays): every ArrayProperty payload is preceded by a
        # single byte that ISN'T counted in the FPropertyTag `size` field, so
        # the actual serialized region is `size + 1` bytes. We read it as its
        # own field (always 0x00 so far) so the writer can reproduce it.
        leading_byte = r.read(1)
        payload = r.read(size)

        if element_type == "ByteProperty":
            # Commonly holds a nested archive blob we parse separately --
            # keep verbatim rather than trying to structure-decode it.
            return Property(name, ptype, raw_header, payload, None,
                            array_leading_byte=leading_byte)

        decoded = _try_decode_array_payload(payload, element_type)
        return Property(name, ptype, raw_header, payload, decoded,
                        array_leading_byte=leading_byte)

    if ptype == "BoolProperty":
        # BoolProperty stores its value INLINE in the tag (no separate
        # payload): [size=0][bool_value: 1 byte][trailing byte: 1 byte].
        bool_value = r.read(1)
        trailing = r.read(1)
        raw_header = r.data[header_start:r.pos]
        return Property(name, ptype, raw_header, b"", None)

    if ptype in ("EnumProperty", "ByteProperty"):
        # Scalar enum/byte properties carry an extra "enum name" FString
        # sub-tag (the enum type, e.g. "EDropshipTransitState") before the
        # usual trailing byte + size-byte payload (the payload is itself an
        # FString naming the specific enum value, e.g. "EDropshipTransitState
        # ::InTransit").
        enum_name = r.fstring()
        trailing = r.read(1)
        raw_header = r.data[header_start:r.pos]
        payload = r.read(size)
        return Property(name, ptype, raw_header, payload, None)

    # Scalar / unknown types: there's a single trailing zero byte after the
    # size for most scalar property tags (the "has value" / terminator byte in
    # newer UE versions). We've observed this pattern (size, then 0x00, then
    # payload) in the dumps; keep it in raw_header and treat the rest as opaque
    # payload so round-trip stays exact regardless of whether our guess about
    # this byte's meaning is right.
    trailing = r.read(1)
    raw_header = r.data[header_start:r.pos]
    payload = r.read(size)
    return Property(name, ptype, raw_header, payload, None)


def _try_decode_struct_payload(payload: bytes, struct_name: str):
    """Most gameplay structs (anything not a core-engine math/date type) are
    serialized as a nested tagged-property list. Core types like Vector,
    Rotator, Guid, DateTime, etc. are raw fixed-layout structs we don't decode.
    We detect "is this a property list" by trying to parse it and checking that
    we consumed it cleanly down to the 'None' terminator."""
    if struct_name in KNOWN_RAW_STRUCTS:
        return None
    try:
        sub = Reader(payload)
        plist = read_property_list(sub)
        if sub.remaining() == 0:
            return plist
    except Exception:
        pass
    return None


def _try_decode_array_payload(payload: bytes, element_type: str):
    """Array payload = [int32 count][elements...]. For StructProperty arrays,
    UE additionally inlines the element's name/type/size/struct-name/guid
    header ONCE before the elements (the "inner tag"), then each element is a
    raw tagged-property list with no further per-element header. For primitive
    element types (IntProperty, StrProperty, etc.) elements are just packed
    values with no per-element header."""
    try:
        r = Reader(payload)
        count = r.i32()

        if element_type == "StructProperty":
            # Inner tag: name, type, size, struct_name, guid
            inner_name = r.fstring()
            inner_type = r.fstring()
            inner_size = r.i64()
            struct_name = r.fstring()
            guid = r.read(16)
            elements_leading_byte = r.read(1)
            elements = []
            for _ in range(count):
                start = r.pos
                plist = read_property_list(r)
                # sanity: re-parsing shouldn't run past the declared payload
                _ = start
                elements.append(plist)
            if r.remaining() != 0:
                return None
            return ArrayValue(element_type, count, elements, inner_tag_name=inner_name,
                              inner_struct_name=struct_name, inner_struct_guid=guid,
                              elements_leading_byte=elements_leading_byte)

        # Primitive arrays: keep as raw per-element blobs (size = remaining/count)
        remaining = r.remaining()
        if count == 0:
            return ArrayValue(element_type, count, [])
        if remaining % count != 0:
            return None
        elem_size = remaining // count
        elements = [r.read(elem_size) for _ in range(count)]
        return ArrayValue(element_type, count, elements)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def write_property_list(w: Writer, plist: PropertyList):
    for prop in plist.properties:
        w.fstring(prop.name)
        w.fstring(prop.type)
        _write_property_body(w, prop)
    w.fstring(NAME_TERMINATOR)


def _write_property_body(w: Writer, prop: Property):
    if prop.type == "StructProperty":
        # raw_header = [size:int64][struct_name:FString][guid:16]; we must
        # rewrite the size, struct_name/guid are unchanged so re-emit them by
        # re-reading from raw_header.
        rr = Reader(prop.raw_header)
        _old_size = rr.i64()
        struct_name = rr.fstring()
        guid = rr.read(16)

        content = _serialize_struct_payload(prop)
        leading = prop.struct_leading_byte if prop.struct_leading_byte is not None else b"\x00"
        w.i64(len(content))
        w.fstring(struct_name)
        w.write(guid)
        w.write(leading)
        w.write(content)
        return

    if prop.type in ("MapProperty", "SetProperty"):
        rr = Reader(prop.raw_header)
        _old_size = rr.i64()
        sub_types = [rr.fstring()]
        if prop.type == "MapProperty":
            sub_types.append(rr.fstring())
        blob = prop.raw_payload
        w.i64(len(blob) - 1)
        for st in sub_types:
            w.fstring(st)
        w.write(blob)
        return

    if prop.type == "ArrayProperty":
        rr = Reader(prop.raw_header)
        _old_size = rr.i64()
        element_type = rr.fstring()
        leading_byte = prop.array_leading_byte if prop.array_leading_byte is not None else b"\x00"
        if element_type == "ByteProperty":
            blob = prop.raw_payload
            w.i64(len(blob))
            w.fstring(element_type)
            w.write(leading_byte)
            w.write(blob)
            return
        payload = _serialize_array_payload(prop)
        w.i64(len(payload))
        w.fstring(element_type)
        w.write(leading_byte)
        w.write(payload)
        return

    if prop.type == "BoolProperty":
        # raw_header = [size=0][bool_value][trailing byte]; payload is empty.
        rr = Reader(prop.raw_header)
        _old_size = rr.i64()
        bool_value = rr.read(1)
        trailing = rr.read(1)
        w.i64(0)
        w.write(bool_value)
        w.write(trailing)
        return

    if prop.type in ("EnumProperty", "ByteProperty"):
        # raw_header = [size:int64][enum_name:FString][trailing byte]
        rr = Reader(prop.raw_header)
        _old_size = rr.i64()
        enum_name = rr.fstring()
        trailing = rr.read(1)
        w.i64(len(prop.raw_payload))
        w.fstring(enum_name)
        w.write(trailing)
        w.write(prop.raw_payload)
        return

    # Scalar/unknown: raw_header = [size:int64][trailing byte], payload verbatim
    rr = Reader(prop.raw_header)
    _old_size = rr.i64()
    trailing = rr.read(1)
    w.i64(len(prop.raw_payload))
    w.write(trailing)
    w.write(prop.raw_payload)


def _serialize_struct_payload(prop: Property) -> bytes:
    if prop.decoded is None:
        return prop.raw_payload
    w = Writer()
    write_property_list(w, prop.decoded)
    return w.bytes()


def _serialize_array_payload(prop: Property) -> bytes:
    av: ArrayValue = prop.decoded
    if av is None:
        return prop.raw_payload
    w = Writer()
    w.i32(av.count)
    if av.element_type == "StructProperty":
        # Re-emit the inner tag. We don't currently track a separate "inner
        # property name" so reuse the array's own name/type framing: in
        # practice MW5 inner tags mirror the outer array's name with the
        # element struct type — but to stay lossless we cache the original
        # inner header bytes the first time we decode (see ArrayValue).
        w.fstring(av.inner_tag_name)
        w.fstring("StructProperty")

        # The declared "inner_size" is the total byte length of all serialized
        # elements (NOT just the first element's payload, despite resembling a
        # property tag's size field).
        elements_writer = Writer()
        for plist in av.elements:
            write_property_list(elements_writer, plist)
        elements_bytes = elements_writer.bytes()

        w.i64(len(elements_bytes))
        w.fstring(av.inner_struct_name)
        w.write(av.inner_struct_guid)
        leading = av.elements_leading_byte if av.elements_leading_byte is not None else b"\x00"
        w.write(leading)
        w.write(elements_bytes)
        return w.bytes()

    for blob in av.elements:
        w.write(blob)
    return w.bytes()
