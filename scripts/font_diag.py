"""Write a diagnostic glyph sheet that shows which part of a glyph cell the player draws.

    uv run python -I scripts/font_diag.py extract/cab/Data/Device/RKNANOFW.IMG OUT.png [16|12]

A: solid block      -> the visible part is the drawing window
G: pixel (x, y) on if y <= x  (column x filled down to row x)   -> which columns are drawn
P: pixel (x, y) on if x <= y  (row y filled across to column y) -> which rows are drawn
S: left half solid                                -> whether drawing starts at column 0
Both fonts get an advance width from the ink on import (font16 in the record, font12 in its width table).
"""

import json
import sys
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from nwe39x import fonts  # noqa: E402
from nwe39x.rknanofw import Firmware  # noqa: E402

PATTERNS = {
    "A": lambda x, y, n: True,
    "G": lambda x, y, n: y <= x,
    "P": lambda x, y, n: x <= y,
    "S": lambda x, y, n: x < n // 2,
}


def main(img_path: str, out: str, which: str = "16"):
    font = fonts.Font.by_name(Firmware.load(img_path), which)
    cps = [ord(c) for c in PATTERNS]
    cell = font.size + 1
    sheet = Image.new("L", (len(cps) * cell + 1, cell + 1), fonts.GRID)
    for i, ch in enumerate(PATTERNS):
        n = font.size
        glyph = Image.new("L", (n, n), fonts.PAPER)
        for y in range(n):
            for x in range(n):
                if PATTERNS[ch](x, y, n):
                    glyph.putpixel((x, y), fonts.INK)
        sheet.paste(glyph, (1 + i * cell, 1))
    meta = PngInfo()
    meta.add_text(fonts.META_KEY, json.dumps({"font": font.name, "cols": len(cps), "cps": cps, "source": "font_diag"}))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, pnginfo=meta)
    print(f"wrote {out}: {', '.join(PATTERNS)}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
