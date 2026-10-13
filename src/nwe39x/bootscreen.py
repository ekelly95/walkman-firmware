"""Turn a photo into a 128x160 picture for the boot screen (picture 44), optionally captioned."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 128, 160
BOOT_PICTURE = 44
FONTS = [r"C:\Windows\Fonts\segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]


def _font(size: int, path: str | None = None) -> ImageFont.ImageFont:
    if path:
        return ImageFont.truetype(path, size)
    for path in FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def fit(photo: Image.Image, focus: tuple[float, float] = (0.5, 0.5), zoom: float = 1.0) -> Image.Image:
    """Crop to the screen's 4:5 shape around `focus` (fractions of the photo), then resize."""
    pw, ph = photo.size
    cw = min(pw, ph * W / H) / zoom
    ch = cw * H / W
    left = min(max(focus[0] * pw - cw / 2, 0), pw - cw)
    top = min(max(focus[1] * ph - ch / 2, 0), ph - ch)
    return photo.crop((round(left), round(top), round(left + cw), round(top + ch))).resize((W, H), Image.LANCZOS)


def caption(img: Image.Image, lines: list[str], size: int = 11, font_path: str | None = None) -> Image.Image:
    """White text on a dark fade at the bottom, like Sony's 'For Music Lovers' screen. With a font
    file given (e.g. Terminus, a pixel font), glyphs are drawn without anti-aliasing at `size`."""
    img = img.convert("RGBA")
    fade = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(fade)
    band = 18 + 14 * len(lines)
    for y in range(band):
        d.line([(0, H - band + y), (W, H - band + y)], fill=(0, 0, 0, int(215 * min(1, y / (band * 0.6)))))
    img = Image.alpha_composite(img, fade)
    d = ImageDraw.Draw(img)
    if font_path:
        d.fontmode = "1"  # pixel fonts stay crisp; system fonts keep their anti-aliasing
    font = _font(size, font_path)
    y = H - 6 - 14 * len(lines)
    for line in lines:
        d.text(((W - d.textlength(line, font=font)) / 2, y), line, font=font, fill=(255, 255, 255))
        y += 14
    return img.convert("RGB")


def quantize_rgb565(img: Image.Image) -> Image.Image:
    """Round to 5-6-5 bits so a preview looks exactly like the panel."""
    px = bytearray(img.convert("RGB").tobytes())
    for i in range(0, len(px), 3):
        r, g, b = px[i] >> 3, px[i + 1] >> 2, px[i + 2] >> 3
        px[i], px[i + 1], px[i + 2] = r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2
    return Image.frombytes("RGB", img.size, bytes(px))


def make(photo_path: Path, lines: list[str], focus=(0.5, 0.5), zoom=1.0, font: str | None = None,
         size: int = 11) -> Image.Image:
    photo = ImageOps.exif_transpose(Image.open(photo_path)).convert("RGB")
    img = fit(photo, focus, zoom)
    if lines:
        img = caption(img, lines, size, font)
    return quantize_rgb565(img)
