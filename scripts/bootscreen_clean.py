"""Boot (044) and power-off (083) pictures that match a grayscale theme and the pixel fonts.

    uv run python -I scripts/bootscreen_clean.py extract/cab/Data/Device/RKNANOFW.IMG mods/bootscreen-clean/images [FONT12_SHEET.png]

Sony's logo is kept (grayed); the text is re-set from the firmware's own glyphs: the tagline and
"See You Later" in font12 (after importing FONT12_SHEET if given, e.g. the Terminus sheet) and
"POWER OFF" in Sony's font16.
"""

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from nwe39x import fonts, imageres, themes  # noqa: E402
from nwe39x.rknanofw import Firmware  # noqa: E402


def line(font, text):
    im = fonts.preview(font, text, 1).convert("L")
    return im.crop(im.getbbox())


def put(canvas, glyphs, y, gray):
    canvas.paste(Image.new("RGB", glyphs.size, (gray, gray, gray)), ((canvas.width - glyphs.width) // 2, y), glyphs)


def main(img, outdir, sheet=None):
    fw = Firmware.load(img)
    pics = imageres.pictures(fw)
    boot, off = imageres.decode(fw, pics[44]), imageres.decode(fw, pics[83])
    if sheet:
        fonts.import_sheet(fw, Path(sheet))
    f12, f16 = fonts.Font.font12(fw), fonts.Font.font16(fw)

    out = themes.mono(boot, keep_red=False).convert("RGB")
    out.paste((0, 0, 0), (0, 100, 128, 160))
    a, b = line(f12, "For Music Lovers,"), line(f12, "By Music Lovers")
    y = 100 + (60 - a.height - b.height - 4) // 2
    put(out, a, y, 230)
    put(out, b, y + a.height + 4, 230)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    out.save(Path(outdir) / pics[44].filename)

    out = themes.mono(off, keep_red=False).convert("RGB")
    out.paste((0, 0, 0), (0, 40, 128, 160))
    put(out, line(f16, "POWER OFF"), 62, 235)
    put(out, line(f12, "See You Later"), 96, 200)
    out.save(Path(outdir) / pics[83].filename)
    print(f"wrote {pics[44].filename} and {pics[83].filename} to {outdir}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
