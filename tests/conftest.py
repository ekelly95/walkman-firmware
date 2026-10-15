"""Synthetic RKnanoFW images, built to the same rules the player checks, so tests need no Sony files."""

import struct
from pathlib import Path

import pytest

from nwe39x.crc import rk_crc
from nwe39x.rknanofw import HEADER_SIZE, MAGIC, expected_file_size

STOCK = Path(__file__).resolve().parent.parent / "extract" / "cab" / "Data" / "Device" / "RKNANOFW.IMG"
PICTURES = [(4, 3, 10, 20), (2, 2, 0, 0)]  # w, h, x, y


def make_imageres() -> bytes:
    table = bytearray(b"ROCK26IMAGERES  " + struct.pack("<I", len(PICTURES)) + bytes(12))
    pixels = bytearray()
    data_start = 0x20 + 16 * len(PICTURES)
    for i, (w, h, x, y) in enumerate(PICTURES):
        size = w * h * 2
        table += struct.pack("<4H2I", w, h, x, y, size, data_start + len(pixels))
        pixels += bytes((i * 37 + k) & 0xFF for k in range(size))
    return bytes(table + pixels)


def make_strtbl(records: int = 3) -> bytes:
    langs = 13
    header = struct.pack("<H", langs)
    first = 2 + 4 * langs
    header += b"".join(struct.pack("<I", first + li * records * 242) for li in range(langs))
    body = bytearray()
    for li in range(langs):
        for r in range(records):
            head = struct.pack("<H", r) + b"\xff\xff" * 20
            text = f"L{li} R{r}".encode("utf-16-le") + b"\0\0"
            body += head + text + bytes(200 - len(text))
    return header + bytes(body)


def make_font16(count: int = 0x80) -> bytes:
    """font1 layout for the first `count` code points: 32 bytes of rows + 0x80|width."""
    out = bytearray()
    for cp in range(count):
        rows = bytes(32) if cp < 0x21 else b"".join(((0x8000 >> (cp % 8)) | 0x0100).to_bytes(2, "big") for _ in range(16))
        out += rows + bytes([0x80 | (0 if cp < 0x21 else 9)])
    return bytes(out)


def make_font12() -> bytes:
    """font0 layout: 8439-entry table (ASCII mapped to glyphs 0-94), 24-byte glyphs, then one
    width byte per glyph (rightmost ink + 1, like Sony's)."""
    table = [0xFFFF] * 8439
    for i in range(95):
        table[i] = i
    glyphs, widths = bytearray(), bytearray()
    for g in range(95):
        glyphs += b"".join(((0x8000 >> (g % 12)) if g >= 1 else 0).to_bytes(2, "big") for _ in range(12))
        widths.append((g % 12) + 1 if g >= 1 else 5)
    return struct.pack("<8439H", *table) + bytes(glyphs) + bytes(widths)


def make_stage3() -> bytes:
    base = 0x03050000
    body = b"\x00" * 16 + b"<firmwareversion>1.01</firmwareversion>"
    header = struct.pack("<II", base, 1)
    section = struct.pack("<8I", base + 40, 0x0306C000, len(body), 0, 0, 0, 0, 0)
    return header + section + body


def make_image(stage0: bytes = b"", free: int = 0) -> bytes:
    """`stage0` gives boot stage 0 bytes; `free` adds zeros after the last blob, like the free space
    in Sony's image where app sections go. The defaults leave both empty."""
    stage3, imageres = make_stage3(), make_imageres()
    header = bytearray(HEADER_SIZE)
    struct.pack_into("<HBB", header, 0, 0x2016, 0x14, 0x10)
    header[0x10:0x18] = b"Rockchip"
    header[0x30:0x3e] = b"RKnano SDK 1.0"
    payload = bytearray()
    offset = HEADER_SIZE

    def table(count_at, blobs):
        nonlocal offset
        struct.pack_into("<I", header, count_at, len(blobs))
        for k, blob in enumerate(blobs):
            struct.pack_into("<II", header, count_at + 4 + 8 * k, offset if blob else HEADER_SIZE, len(blob))
            payload.extend(blob)
            offset += len(blob)

    table(0x50, [stage0, b"", b"", stage3])
    table(0x74, [make_font12(), make_font16()])
    table(0xF4, [make_strtbl()])
    table(0x148, [imageres])
    payload.extend(bytes(free))
    size = HEADER_SIZE + len(payload)
    struct.pack_into("<I", header, 0x1F4, size)
    header[0x1F8:0x200] = MAGIC
    body = bytes(header) + bytes(payload) + bytes(header)
    total = expected_file_size(size)
    body += bytes(total - 4 - len(body))
    return body + struct.pack("<I", rk_crc(body))


@pytest.fixture
def image_bytes() -> bytes:
    return make_image()


@pytest.fixture
def stock_bytes() -> bytes:
    if not STOCK.exists():
        pytest.skip("Sony's RKNANOFW.IMG not unpacked locally")
    return STOCK.read_bytes()
