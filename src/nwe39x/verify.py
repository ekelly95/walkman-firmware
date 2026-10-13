"""Explain every byte a built image changes compared with Sony's, so nothing changes by accident.

`explain` names each differing byte by the resource it belongs to (a picture, a string slot, a
glyph, a width byte, a patch from the given patches.tsv files, the version fields, the CRC) and
returns whatever it cannot name. `build` writes a manifest.json beside the image listing the
patch files it used; `flash` runs this check against it and refuses an image with unexplained
bytes unless forced.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import fonts, imageres, patches, strtbl, updater
from .rknanofw import Firmware, FirmwareError

MANIFEST = "manifest.json"


@dataclass
class Report:
    hits: dict[str, int] = field(default_factory=dict)        # region name -> bytes changed
    glyphs: dict[str, set[int]] = field(default_factory=dict)  # font name -> code points changed
    unknown: list[int] = field(default_factory=list)           # offsets of unexplained bytes

    def lines(self) -> list[str]:
        out = [f"{name}: {n} bytes" for name, n in self.hits.items()]
        out += [f"{font}: {len(cps)} glyphs, U+{min(cps):04X}..U+{max(cps):04X}" for font, cps in self.glyphs.items()]
        if self.unknown:
            out.append(f"UNEXPECTED: {len(self.unknown)} bytes outside known regions, first at {self.unknown[0]:#x}")
        return out


def explain(stock: Firmware, built: Firmware, patch_files: list[Path] = ()) -> Report:
    if len(built.buf) != len(stock.buf):
        raise FirmwareError("images differ in size")
    regions = [(p.offset, p.offset + p.size, f"picture {p.index:03d}") for p in imageres.pictures(stock)]
    for f in patch_files:
        regions += patches.regions(stock, patches.parse_tsv(Path(f)))
    regions += [(t.offset, t.offset + strtbl.SLOT, f"string {t.lang}:{t.record} ({t.text!r})") for t in strtbl.texts(stock)]
    m = updater.VERSION_RE.search(bytes(stock.buf))
    regions += [(m.start(1), m.end(1), "firmware version (XML)"), (4, 8, "header version"),
                (stock.size_field + 4, stock.size_field + 8, "backup header version"),
                (len(stock.buf) - 4, len(stock.buf), "CRC")]
    f16, f12 = fonts.Font.font16(stock), fonts.Font.font12(stock)
    f12_glyph_cp = {v: i + 0x20 for i, v in enumerate(f12.table) if v != 0xFFFF}
    f12_data, f12_widths = f12.glyphs_offset, f12.widths_offset

    def glyph_at(i: int) -> tuple[str, int] | None:
        if f16.blob_offset <= i < f16.blob_offset + f16.blob_size:
            return "font16", (i - f16.blob_offset) // 33
        if f12_data <= i < f12_widths:
            cp = f12_glyph_cp.get((i - f12_data) // fonts.FONT12_RECORD)
            return ("font12", cp) if cp is not None else None
        if f12_widths <= i < f12_widths + f12.glyph_count:
            cp = f12_glyph_cp.get(i - f12_widths)
            return ("font12 widths", cp) if cp is not None else None
        return None

    rep = Report()
    for i in (i for i in range(len(stock.buf)) if built.buf[i] != stock.buf[i]):
        name = next((n for s, e, n in regions if s <= i < e), None)
        if name:
            rep.hits[name] = rep.hits.get(name, 0) + 1
        elif g := glyph_at(i):
            rep.glyphs.setdefault(g[0], set()).add(g[1])
        else:
            rep.unknown.append(i)
    return rep


def write_manifest(outdir: Path, version: str, patch_files: list[Path], mod: str | None):
    data = {"version": version, "mod": mod, "patches": [str(Path(p).resolve()) for p in patch_files]}
    (outdir / MANIFEST).write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_manifest(outdir: Path) -> dict | None:
    f = outdir / MANIFEST
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
