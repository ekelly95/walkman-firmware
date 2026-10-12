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


def make_stage3() -> bytes:
    base = 0x03050000
    body = b"\x00" * 16 + b"<firmwareversion>1.01</firmwareversion>"
    header = struct.pack("<II", base, 1)
    section = struct.pack("<8I", base + 40, 0x0306C000, len(body), 0, 0, 0, 0, 0)
    return header + section + body


def make_image() -> bytes:
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

    table(0x50, [b"", b"", b"", stage3])
    table(0xF4, [make_strtbl()])
    table(0x148, [imageres])
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
