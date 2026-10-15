"""Explain every byte a built image changes compared with Sony's, so nothing changes by accident.

`explain` names each differing byte by the resource it belongs to (a picture, a string slot, a
glyph, a width byte, a patch from the given patches.tsv files, the version fields, the CRC) and
returns whatever it cannot name. A byte inside a patch must also hold that patch's new value; any
other value there is a mismatch, not explained. `build` writes a manifest.json beside the image
listing the patch files it used; `flash` runs this check against it and refuses an image with
unexplained or mismatched bytes unless forced.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import fonts, imageres, patches, strtbl, updater
from .rknanofw import HEADER_SIZE, Firmware, FirmwareError

MANIFEST = "manifest.json"


@dataclass
class Report:
    hits: dict[str, int] = field(default_factory=dict)        # region name -> bytes changed
    glyphs: dict[str, set[int]] = field(default_factory=dict)  # font name -> code points changed
    unknown: list[int] = field(default_factory=list)           # offsets of unexplained bytes
    mismatched: list[int] = field(default_factory=list)        # patch bytes that are not the patch's new bytes

    @property
    def ok(self) -> bool:
        return not self.unknown and not self.mismatched

    def lines(self) -> list[str]:
        out = [f"{name}: {n} bytes" for name, n in self.hits.items()]
        out += [f"{font}: {len(cps)} glyphs, U+{min(cps):04X}..U+{max(cps):04X}" for font, cps in self.glyphs.items()]
        if self.unknown:
            out.append(f"UNEXPECTED: {len(self.unknown)} bytes outside known regions, first at {self.unknown[0]:#x}")
        if self.mismatched:
            out.append(f"PATCH MISMATCH: {len(self.mismatched)} bytes differ from their patch's new bytes, "
                       f"first at {self.mismatched[0]:#x}")
        return out


def explain(stock: Firmware, built: Firmware, patch_files: list[Path] = ()) -> Report:
    if len(built.buf) != len(stock.buf):
        raise FirmwareError("images differ in size")
    regions = [(p.offset, p.offset + p.size, f"picture {p.index:03d}") for p in imageres.pictures(stock)]
    patch_new: dict[int, set[int]] = {}  # offset -> every value a patch puts there (patches may overlap)
    for f in patch_files:
        ps = patches.parse_tsv(Path(f))
        regions += patches.regions(stock, ps)
        for p in ps:
            off = patches.code_offset(stock, p.section, p.addr, len(p.new))
            for k, b in enumerate(p.new):
                patch_new.setdefault(off + k, set()).add(b)
    regions += [(t.offset, t.offset + strtbl.SLOT, f"string {t.lang}:{t.record} ({t.text!r})") for t in strtbl.texts(stock)]
    m = updater.VERSION_RE.search(bytes(stock.buf))
    regions += [(m.start(1), m.end(1), "firmware version (XML)"), (4, 8, "header version"),
                (stock.size_field + 4, stock.size_field + 8, "backup header version"),
                (len(stock.buf) - 4, len(stock.buf), "CRC")]
    f16, f12 = fonts.Font.font16(stock), fonts.Font.font12(stock)
    f12_glyph_cp = {v: i + 0x20 for i, v in enumerate(f12.table) if v != 0xFFFF}
    f12_data, f12_widths = f12.glyphs_offset, f12.widths_offset
    # CJK records -> the first code point drawn from them (several may share one); the Latin table
    # wins over the CJK index, as on the player, so a code point it covers never names a CJK record.
    f12_cjk_cp: dict[int, int] = {}
    for cp, r in enumerate(f12.cjk):
        if r and f12.glyph(cp) is None:
            f12_cjk_cp.setdefault(r - 1, cp)
    f12_banks = [(f12.blob_offset + start, name) for start, name in zip(fonts.CJK_BANKS, ("font12", "font12zh"))
                 if f12.cjk]

    def glyph_at(i: int) -> tuple[str, int] | None:
        if f16.blob_offset <= i < f16.blob_offset + min(f16.blob_size, fonts.FONT16_GLYPHS * 33):
            return "font16", (i - f16.blob_offset) // 33
        if f12_data <= i < f12_widths:
            cp = f12_glyph_cp.get((i - f12_data) // fonts.FONT12_RECORD)
            return ("font12", cp) if cp is not None else None
        if f12_widths <= i < f12_widths + f12.glyph_count:
            cp = f12_glyph_cp.get(i - f12_widths)
            return ("font12 widths", cp) if cp is not None else None
        for start, name in f12_banks:
            if start <= i < start + fonts.CJK_BANK_GLYPHS * fonts.FONT12_RECORD:
                cp = f12_cjk_cp.get((i - start) // fonts.FONT12_RECORD)
                return (name, cp) if cp is not None else None
        return None

    rep = Report()
    for i in (i for i in range(len(stock.buf)) if built.buf[i] != stock.buf[i]):
        if i in patch_new and built.buf[i] not in patch_new[i]:
            rep.mismatched.append(i)
            continue
        name = next((n for s, e, n in regions if s <= i < e), None)
        if name:
            rep.hits[name] = rep.hits.get(name, 0) + 1
        elif g := glyph_at(i):
            rep.glyphs.setdefault(g[0], set()).add(g[1])
        else:
            rep.unknown.append(i)
    return rep


VERSION_REGIONS = {"firmware version (XML)", "header version", "backup header version", "CRC"}


RESOURCE_TABLES = ("font", "gbk", "strtbl", "imageres")


def code_changes(stock: Firmware, built: Firmware) -> list[int]:
    """Offsets of changed payload bytes that are not inside a resource blob (font, gbk, strtbl,
    imageres) and not the OS version string: the boot stages, the OS, unknown blobs, gaps between
    blobs, and the free tail where app sections put their code. Checking the complement rather than
    a list of code ranges means a `file` patch into a boot stage cannot slip past the gate.
    Resource edits never land here; byte patches and app sections do."""
    resources = sorted((b.offset, b.end) for t in RESOURCE_TABLES for b in stock.blobs.get(t, []) if b.size)
    m = updater.VERSION_RE.search(bytes(stock.buf))
    a, b, out = stock.buf, built.buf, []
    lo = HEADER_SIZE
    for r_lo, r_hi in resources + [(stock.size_field, stock.size_field)]:  # resources may overlap or touch
        hi = min(r_lo, stock.size_field)
        for start in range(lo, hi, 0x1000):  # compare in pages, look closer only where they differ
            end = min(start + 0x1000, hi)
            if a[start:end] != b[start:end]:
                out += [i for i in range(start, end) if a[i] != b[i] and not m.start(1) <= i < m.end(1)]
        lo = max(lo, r_hi)
    return out


def is_stock(stock: Firmware, built: Firmware) -> bool:
    """True if `built` is Sony's image apart from its version fields and CRC (what `restore` makes)."""
    rep = explain(stock, built)
    return built.problems() == [] and rep.ok and not rep.glyphs and set(rep.hits) <= VERSION_REGIONS


def write_manifest(outdir: Path, version: str, patch_files: list[Path], mod: str | None):
    data = {"version": version, "mod": mod, "patches": [str(Path(p).resolve()) for p in patch_files]}
    (outdir / MANIFEST).write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_manifest(outdir: Path) -> dict | None:
    f = outdir / MANIFEST
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
