"""Compile an app: the launcher into an app slot (a patches.tsv for `nwe39x build`), or a .BIN app
for the launcher to load from the player's drive.

    uv run python -I scripts/build_app.py mods/launcher [--slot 7] [--image RKNANOFW.IMG]
    uv run python -I scripts/build_app.py --bin apps/keytest          # -> apps/keytest/build/KEYTEST.BIN

Every .c file in the folder is compiled with the SDK in apps/sdk (fw.h, nwapp.h, ui.c, rt.c).
The compiler is arm-none-eabi-gcc, run directly if it is on PATH, else through WSL.

Slot mode: the folder has a slot.ld. The app becomes
the code and data of an empty stage 3 section (Sony left sections 26 and 27, the Record and Ebook
apps, empty), placed in the free space after the last blob; the patches set that section's header,
the app's descriptor pointer in the app table, and point the home menu's Photos icon at it. Every
patch carries the stock bytes it replaces, so `build`, `diff` and `flash` check it as usual.
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from nwe39x.rknanofw import Firmware, stage_sections  # noqa: E402

APP_SECTIONS = {6: 26, 7: 27}       # app index -> its (empty) stage 3 section
APP_TABLE = 0x3090a34                # section 2 data: descriptor pointer per app index
CODE_PA, DATA_PA = 0x306C4A4, 0x3023010
PLACE = 0xC94200                     # file offset for app code: after the last blob (0xc9411e)
SDK = Path(__file__).resolve().parent.parent / "apps" / "sdk"
NWAPP_LOAD, NWAPP_MAX, NWAPP_MAGIC = 0x306D000, 0x4E00, 0x5041574E
CFLAGS = ["-mcpu=cortex-m3", "-mthumb", "-Os", "-ffreestanding", "-nostdlib", "-fno-builtin",
          "-fno-zero-initialized-in-bss", "-fno-common", "-ffunction-sections", "-Wall", "-Wextra"]


def run(cmd: list[str], cwd: Path):
    if shutil.which(cmd[0]):
        subprocess.run(cmd, cwd=cwd, check=True)
    else:  # through WSL, from the same folder
        subprocess.run(["wsl.exe", "--cd", str(cwd.resolve()), "-e", *cmd], check=True)


def compile_app(src: Path, ld: Path, sections: list[str]) -> list[bytes]:
    """Compile src/*.c with the SDK, link with `ld`, return the raw bytes of each output section."""
    out = src / "build"
    out.mkdir(exist_ok=True)
    rel = lambda p: os.path.relpath(p, src).replace("\\", "/")  # noqa: E731
    sources = sorted(f.name for f in src.glob("*.c")) + [rel(SDK / "ui.c"), rel(SDK / "rt.c")]
    run(["arm-none-eabi-gcc", *CFLAGS, f"-I{rel(SDK)}", "-T", rel(ld), "-Wl,--gc-sections",
         "-o", "build/app.elf", *sources], src)
    blobs = []
    for s in sections:
        run(["arm-none-eabi-objcopy", "-O", "binary", "-j", s, "build/app.elf", f"build/{s[1:]}.bin"], src)
        blobs.append((out / f"{s[1:]}.bin").read_bytes())
    return blobs


def build_bin(src: Path):
    (image,) = compile_app(src, SDK / "app.ld", [".bin"])
    magic, abi, load, end = struct.unpack_from("<4I", image)
    if magic != NWAPP_MAGIC or load != NWAPP_LOAD:
        sys.exit("no NWAPP(...) header at the start of the image")
    if end - load > NWAPP_MAX:
        sys.exit(f"app needs {end - load} bytes; the limit is {NWAPP_MAX}")
    name = image[16:32].split(bytes(1))[0].decode("ascii", "replace")
    dest = src / "build" / f"{src.name.upper()[:8]}.BIN"
    dest.write_bytes(image)
    print(f"{dest}: \"{name}\", {len(image)} bytes ({end - load} with bss) of {NWAPP_MAX}. "
          f"Copy it to the player's top folder as APP0.BIN .. APP9.BIN.")


def hexline(section: str, addr: int, old: bytes, new: bytes, note: str) -> str:
    return f"{section}\t{addr:x}\t{old.hex()}\t{new.hex()}\t{note}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("app", type=Path)
    ap.add_argument("--bin", action="store_true", help="a .BIN app for the launcher")
    ap.add_argument("--slot", type=int, default=7, choices=sorted(APP_SECTIONS))
    ap.add_argument("--image", type=Path, default=Path("extract/cab/Data/Device/RKNANOFW.IMG"))
    args = ap.parse_args()
    if args.bin:
        return build_bin(args.app)

    fw = Firmware.load(args.image)
    stage = fw.blob("stage", 3)
    base, secs = stage_sections(fw.read(stage))
    sec = APP_SECTIONS[args.slot]
    if secs[sec].code_sz or secs[sec].data_sz:
        sys.exit(f"section {sec} is not empty in this image")
    if PLACE < fw.blobs_end:
        sys.exit(f"free space starts at {fw.blobs_end:#x}, after {PLACE:#x}")

    text, data = compile_app(args.app, args.app / "slot.ld", [".text", ".data"])
    if CODE_PA + len(text) > NWAPP_LOAD:
        sys.exit(f"slot code ends at {CODE_PA + len(text):#x}, past {NWAPP_LOAD:#x} where .BIN apps load")
    if len(data) < 28:
        sys.exit("no app descriptor at the start of .data")
    code_at = PLACE
    data_at = (code_at + len(text) + 15) & ~15
    end = data_at + len(data)
    if end > fw.size_field:
        sys.exit(f"app needs {end - PLACE} bytes; {fw.size_field - PLACE} are free")
    if any(fw.buf[PLACE:end]):
        sys.exit("the free space is not empty in this image")

    lines = [f"# Generated by scripts/build_app.py from {args.app.name}: do not edit.",
             f"# {len(text)} bytes of code at {CODE_PA:#x}, {len(data)} of data at {DATA_PA:#x}, as section {sec} "
             f"(app {args.slot}).",
             "# section\trun address\told\tnew\tnote"]
    for at, blob, what in ((code_at, text, "code"), (data_at, data, "data")):
        for k in range(0, len(blob), 64):  # 64-byte lines keep the TSV readable
            chunk = blob[k:k + 64]
            lines.append(hexline("file", at + k, bytes(fw.buf[at + k:at + k + len(chunk)]), chunk,
                                 f"app {what} +{k:#x}"))
    hdr = stage.offset + 8 + 32 * sec
    s = secs[sec]
    new_hdr = struct.pack("<8I", base + code_at - stage.offset, CODE_PA, len(text),
                          base + data_at - stage.offset, DATA_PA, len(data), DATA_PA + len(data), 0)
    lines.append(hexline("file", hdr, bytes(fw.buf[hdr:hdr + 32]), new_hdr, f"section {sec} header: the app"))
    slot = APP_TABLE + 4 * args.slot
    lines.append(hexline("2", slot, struct.pack("<I", 0), struct.pack("<I", DATA_PA),
                         f"app table: descriptor for app {args.slot}"))
    # Home menu, Photos (slot 0) handler at section 17 0x306c59e: skip the "any photos?" check and
    # switch to our app instead of PhotoMenu (16).
    lines.append(hexline("17", 0x306C5A2, bytes.fromhex("40b1"), bytes.fromhex("00bf"),
                         "home Photos: no photo-count check (cbz -> nop)"))
    lines.append(hexline("17", 0x306C5AC, bytes.fromhex("1020"), bytes([args.slot, 0x20]),
                         f"home Photos: open app {args.slot} (movs r0, 16 -> {args.slot})"))
    (args.app / "patches.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{args.app / 'patches.tsv'}: {len(text)} bytes code, {len(data)} bytes data, section {sec}, "
          f"file {code_at:#x}-{end:#x}")


if __name__ == "__main__":
    main()
