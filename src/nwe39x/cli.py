"""nwe39x: mod the firmware of Sony's NW-E393/E394/E395 Walkman.

  nwe39x unpack NW-E390_V1_01.exe          unpack Sony's updater into extract/
  nwe39x status                            connected players and the version they report
  nwe39x info                              header, resources, checks
  nwe39x diff BUILT.IMG                    what a build changes compared with Sony's image
  nwe39x blobs DIR                         raw resources (stage3.bin is the OS, for Ghidra)
  nwe39x images export DIR                 every UI picture as PNG (+ contact sheet)
  nwe39x strings export FILE.tsv           every UI string, all 13 languages
  nwe39x fonts export SHEET.png            glyph sheet (--font 16|12, --range ascii|cyrillic|...)
  nwe39x fonts preview "text" OUT.png      render text with the firmware's own glyphs
  nwe39x bootscreen PHOTO OUT.png          make a 128x160 boot picture from a photo
  nwe39x build --mod DIR                   patched updater in out/updater from DIR/images/*.png,
                                           DIR/strings.tsv and DIR/fonts/*.png (version from the player)
  nwe39x restore                           Sony's stock firmware, re-versioned so it installs over a mod
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import bootscreen, device, fonts, imageres, strtbl, updater
from .rknanofw import Firmware, FirmwareError, stage_sections

DEFAULT_EXTRACT = Path("extract")
DEFAULT_OUT = Path("out") / "updater"


def stock_image(args) -> Path:
    path = Path(args.img) if getattr(args, "img", None) else args.cab / updater.IMG
    if not path.exists():
        raise FirmwareError(f"{path} not found; run `nwe39x unpack NW-E390_V1_01.exe` first")
    return path


def pick_version(args, fw: Firmware) -> str:
    if args.version:
        updater.check_version(args.version)
        return args.version
    players = device.find_players()
    if len(players) != 1:
        raise FirmwareError(f"found {len(players)} connected players; plug one in or pass --version")
    p = players[0]
    version = updater.next_version(max(p.version, updater.firmware_version(fw)))
    print(f"player at {p.root} reports {p.version}; building {version}")
    return version


def cmd_unpack(args):
    cab = updater.unpack(Path(args.exe), args.out)
    print(f"unpacked to {cab}")


def cmd_info(args):
    fw = Firmware.load(stock_image(args))
    major, minor, rev = fw.header_version
    print(f"date {fw.date}  vendor {fw.vendor!r}  model {fw.model!r}")
    print(f"version: XML {updater.firmware_version(fw)}, header {major}.{minor:02d} (rev {rev})")
    print(f"payload {fw.size_field:#x} bytes, file {len(fw.buf):#x}, CRC {fw.stored_crc:#010x}")
    for name, blobs in fw.blobs.items():
        for b in blobs:
            if b.size:
                print(f"  {name}{b.index:<2} {b.offset:#09x}-{b.end:#09x}  {b.size:>9,} bytes")
    base, secs = stage_sections(fw.read(fw.blob("stage", 3)))
    print(f"stage3: base {base:#x}, {len(secs)} sections, {len({s.code_pa for s in secs})} run addresses")
    print(f"pictures: {len(imageres.pictures(fw))}")
    problems = fw.problems()
    print("checks: " + ("all pass (the player would accept this image)" if not problems else "; ".join(problems)))


def cmd_diff(args):
    """Name every region of a built image that differs from Sony's, so nothing changes by accident."""
    stock = Firmware.load(args.cab / updater.IMG)
    fw = Firmware.load(args.target)
    if len(fw.buf) != len(stock.buf):
        raise FirmwareError("images differ in size")
    regions = [(p.offset, p.offset + p.size, f"picture {p.index:03d}") for p in imageres.pictures(stock)]
    regions += [(t.offset, t.offset + strtbl.SLOT, f"string {t.lang}:{t.record} ({t.text!r})") for t in strtbl.texts(stock)]
    m = updater.VERSION_RE.search(bytes(stock.buf))
    regions += [(m.start(1), m.end(1), "firmware version (XML)"), (4, 8, "header version"),
                (stock.size_field + 4, stock.size_field + 8, "backup header version"),
                (len(stock.buf) - 4, len(stock.buf), "CRC")]
    f16, f12 = fonts.Font.font16(stock), fonts.Font.font12(stock)
    f12_glyph_cp = {v + 32: i + 0x20 for i, v in enumerate(f12.table) if v != 0xFFFF}
    f12_data = f12.blob_offset + 2 * len(f12.table)

    def glyph_at(i: int) -> tuple[str, int] | None:
        if f16.blob_offset <= i < f16.blob_offset + f16.blob_size:
            return "font16", (i - f16.blob_offset) // 33
        if f12_data <= i < f12.blob_offset + f12.blob_size:
            cp = f12_glyph_cp.get((i - f12_data) // 24)
            return ("font12", cp) if cp is not None else None
        return None

    hits, glyphs, unknown = {}, {}, []
    for i in (i for i in range(len(stock.buf)) if fw.buf[i] != stock.buf[i]):
        name = next((n for s, e, n in regions if s <= i < e), None)
        if name:
            hits[name] = hits.get(name, 0) + 1
        elif g := glyph_at(i):
            glyphs.setdefault(g[0], set()).add(g[1])
        else:
            unknown.append(i)
    for name, n in hits.items():
        print(f"  {name}: {n} bytes")
    for font, cps in glyphs.items():
        print(f"  {font}: {len(cps)} glyphs, U+{min(cps):04X}..U+{max(cps):04X}")
    if unknown:
        print(f"  UNEXPECTED: {len(unknown)} bytes outside known regions, first at {unknown[0]:#x}")
    print("checks: " + ("pass" if not fw.problems() else "; ".join(fw.problems())))
    if unknown:
        sys.exit(1)


def cmd_blobs(args):
    fw = Firmware.load(stock_image(args))
    out = Path(args.dir)
    out.mkdir(parents=True, exist_ok=True)
    for blobs in fw.blobs.values():
        for b in blobs:
            if b.size:
                (out / f"{b.table}{b.index}.bin").write_bytes(fw.read(b))
                print(f"  {b.table}{b.index}.bin  {b.size:,} bytes")


def cmd_images_export(args):
    fw = Firmware.load(stock_image(args))
    n = imageres.export(fw, Path(args.dir), Path(args.dir) / "_contact_sheet.png" if args.sheet else None)
    print(f"exported {n} pictures to {args.dir}")


def cmd_bootscreen(args):
    focus = tuple(float(v) for v in args.focus.split(","))
    img = bootscreen.make(Path(args.photo), args.caption.split("|") if args.caption else [], focus, args.zoom)
    img.save(args.out)
    if args.preview:
        img.resize((bootscreen.W * 3, bootscreen.H * 3), resample=0).save(args.preview)
    print(f"wrote {args.out} (the boot screen is picture {bootscreen.BOOT_PICTURE:03d}, power off is 083)")


def cmd_strings_export(args):
    fw = Firmware.load(stock_image(args))
    strtbl.export(fw, Path(args.file), args.lang)
    print(f"wrote {args.file}")


def cmd_fonts_export(args):
    fw = Firmware.load(stock_image(args))
    n = fonts.export_sheet(fonts.Font.by_name(fw, args.font), fonts.parse_range(args.range), Path(args.out))
    print(f"wrote {n} glyphs to {args.out}; edit them (white = ink) and put the file in your mod's fonts/ folder")


def cmd_fonts_from_ttf(args):
    fw = Firmware.load(stock_image(args))
    font = fonts.Font.by_name(fw, args.font)
    n = fonts.sheet_from_ttf(font, Path(args.ttf), fonts.parse_range(args.range), Path(args.out), args.size)
    print(f"wrote {n} glyphs from {Path(args.ttf).name} to {args.out}")


def cmd_fonts_preview(args):
    fw = Firmware.load(stock_image(args))
    fonts.preview(fonts.Font.by_name(fw, args.font), args.text).save(args.out)
    print(f"wrote {args.out}")


def cmd_build(args):
    fw = Firmware.load(stock_image(args))
    images, strings, font_dir = args.images, args.strings, args.fonts
    if args.mod:
        mod = Path(args.mod)
        images = images or (mod / "images" if (mod / "images").is_dir() else None)
        strings = strings or (mod / "strings.tsv" if (mod / "strings.tsv").is_file() else None)
        font_dir = font_dir or (mod / "fonts" if (mod / "fonts").is_dir() else None)
    pics = imageres.import_dir(fw, Path(images)) if images else []
    texts = strtbl.import_tsv(fw, Path(strings)) if strings else []
    glyphs = [cp for sheet in sorted(Path(font_dir).glob("*.png")) for cp in fonts.import_sheet(fw, sheet)] if font_dir else []
    if not pics and not texts and not glyphs:
        raise FirmwareError("nothing to change; give --mod, --images, --strings or --fonts (or use `restore`)")
    if pics:
        print(f"pictures replaced: {', '.join(map(str, pics))}")
    if texts:
        print(f"strings changed: {', '.join(f'{lang}:{r}' for lang, r in texts)}")
    if glyphs:
        print(f"glyphs changed: {len(glyphs)}")
    _write(args, fw)


def cmd_restore(args):
    _write(args, Firmware.load(stock_image(args)))


FLASH_TIPS = """\
Before running it: close File Explorer windows and apps showing the player, and leave the drive
alone until the tool's window closes (other programs reading the drive make it fail before copying).
If Sony's tool says "failed ... unknown error", check `nwe39x status` before retrying: the player
reports the new version if the install worked."""


def _write(args, fw: Firmware):
    version = pick_version(args, fw)
    exe = updater.build(args.cab, fw, version, args.out)
    print(f"ready: run {exe} with the player connected (installs as {version})")
    print(FLASH_TIPS)


def cmd_status(args):
    players = device.find_players()
    if not players:
        print("no NW-E390-series player found (is it plugged in and unlocked?)")
    for p in players:
        print(f"{p.root}  firmware {p.version}")


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(prog="nwe39x", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("unpack", help="unpack Sony's updater .exe")
    p.add_argument("exe")
    p.add_argument("-o", "--out", type=Path, default=DEFAULT_EXTRACT)
    p.set_defaults(func=cmd_unpack)

    def image_args(p):
        p.add_argument("--cab", type=Path, default=DEFAULT_EXTRACT / "cab", help="unpacked updater folder")
        p.add_argument("--img", help="use this RKNANOFW.IMG instead of the stock one in --cab")

    p = sub.add_parser("info", help="describe a firmware image")
    image_args(p)
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("status", help="show connected players and their firmware version")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("diff", help="list what a built image changes compared with Sony's")
    p.add_argument("target", help="built RKNANOFW.IMG, e.g. out/updater/Data/Device/RKNANOFW.IMG")
    p.add_argument("--cab", type=Path, default=DEFAULT_EXTRACT / "cab", help="unpacked updater folder")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("blobs", help="write every resource (stage3 = the OS, fonts, strings, images) to DIR")
    p.add_argument("dir")
    image_args(p)
    p.set_defaults(func=cmd_blobs)

    images = sub.add_parser("images", help="UI pictures").add_subparsers(dest="images_cmd", required=True)
    p = images.add_parser("export", help="write every picture as PNG")
    p.add_argument("dir")
    p.add_argument("--sheet", action="store_true", help="also write _contact_sheet.png")
    image_args(p)
    p.set_defaults(func=cmd_images_export)

    strings = sub.add_parser("strings", help="UI text").add_subparsers(dest="strings_cmd", required=True)
    p = strings.add_parser("export", help="write every string as lang<TAB>record<TAB>text")
    p.add_argument("file")
    p.add_argument("--lang", choices=strtbl.LANGS, help="only this language")
    image_args(p)
    p.set_defaults(func=cmd_strings_export)

    fnt = sub.add_parser("fonts", help="bitmap fonts").add_subparsers(dest="fonts_cmd", required=True)
    p = fnt.add_parser("export", help="write a glyph sheet PNG for a range of characters")
    p.add_argument("out")
    p.add_argument("--font", default="16", help="16 (font1, 16x16) or 12 (font0, 12x12)")
    p.add_argument("--range", default="ascii", help=f"{', '.join(fonts.RANGES)} or U+XXXX-U+YYYY")
    image_args(p)
    p.set_defaults(func=cmd_fonts_export)
    p = fnt.add_parser("from-ttf", help="render a TrueType font into a glyph sheet")
    p.add_argument("ttf")
    p.add_argument("out")
    p.add_argument("--font", default="16", help="16 or 12")
    p.add_argument("--range", default="ascii")
    p.add_argument("--size", type=int, help="pixel size (default: cell size - 3)")
    image_args(p)
    p.set_defaults(func=cmd_fonts_from_ttf)
    p = fnt.add_parser("preview", help="render text with the firmware's glyphs")
    p.add_argument("text", help='a backslash starts a new line')
    p.add_argument("out")
    p.add_argument("--font", default="16")
    image_args(p)
    p.set_defaults(func=cmd_fonts_preview)

    p = sub.add_parser("bootscreen", help="make a 128x160 boot picture from a photo")
    p.add_argument("photo")
    p.add_argument("out")
    p.add_argument("--caption", default="", help='lines separated by "|"')
    p.add_argument("--focus", default="0.5,0.5", help="centre of the crop as fractions, e.g. 0.55,0.45")
    p.add_argument("--zoom", type=float, default=1.0)
    p.add_argument("--preview", help="also write a 3x enlarged preview PNG")
    p.set_defaults(func=cmd_bootscreen)

    for name, func, helptext in (("build", cmd_build, "build a patched updater"),
                                 ("restore", cmd_restore, "build Sony's stock firmware with a newer version")):
        p = sub.add_parser(name, help=helptext)
        image_args(p)
        if name == "build":
            p.add_argument("--mod", help="mod folder with images/ and/or strings.tsv")
            p.add_argument("--images", help="folder of NNN.png / NNN_*.png pictures to swap in")
            p.add_argument("--strings", help="TSV of lang<TAB>record<TAB>text lines")
            p.add_argument("--fonts", help="folder of glyph sheets from `nwe39x fonts export`")
        p.add_argument("--version", help="version to install as, e.g. 1.03 (default: one above the player's)")
        p.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
        p.set_defaults(func=func)

    args = ap.parse_args(argv)
    try:
        args.func(args)
    except FirmwareError as e:
        sys.exit(f"error: {e}")
