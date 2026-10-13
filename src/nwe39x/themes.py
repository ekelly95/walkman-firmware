"""Recolour the UI: the stock theme is black with gold accents (highlight bars, icons, the battery
frame), blue rings for the boot animation and red rings for alerts. A theme is a per-pixel colour
transform applied to every picture, written out as a folder of PNGs for `build --images`.

    mono       accents become light grey (a plain white-on-black UI); reds stay red for alerts
    hue DEG    rotate every colour by DEG degrees (gold is ~40: 200 gives ice blue, 290 purple)

Pictures 044 (boot) and 083 (power off) are artwork and are left alone by default.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import imageres
from .rknanofw import Firmware, FirmwareError

ARTWORK = {44, 83}


def mono(img: Image.Image, keep_red: bool = True) -> Image.Image:
    h, s, v = img.convert("HSV").split()
    if keep_red:
        # Hue 0-255 scale: red sits below ~14 and above ~240.
        red = h.point(lambda x: 255 if x < 14 or x > 240 else 0)
        s = Image.composite(s, s.point(lambda _: 0), red)
    else:
        s = s.point(lambda _: 0)
    return Image.merge("HSV", (h, s, v)).convert("RGB")


def hue_shift(img: Image.Image, degrees: float) -> Image.Image:
    delta = round(degrees * 255 / 360) % 256
    h, s, v = img.convert("HSV").split()
    h = h.point(lambda x: (x + delta) % 256)
    return Image.merge("HSV", (h, s, v)).convert("RGB")


def transform(name: str, hue: float | None = None):
    if name == "mono":
        return mono
    if name == "hue":
        if hue is None:
            raise FirmwareError("hue theme needs --hue DEG")
        return lambda img: hue_shift(img, hue)
    raise FirmwareError(f"unknown theme {name!r}; use mono or hue")


def generate(fw: Firmware, outdir: Path, fn, skip: set[int] = ARTWORK, sheet: Path | None = None) -> list[int]:
    """Write every picture the transform changes into outdir as NNN_WxH_at.png. Returns the indices."""
    outdir.mkdir(parents=True, exist_ok=True)
    changed, previews = [], []
    for p in imageres.pictures(fw):
        src = imageres.decode(fw, p)
        out = src if p.index in skip else fn(src)
        previews.append(out)
        if imageres.encode(out) != imageres.encode(src):
            out.save(outdir / p.filename)
            changed.append(p.index)
    if sheet:
        imageres.contact_sheet(previews).save(sheet)
    return changed
