"""The firmware's bitmap fonts.

font1, "font16": 16x16 pixels, one 33-byte record per Unicode code point (U+0000-U+FFFF, indexed
directly): 16 rows of 2 bytes, MSB = leftmost pixel, then one byte = 0x80 | advance width.
It covers every UI language (Latin, Cyrillic, Greek, kana, all 11,172 Hangul syllables, 20,902
CJK ideographs).

font0, "font12": 12x12 pixels. A table of 8,439 u16 values maps code points U+0020-U+20F6 to
glyph numbers (0xFFFF = no glyph); then 424 glyph records of 24 bytes (12 rows of 2 bytes, left 12
bits used, rows 0 and 11 blank in Sony's glyphs); then one advance-width byte per glyph (Sony's
are rightmost ink + 1; space is 5). The player clips each glyph to its advance, so a replaced
glyph needs its width written too. That covers ASCII, Latin, Cyrillic and Greek.

After the width table comes font12's CJK part: two banks of 31,682 glyph records (24 bytes, same
row format), then a u16 index of all 65,536 code points (0 = no glyph, else record number + 1):
symbols, kana, CJK U+4E00-U+9FA5 and compatibility ideographs, Hangul syllables, full-width forms.
Stage 3 reads it at fixed offsets in section 0 (index `0x3053fac`, bank 1 `0x3053f84`, bank 2
`0x3053f5c`); `0x30540ac` looks a character up in the Latin table first and the CJK index second,
and uses bank 2 when the UI language is Chinese (settings `+0x4c` = 11 or 12), bank 1 otherwise
(the banks differ in 7,262 Han glyph shapes). CJK glyphs have no width table: they advance 12,
halfwidth katakana (U+FF61-U+FF9F) 6. `font12zh` is font12 with bank 2.

Sheets are PNGs with one glyph per cell; the font and code points are stored in the PNG's text
metadata so an edited sheet imports back to the same characters. An optional "advance" in the
metadata gives every glyph of the sheet that advance width instead of one computed from its ink
(`fonts from-ttf --advance N`, for a monospace rhythm); "widths" ({code point: width}) does the
same per glyph (`fonts from-bdf` keeps the BDF's own advance widths that way).
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from .rknanofw import Firmware, FirmwareError

RANGES = {
    "ascii": range(0x20, 0x7F),
    "latin1": range(0xA0, 0x100),
    "latin-ext": range(0x100, 0x180),
    "cyrillic": range(0x400, 0x460),
    "greek": range(0x370, 0x400),
    "cjk-symbols": range(0x3000, 0x3040),
    "kana": range(0x3040, 0x3100),
    "cjk": range(0x4E00, 0x9FA6),
    "hangul": range(0xAC00, 0xD7A4),
    "fullwidth": range(0xFF00, 0xFFF0),
}
META_KEY = "nwe39x-font"
INK, PAPER, GRID = 255, 0, 64
FONT16_GLYPHS = 0x10000  # one record per BMP code point; the blob has 7,174 more bytes after them
FONT12_TABLE = 8439  # u16 entries, U+0020..U+20F6
FONT12_RECORD = 24
# font12's CJK part, as offsets in the blob (the constants in section 0's readers)
CJK_BANKS = (0x6B56, 0xC0586)
CJK_BANK_GLYPHS = 31682
CJK_INDEX = 0x179FB6
CJK_LATIN_GLYPHS = 424  # the layout these offsets assume


@dataclass
class Font:
    fw: Firmware
    name: str          # "font16", "font12" or "font12zh"
    size: int          # glyph cell, square
    blob_offset: int
    blob_size: int
    table: tuple[int, ...] = ()
    cjk: tuple[int, ...] = ()  # font12: the CJK index (record number + 1, 0 = none)
    bank: int = 0              # font12: 0 = bank 1, 1 = bank 2 (Chinese UI)

    @classmethod
    def font16(cls, fw: Firmware) -> Font:
        b = fw.blob("font", 1)
        return cls(fw, "font16", 16, b.offset, b.size)

    @classmethod
    def font12(cls, fw: Firmware, bank: int = 0) -> Font:
        b = fw.blob("font", 0)
        table = struct.unpack_from(f"<{FONT12_TABLE}H", fw.buf, b.offset)
        f = cls(fw, "font12zh" if bank else "font12", 12, b.offset, b.size, table, bank=bank)
        if (f.glyph_count == CJK_LATIN_GLYPHS and CJK_INDEX + 0x20000 <= b.size
                and f.widths_offset + f.glyph_count == b.offset + CJK_BANKS[0]):
            f.cjk = struct.unpack_from("<65536H", fw.buf, b.offset + CJK_INDEX)
        elif bank:
            raise FirmwareError("this image's font12 has no CJK part where expected")
        return f

    # font12 layout -----------------------------------------------------------------------------
    @property
    def glyph_count(self) -> int:
        return max(v for v in self.table if v != 0xFFFF) + 1

    @property
    def glyphs_offset(self) -> int:
        return self.blob_offset + 2 * len(self.table)

    @property
    def widths_offset(self) -> int:
        return self.glyphs_offset + self.glyph_count * FONT12_RECORD

    def glyph(self, cp: int) -> int | None:
        if not 0x20 <= cp < 0x20 + len(self.table) or self.table[cp - 0x20] == 0xFFFF:
            return None
        return self.table[cp - 0x20]

    @classmethod
    def by_name(cls, fw: Firmware, name: str) -> Font:
        if name in ("16", "font16"):
            return cls.font16(fw)
        if name in ("12", "font12"):
            return cls.font12(fw)
        if name in ("12zh", "font12zh"):
            return cls.font12(fw, bank=1)
        raise FirmwareError(f"unknown font {name!r}; use 16, 12 or 12zh (font12's Chinese-UI CJK bank)")

    def is_cjk(self, cp: int) -> bool:
        """font12: drawn from the CJK part (not in the Latin table, but in the CJK index)."""
        return self.glyph(cp) is None and 0 <= cp < len(self.cjk) and self.cjk[cp] != 0

    # Where a glyph lives ---------------------------------------------------------------------
    def offset(self, cp: int) -> int | None:
        if self.name == "font16":
            off = cp * 33
            return self.blob_offset + off if 0 <= cp < FONT16_GLYPHS and off + 33 <= self.blob_size else None
        g = self.glyph(cp)
        if g is None:
            if not self.is_cjk(cp):
                return None
            return self.blob_offset + CJK_BANKS[self.bank] + (self.cjk[cp] - 1) * FONT12_RECORD
        off = 2 * len(self.table) + g * FONT12_RECORD
        return self.blob_offset + off if off + FONT12_RECORD <= self.blob_size else None

    def has(self, cp: int) -> bool:
        return self.offset(cp) is not None

    # Reading and writing ---------------------------------------------------------------------
    def rows(self, cp: int) -> list[int]:
        off = self.offset(cp)
        if off is None:
            raise FirmwareError(f"{self.name} has no glyph for U+{cp:04X}")
        return [int.from_bytes(self.fw.buf[off + 2 * y: off + 2 * y + 2], "big") for y in range(self.size)]

    def width(self, cp: int) -> int:
        """Advance width: font16 stores it after the rows, font12 in its width table; font12's CJK
        glyphs are fixed (12, halfwidth katakana 6)."""
        if self.name == "font16":
            return self.fw.buf[self.offset(cp) + 32] & 0x7F
        if self.is_cjk(cp):
            return self.size // 2 if 0xFF61 <= cp <= 0xFF9F else self.size
        return self.fw.buf[self.widths_offset + self.glyph(cp)]

    @staticmethod
    def _rightmost_ink(rows: list[int], size: int) -> int | None:
        ink = [x for r in rows for x in range(size) if r & (1 << (15 - x))]
        return max(ink) if ink else None

    def image(self, cp: int) -> Image.Image:
        img = Image.new("L", (self.size, self.size), PAPER)
        for y, v in enumerate(self.rows(cp)):
            for x in range(self.size):
                if v & (1 << (15 - x)):
                    img.putpixel((x, y), INK)
        return img

    def set_image(self, cp: int, img: Image.Image, advance: int | None = None) -> bool:
        """Write a glyph from a size x size image (pixels >= 128 are ink). Returns False if unchanged.
        The advance width is `advance` if given, else recomputed from the ink the way Sony's are
        (font16: rightmost + 2, font12: rightmost + 1); a glyph with no ink keeps its width.
        font12's CJK glyphs have fixed widths, so only their rows are written."""
        if img.size != (self.size, self.size):
            raise FirmwareError(f"U+{cp:04X}: glyph must be {self.size}x{self.size}")
        off = self.offset(cp)
        if off is None:
            raise FirmwareError(f"{self.name} has no glyph for U+{cp:04X}")
        px = img.convert("L").load()
        rows = [sum(1 << (15 - x) for x in range(self.size) if px[x, y] >= 128) for y in range(self.size)]
        if self.name != "font16" and self.is_cjk(cp):
            if rows == self.rows(cp):
                return False
            self.fw.write(off, b"".join(r.to_bytes(2, "big") for r in rows))
            return True
        if advance is not None and not 1 <= advance <= self.size:
            raise FirmwareError(f"advance {advance} is outside 1-{self.size} for {self.name}")
        if rows == self.rows(cp) and advance is None:
            return False  # untouched glyphs keep Sony's width, even where it is not ink + 1
        right = self._rightmost_ink(rows, self.size)
        if advance is not None:
            width = advance
        elif right is None:
            width = self.width(cp)
        elif self.name == "font16":
            width = min(right + 2, 16)
        else:
            width = right + 1
        if rows == self.rows(cp) and width == self.width(cp):
            return False
        data = b"".join(r.to_bytes(2, "big") for r in rows)
        if self.name == "font16":
            data += bytes([0x80 | width])
        else:
            self.fw.write(self.widths_offset + self.glyph(cp), bytes([width]))
        self.fw.write(off, data)
        return True


def parse_range(text: str) -> list[int]:
    if text in RANGES:
        return list(RANGES[text])
    a, _, b = text.upper().replace("U+", "").partition("-")
    try:
        return list(range(int(a, 16), int(b or a, 16) + 1))
    except ValueError:
        raise FirmwareError(f"range must be one of {', '.join(RANGES)} or like U+0400-U+045F") from None


def export_sheet(font: Font, cps: list[int], path: Path, cols: int = 16):
    cps = [cp for cp in cps if font.has(cp)]
    if not cps:
        raise FirmwareError(f"{font.name} has none of those characters")
    cell = font.size + 1
    rows = (len(cps) + cols - 1) // cols
    sheet = Image.new("L", (cols * cell + 1, rows * cell + 1), GRID)
    for i, cp in enumerate(cps):
        sheet.paste(font.image(cp), (1 + (i % cols) * cell, 1 + (i // cols) * cell))
    meta = PngInfo()
    meta.add_text(META_KEY, json.dumps({"font": font.name, "cols": cols, "cps": cps}))
    sheet.save(path, pnginfo=meta)
    return len(cps)


def import_sheet(fw: Firmware, path: Path) -> list[int]:
    img = Image.open(path)
    raw = img.text.get(META_KEY) if hasattr(img, "text") else None
    if not raw:
        raise FirmwareError(f"{path.name} has no {META_KEY} metadata; export a sheet with `nwe39x fonts export`")
    meta = json.loads(raw)
    font = Font.by_name(fw, meta["font"])
    cell, cols = font.size + 1, meta["cols"]
    img = img.convert("L")
    changed = []
    for i, cp in enumerate(meta["cps"]):
        x, y = 1 + (i % cols) * cell, 1 + (i // cols) * cell
        advance = meta.get("advance") or meta.get("widths", {}).get(str(cp))
        if font.set_image(cp, img.crop((x, y, x + font.size, y + font.size)), advance):
            changed.append(cp)
    return changed


def baseline(font: Font) -> int:
    """Row just below the original 'H' (its baseline), so replacement glyphs sit on the same line."""
    rows = font.rows(ord("H"))
    return max(y for y, r in enumerate(rows) if r) + 1


def sheet_from_ttf(font: Font, ttf: Path, cps: list[int], path: Path, size: int | None = None,
                   cols: int = 16, base: int | None = None, advance: int | None = None) -> int:
    """Render a TrueType/OpenType font into a glyph sheet (1-bit, no anti-aliasing) on the
    firmware font's baseline (or `base`, a row index: lower it to make room for descenders).
    `advance` fixes every glyph's advance width (monospace) instead of rightmost ink + 1.
    Import it with `build --fonts` / a mod's fonts/ folder."""
    if advance is not None and not 1 <= advance <= font.size:
        raise FirmwareError(f"advance {advance} is outside 1-{font.size} for {font.name}")
    from PIL import ImageDraw, ImageFont
    cps = [cp for cp in cps if font.has(cp)]
    face = ImageFont.truetype(str(ttf), size or font.size - 3)
    base = baseline(font) if base is None else base
    glyphs = {}
    for cp in cps:
        glyph = Image.new("L", (font.size, font.size), PAPER)
        draw = ImageDraw.Draw(glyph)
        draw.fontmode = "1"
        draw.text((1, base), chr(cp), font=face, fill=INK, anchor="ls")
        glyphs[cp] = glyph
    info = {"source": Path(ttf).name}
    if advance is not None:
        info["advance"] = advance
    return _save_sheet(font, glyphs, path, cols, info)


def _save_sheet(font: Font, glyphs: dict[int, Image.Image], path: Path, cols: int, info: dict) -> int:
    cell = font.size + 1
    rows = (len(glyphs) + cols - 1) // cols
    sheet = Image.new("L", (cols * cell + 1, rows * cell + 1), GRID)
    for i, glyph in enumerate(glyphs.values()):
        sheet.paste(glyph, (1 + (i % cols) * cell, 1 + (i // cols) * cell))
    meta = PngInfo()
    meta.add_text(META_KEY, json.dumps({"font": font.name, "cols": cols, "cps": list(glyphs), **info}))
    sheet.save(path, pnginfo=meta)
    return len(glyphs)


@dataclass
class BdfGlyph:
    cp: int
    dwidth: int
    bbx: tuple[int, int, int, int]  # w, h, x offset, y offset (from the baseline, up)
    rows: list[int]                 # one int per row, MSB = leftmost of `bits` bits
    bits: int


@dataclass
class Bdf:
    name: str
    ascent: int
    descent: int
    glyphs: dict[int, BdfGlyph]


def parse_bdf(text: str) -> Bdf:
    """The parts of a BDF 2.1 file a sheet needs. Only Unicode (ISO10646) and Latin-1 (ISO8859-1)
    encodings, where ENCODING is the code point."""
    props, glyphs = {}, {}
    lines = iter(text.splitlines())
    if not next(lines, "").startswith("STARTFONT"):
        raise FirmwareError("not a BDF font (no STARTFONT)")
    cur = None
    for line in lines:
        key, _, rest = line.strip().partition(" ")
        if cur is None:
            if key == "STARTCHAR":
                cur = {"rows": []}
            elif key in ("FONT", "CHARSET_REGISTRY", "CHARSET_ENCODING", "FONT_ASCENT", "FONT_DESCENT",
                         "FONTBOUNDINGBOX"):
                props[key] = rest.strip().strip('"')
        elif key == "ENCODING":
            cur["cp"] = int(rest.split()[0])
        elif key == "DWIDTH":
            cur["dwidth"] = int(rest.split()[0])
        elif key == "BBX":
            cur["bbx"] = tuple(int(v) for v in rest.split()[:4])
        elif key == "BITMAP":
            cur["bitmap"] = True
        elif key == "ENDCHAR":
            if cur.get("cp", -1) >= 0 and "bbx" in cur:
                bits = 4 * len(cur["rows"][0]) if cur["rows"] else 0
                glyphs[cur["cp"]] = BdfGlyph(cur["cp"], cur.get("dwidth", 0), cur["bbx"],
                                             [int(r, 16) for r in cur["rows"]], bits)
            cur = None
        elif cur.get("bitmap") and key:
            cur["rows"].append(key)
    charset = props.get("CHARSET_REGISTRY", "ISO10646").upper() + "-" + props.get("CHARSET_ENCODING", "1")
    if charset not in ("ISO10646-1", "ISO8859-1"):
        raise FirmwareError(f"BDF charset {charset} is not Unicode or Latin-1; convert it to ISO10646 first")
    box = [int(v) for v in props.get("FONTBOUNDINGBOX", "0 0 0 0").split()]
    ascent = int(props.get("FONT_ASCENT", box[1] + box[3]))
    descent = int(props.get("FONT_DESCENT", -box[3]))
    return Bdf(props.get("FONT", ""), ascent, descent, glyphs)


def sheet_from_bdf(font: Font, bdf_path: Path, cps: list[int], path: Path, cols: int = 16,
                   base: int | None = None, advance: int | str | None = None) -> tuple[int, list[int]]:
    """Copy a BDF bitmap font's glyphs into a glyph sheet, pixel for pixel, on `base` (default: the
    BDF's ascent when ascent + descent fit the cell, else the firmware font's baseline). Widths:
    the BDF's DWIDTH per glyph (default), "ink" for rightmost ink + 1, or a number for all.
    With "ink" the glyphs move one column right: the firmware's convention (Sony's glyphs and
    from-ttf) is a blank column on the left, while BDF fonts keep their spacing on the right.
    Returns (glyph count, code points whose pixels did not fit the cell)."""
    bdf = parse_bdf(Path(bdf_path).read_text(encoding="latin-1"))
    if base is None:
        base = bdf.ascent if 0 < bdf.ascent + bdf.descent <= font.size else baseline(font)
    if isinstance(advance, int) and not 1 <= advance <= font.size:
        raise FirmwareError(f"advance {advance} is outside 1-{font.size} for {font.name}")
    if advance not in (None, "ink") and not isinstance(advance, int):
        raise FirmwareError(f"advance must be a number or 'ink', not {advance!r}")
    left = 1 if advance == "ink" else 0
    glyphs, widths, clipped = {}, {}, []
    for cp in cps:
        g = bdf.glyphs.get(cp)
        if g is None or not font.has(cp):
            continue
        w, h, xo, yo = g.bbx
        img = Image.new("L", (font.size, font.size), PAPER)
        top = base - yo - h
        lost = False
        for r, bits in enumerate(g.rows[:h]):
            for c in range(w):
                if bits >> (g.bits - 1 - c) & 1:
                    x, y = left + xo + c, top + r
                    if 0 <= x < font.size and 0 <= y < font.size:
                        img.putpixel((x, y), INK)
                    else:
                        lost = True
        if lost:
            clipped.append(cp)
        glyphs[cp] = img
        if g.dwidth > 0:
            widths[str(cp)] = min(g.dwidth, font.size)
    if not glyphs:
        raise FirmwareError(f"{Path(bdf_path).name} has none of those characters that {font.name} has")
    info = {"source": Path(bdf_path).name}
    if isinstance(advance, int):
        info["advance"] = advance
    elif advance is None:
        info["widths"] = widths
    return _save_sheet(font, glyphs, path, cols, info), clipped


def preview(font: Font, text: str, scale: int = 3) -> Image.Image:
    """Render text with the firmware's own glyphs (missing characters are skipped)."""
    lines = text.split("\\")
    width = max(sum(font.width(ord(c)) or font.size // 2 for c in line if font.has(ord(c))) for line in lines) + 4
    img = Image.new("L", (max(width, 8), len(lines) * (font.size + 2) + 2), PAPER)
    for row, line in enumerate(lines):
        x = 2
        for c in line:
            if not font.has(ord(c)):
                continue
            glyph = font.image(ord(c))
            img.paste(glyph, (x, 2 + row * (font.size + 2)), glyph)
            x += font.width(ord(c)) or font.size // 2
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST)
