"""Test the reader's line layout on the PC, with the player's own font widths.

    uv run python -I scripts/reader_test.py [TEXT] [--image RKNANOFW.IMG] [--show]

Exports the 12 px font's glyph map and widths from a built image (default out/launcher/...; the
font in the image you flash is the one the player measures with), compiles apps/reader/reader.c
natively with apps/reader/test/harness.c (gcc, directly or through WSL), and lays out TEXT
(default the sample book). Fails if a line is wider than the screen or a character goes missing.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from nwe39x.fonts import Font  # noqa: E402
from nwe39x.rknanofw import Firmware  # noqa: E402


def run(cmd: list[str], cwd: Path) -> int:
    if shutil.which(cmd[0]):
        return subprocess.run(cmd, cwd=cwd).returncode
    return subprocess.run(["wsl.exe", "--cd", str(cwd.resolve()), "-e", *cmd]).returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("text", nargs="?", type=Path, default=ROOT / "apps/reader/sample/BOOK0.TXT")
    ap.add_argument("--image", type=Path, default=ROOT / "out/launcher/Data/Device/RKNANOFW.IMG")
    ap.add_argument("--show", action="store_true", help="print every line with its width")
    args = ap.parse_args()

    work = ROOT / "apps/reader/build/test"
    work.mkdir(parents=True, exist_ok=True)
    fw = Firmware.load(args.image)
    f = Font.font12(fw)
    glyph = [g if g is not None else 0xFFFF for g in (f.glyph(cp) for cp in range(0x20, 0x20F7))]
    widths = [fw.buf[f.widths_offset + i] for i in range(f.glyph_count)]
    (work / "fontdata.h").write_text(
        "static const unsigned short GLYPH[] = {" + ",".join(map(str, glyph)) + "};\n"
        "static const unsigned char WIDTH[] = {" + ",".join(map(str, widths)) + "};\n")
    for stub in ("fw.h", "nwapp.h"):   # the harness defines what reader.c needs from these
        (work / stub).write_text("/* host stand-in */\n")
    for src in ("apps/reader/reader.c", "apps/reader/test/harness.c", "apps/sdk/ui.h"):
        shutil.copy(ROOT / src, work)
    shutil.copy(args.text, work / "book.txt")
    if run(["gcc", "-O1", "-Wall", "-Wno-unused-function", "-o", "harness", "harness.c"], work):
        sys.exit("harness did not compile")
    sys.exit(run(["./harness", "book.txt", *(["show"] if args.show else [])], work))


if __name__ == "__main__":
    main()
