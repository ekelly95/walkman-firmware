"""Recolor the UI: the stock theme is black with gold accents (highlight bars, icons, the battery
frame), blue rings for the boot animation and red rings for alerts. A theme is a per-pixel color
transform applied to every picture, written out as a folder of PNGs for `build --images`.

    mono       accents become light gray (a plain white-on-black UI); reds stay red for alerts
    hue DEG    rotate every color by DEG degrees (gold is ~40: 200 gives ice blue, 290 purple)

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


def saturate(img: Image.Image, factor: float) -> Image.Image:
    h, s, v = img.convert("HSV").split()
    s = s.point(lambda x: min(255, round(x * factor)))
    return Image.merge("HSV", (h, s, v)).convert("RGB")


def brighten(img: Image.Image, factor: float) -> Image.Image:
    h, s, v = img.convert("HSV").split()
    v = v.point(lambda x: min(255, round(x * factor)))
    return Image.merge("HSV", (h, s, v)).convert("RGB")


def tint(img: Image.Image, hue_deg: float, sat: float = 0.6) -> Image.Image:
    """Everything colored becomes one hue (a phosphor look); grays stay gray."""
    h, s, v = img.convert("HSV").split()
    h = h.point(lambda _: round(hue_deg * 255 / 360) % 256)
    s = s.point(lambda x: min(255, round(x * sat)))
    return Image.merge("HSV", (h, s, v)).convert("RGB")


def accent(img: Image.Image, hue_deg: float) -> Image.Image:
    """Move only the gold accent (hue 15-70 degrees) to another hue; the red alert rings and the
    blue boot rings keep their colors."""
    h, s, v = img.convert("HSV").split()
    lo, hi = round(15 * 255 / 360), round(70 * 255 / 360)
    gold = h.point(lambda x: 255 if lo <= x <= hi else 0)
    target = h.point(lambda _: round(hue_deg * 255 / 360) % 256)
    return Image.merge("HSV", (Image.composite(target, h, gold), s, v)).convert("RGB")


# Stock gold sits at about hue 40. Presets move it, or treat the whole palette.
PRESETS = {
    "mono": ("gray accents, reds kept for alerts", mono),
    "ice": ("gold accent -> ice blue", lambda im: accent(im, 195)),
    "sony-blue": ("gold accent -> the classic Walkman blue", lambda im: accent(im, 220)),
    "purple": ("gold accent -> violet", lambda im: accent(im, 275)),
    "mint": ("gold accent -> mint green", lambda im: accent(im, 150)),
    "rose": ("gold accent -> pink", lambda im: accent(im, 330)),
    "amber": ("everything amber, like an old phosphor display", lambda im: tint(im, 35)),
    "matrix": ("everything green phosphor", lambda im: tint(im, 115, 0.8)),
    "neon": ("stock colors, saturated and brighter", lambda im: brighten(saturate(im, 1.6), 1.15)),
    "ghost": ("mono, dimmed: accents barely there", lambda im: brighten(mono(im), 0.65)),
}


def transform(name: str, hue: float | None = None):
    if name == "hue":
        if hue is None:
            raise FirmwareError("hue theme needs --hue DEG")
        return lambda img: hue_shift(img, hue)
    if name in PRESETS:
        return PRESETS[name][1]
    raise FirmwareError(f"unknown theme {name!r}; use hue or one of {', '.join(PRESETS)}")


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


def apply(fw: Firmware, fn, skip: set[int] = ARTWORK) -> list[int]:
    """Recolor the pictures in place (no folder). Returns the indices that changed."""
    changed = []
    for p in imageres.pictures(fw):
        if p.index in skip:
            continue
        src = imageres.decode(fw, p)
        new = imageres.encode(fn(src))
        if new != bytes(fw.buf[p.offset:p.offset + p.size]):
            fw.write(p.offset, new)
            changed.append(p.index)
    return changed
