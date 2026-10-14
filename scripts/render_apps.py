"""Render the launcher list and a Snake game as the player draws them, for the README.

    uv run python -I scripts/render_apps.py [IMAGE] [-o docs/apps-demo.png]

IMAGE is a built RKNANOFW.IMG (default out/launcher/...): its 12 px font and its home backdrop
(picture 105, so a themed build gives a themed list) are what the player would use. Layout,
coordinates and colors follow mods/launcher/launcher.c and apps/snake/snake.c; the snake's
position is made up. Each screen is 128x160, shown at 2x.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from nwe39x import imageres  # noqa: E402
from nwe39x.fonts import Font  # noqa: E402
from nwe39x.rknanofw import Firmware  # noqa: E402

GREEN, WHITE, GRAY, BLACK, RED, HEAD, WALL = 0x47A6, 0xFFFF, 0x7BCF, 0x0000, 0xF800, 0x07E0, 0x39E7


def rgb(c: int) -> tuple[int, int, int]:
    return ((c >> 11) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31)


class Screen:
    def __init__(self, font: Font, background: Image.Image | None = None):
        self.font = font
        self.img = background.convert("RGB").copy() if background else Image.new("RGB", (128, 160), rgb(BLACK))

    def fill(self, x0: int, y0: int, x1: int, y1: int, color: int):   # ui_fill: inclusive
        for y in range(max(y0, 0), min(y1, 159) + 1):
            for x in range(max(x0, 0), min(x1, 127) + 1):
                self.img.putpixel((x, y), rgb(color))

    def text(self, x: int, y: int, s: str, color: int):               # ui_text: transparent background
        for ch in s:
            cp = ord(ch)
            if not self.font.has(cp):
                continue
            for row, bits in enumerate(self.font.rows(cp)):
                for col in range(self.font.size):
                    if bits & (1 << (15 - col)) and 0 <= x + col < 128 and y + row < 160:
                        self.img.putpixel((x + col, y + row), rgb(color))
            x += self.font.width(cp) or self.font.size // 2


def launcher(font: Font, backdrop: Image.Image) -> Image.Image:
    s = Screen(font, backdrop)
    s.text(4, 18, "Apps", GREEN)
    apps, sel = [(1, "Key test"), (2, "Snake")], 2
    for row, (n, name) in enumerate(apps):
        s.text(4, 34 + 13 * row, f"{'>' if n == sel else ' '} APP{n} {name}", GREEN if n == sel else WHITE)
    s.text(4, 134, "center: run", GRAY)
    s.text(4, 148, "OPTION: home", GRAY)
    return s.img


def snake(font: Font) -> Image.Image:
    s = Screen(font)
    cell = lambda c, color: s.fill(c[0] * 8 + 1, 20 + c[1] * 8 + 1, c[0] * 8 + 6, 20 + c[1] * 8 + 6, color)  # noqa: E731
    s.fill(0, 19, 127, 19, WALL)
    # tail first, head last: length 17 = 3 + 2 per food at score 7
    path = [(3, 13), (3, 12), (3, 11), (3, 10), (4, 10), (5, 10), (6, 10), (7, 10), (7, 9), (7, 8),
            (7, 7), (8, 7), (9, 7), (10, 7), (11, 7), (11, 6), (11, 5)]
    for c in path[:-1]:
        cell(c, GREEN)
    cell(path[-1], HEAD)
    cell((11, 2), RED)
    s.text(2, 3, "Score 7", WHITE)
    s.text(76, 3, "Best 12", GRAY)
    return s.img


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image", nargs="?", type=Path, default=Path("out/launcher/Data/Device/RKNANOFW.IMG"))
    ap.add_argument("-o", "--out", type=Path, default=Path("docs/apps-demo.png"))
    args = ap.parse_args()
    fw = Firmware.load(args.image)
    font = Font.font12(fw)
    backdrop = imageres.decode(fw, imageres.pictures(fw)[105])
    screens = [launcher(font, backdrop), snake(font)]
    gap, scale = 8, 2   # as docs/bootscreen-demo.png: white 8 px gap, shown at 2x
    sheet = Image.new("RGB", (len(screens) * 128 + (len(screens) - 1) * gap, 160), (255, 255, 255))
    for i, img in enumerate(screens):
        sheet.paste(img, (i * (128 + gap), 0))
    sheet = sheet.resize((sheet.width * scale, sheet.height * scale), Image.NEAREST)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out, optimize=True)
    print(f"{args.out}: {sheet.width}x{sheet.height}")


if __name__ == "__main__":
    main()
