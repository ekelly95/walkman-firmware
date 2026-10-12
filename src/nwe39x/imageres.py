"""ROCK26IMAGERES, the firmware's table of UI pictures.

Layout (NW-E390 1.01): 16-byte magic "ROCK26IMAGERES  ", u32 count, 12 bytes of zeros, then `count`
16-byte entries {u16 width, u16 height, u16 x, u16 y, u32 size, u32 offset}. `offset` is relative
to the blob, `size` = width * height * 2, and pixels are RGB565 big-endian. x/y are the picture's
position on the 128x160 screen.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .rknanofw import Firmware, FirmwareError

MAGIC = b"ROCK26IMAGERES"
NAME = re.compile(r"^(\d{3})(?:_.*)?\.png$", re.IGNORECASE)


@dataclass
class Picture:
    index: int
    width: int
    height: int
    x: int
    y: int
    size: int
    offset: int  # absolute, in the firmware file

    @property
    def filename(self) -> str:
        return f"{self.index:03d}_{self.width}x{self.height}_at{self.x},{self.y}.png"


def pictures(fw: Firmware) -> list[Picture]:
    blob = fw.blob("imageres")
    data = fw.read(blob)
    if not data.startswith(MAGIC):
        raise FirmwareError("imageres0 is not a ROCK26IMAGERES table")
    count = struct.unpack_from("<I", data, 0x10)[0]
    out = []
    for i in range(count):
        w, h, x, y, size, off = struct.unpack_from("<4H2I", data, 0x20 + 16 * i)
        if size != w * h * 2 or off + size > blob.size:
            raise FirmwareError(f"picture {i} has an unexpected entry")
        out.append(Picture(i, w, h, x, y, size, blob.offset + off))
    return out


def decode(fw: Firmware, pic: Picture) -> Image.Image:
    raw = bytes(fw.buf[pic.offset:pic.offset + pic.size])
    out = bytearray()
    for (v,) in struct.iter_unpack(">H", raw):
        r, g, b = v >> 11, (v >> 5) & 0x3F, v & 0x1F
        out += bytes((r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2))
    return Image.frombytes("RGB", (pic.width, pic.height), bytes(out))


def encode(img: Image.Image) -> bytes:
    """RGB565 big-endian. Lossless for pictures exported by `decode` (the low bits are dropped)."""
    rgb = img.convert("RGB").tobytes()
    out = bytearray()
    for r, g, b in zip(rgb[0::3], rgb[1::3], rgb[2::3]):
        out += struct.pack(">H", (r >> 3) << 11 | (g >> 2) << 5 | b >> 3)
    return bytes(out)


def replace(fw: Firmware, index: int, img: Image.Image):
    pic = pictures(fw)[index]
    if img.size != (pic.width, pic.height):
        raise FirmwareError(f"picture {index} is {pic.width}x{pic.height}, not {img.size[0]}x{img.size[1]}")
    fw.write(pic.offset, encode(img))


def export(fw: Firmware, outdir: Path, sheet: Path | None = None) -> int:
    outdir.mkdir(parents=True, exist_ok=True)
    pics = pictures(fw)
    decoded = [(p, decode(fw, p)) for p in pics]
    for p, img in decoded:
        img.save(outdir / p.filename)
    if sheet:
        contact_sheet([img for _, img in decoded]).save(sheet)
    return len(pics)


def import_dir(fw: Firmware, srcdir: Path) -> list[int]:
    """Replace every picture whose PNG in `srcdir` (named NNN_*.png or NNN.png) differs."""
    pics = pictures(fw)
    changed = []
    for path in sorted(srcdir.iterdir()):
        m = NAME.match(path.name)
        if not m:
            continue
        index = int(m.group(1))
        if index >= len(pics):
            raise FirmwareError(f"{path.name}: there are only {len(pics)} pictures")
        new = encode(Image.open(path))
        p = pics[index]
        if len(new) != p.size:
            raise FirmwareError(f"{path.name}: picture {index} is {p.width}x{p.height}")
        if new != bytes(fw.buf[p.offset:p.offset + p.size]):
            fw.write(p.offset, new)
            changed.append(index)
    return changed


def contact_sheet(images: list[Image.Image], width: int = 1200, gap: int = 6) -> Image.Image:
    rows, row, row_w, row_h = [], [], gap, 0
    for img in images:
        if row and row_w + img.width + gap > width:
            rows.append((row, row_h))
            row, row_w, row_h = [], gap, 0
        row.append(img)
        row_w += img.width + gap
        row_h = max(row_h, img.height)
    rows.append((row, row_h))
    sheet = Image.new("RGB", (width, gap + sum(h + gap for _, h in rows)), (48, 48, 48))
    top = gap
    for row, row_h in rows:
        left = gap
        for img in row:
            sheet.paste(img, (left, top))
            left += img.width + gap
        top += row_h + gap
    return sheet
