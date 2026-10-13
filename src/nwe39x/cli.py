"""nwe39x: mod the firmware of Sony's NW-E393/E394/E395 Walkman.

  nwe39x unpack NW-E390_V1_01.exe          unpack Sony's updater into extract/
  nwe39x status                            connected players and the version they report
  nwe39x info                              header, resources, checks
  nwe39x diff BUILT.IMG                    what a build changes compared with Sony's image
  nwe39x blobs DIR                         raw resources (stage3.bin is the OS, for Ghidra)
  nwe39x images export DIR                 every UI picture as PNG (+ contact sheet)
  nwe39x strings export FILE.tsv           every UI string, all 13 languages
  nwe39x fonts export SHEET.png            glyph sheet (--font 16|12|12zh, --range ascii|cyrillic|kana|cjk|...)
  nwe39x fonts preview "text" OUT.png      render text with the firmware's own glyphs
  nwe39x fonts from-bdf FONT.bdf OUT.png   glyph sheet from a BDF bitmap font (--font 12|16, --advance)
  nwe39x bootscreen PHOTO OUT.png          make a 128x160 boot picture from a photo
  nwe39x menu show                         the home menu's entries (id, icon, label)
  nwe39x menu hide NAME... -o FILE.tsv     patches that drop entries from the home menu
  nwe39x menu settings                     the Settings menu tree (from the string table)
  nwe39x menu settings-hide NAME... -o F   patches that drop submenus from Settings
  nwe39x theme NAME DIR                    recolour every UI picture into DIR (presets: mono, ice, purple,
                                           amber, ... ; or hue --hue DEG; --sheet PNG for a preview)
  nwe39x build --mod DIR                   patched updater in out/updater from DIR's mod.toml (includes,
                                           theme, images, fonts, strings, patches); version from the player
  nwe39x restore                           Sony's stock firmware, re-versioned so it installs over a mod
                                           (out/stock-restore; flash refuses until it exists)
  nwe39x flash [IMG]                       install a built image directly (copy + START FW UPDATE over SCSI);
                                           OS byte patches need --allow-code-patches
  nwe39x devinfo                           the DEVINFO block the player returns over SCSI
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import bootscreen, device, flash, fonts, imageres, menus, modspec, patches, strtbl, themes, updater, verify
from .rknanofw import Firmware, FirmwareError, stage_sections

DEFAULT_EXTRACT = Path("extract")
DEFAULT_OUT = Path("out") / "updater"
DEFAULT_RESTORE = Path("out") / "stock-restore"


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
    patch_files = list(args.patches or [])
    if not patch_files and (manifest := verify.read_manifest(Path(args.target).parent.parent.parent)):
        patch_files = manifest["patches"]
    rep = verify.explain(stock, fw, patch_files)
    for line in rep.lines():
        print("  " + line)
    print("checks: " + ("pass" if not fw.problems() else "; ".join(fw.problems())))
    if not rep.ok:
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


def cmd_theme(args):
    fw = Firmware.load(stock_image(args))
    fn = themes.transform(args.theme, args.hue)
    skip = set() if args.artwork else themes.ARTWORK
    changed = themes.generate(fw, Path(args.dir), fn, skip, Path(args.sheet) if args.sheet else None)
    print(f"wrote {len(changed)} recoloured pictures to {args.dir}; build with --images {args.dir}")


def cmd_menu_show(args):
    fw = Firmware.load(stock_image(args))
    for i, e in enumerate(menus.home_menu(fw)):
        print(f"  {i}: id {e.id}  icon {e.icon:3d}  string {e.string:3d}  {e.label}")


def cmd_menu_hide(args):
    fw = Firmware.load(stock_image(args))
    plist = menus.hide(fw, args.names)
    if not plist:
        raise FirmwareError("nothing to hide")
    menus.write_tsv(Path(args.out), plist, "home menu without " + ", ".join(args.names) + " (nwe39x menu hide)")
    print(f"wrote {len(plist)} patches to {args.out}: {plist[0].note}")


def cmd_menu_settings(args):
    fw = Firmware.load(stock_image(args))
    nodes = menus.settings_menu(fw)
    sys.stdout.reconfigure(errors="replace")  # language names on a cp1252 console
    for depth, n in menus.walk(nodes):
        value = "" if n.value is None else f"  = {n.value}"
        print(f"  {'  ' * depth}{n.record:3d}  {n.label.replace(chr(92), ' ')}{value}")


def cmd_menu_settings_hide(args):
    fw = Firmware.load(stock_image(args))
    plist = menus.hide_settings(fw, args.names)
    if not plist:
        raise FirmwareError("nothing to hide")
    menus.write_tsv(Path(args.out), plist, "Settings menu without " + ", ".join(args.names) + " (nwe39x menu settings-hide)")
    print(f"wrote {len(plist)} patches to {args.out}")


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
    n = fonts.sheet_from_ttf(font, Path(args.ttf), fonts.parse_range(args.range), Path(args.out), args.size,
                             base=args.baseline, advance=args.advance)
    print(f"wrote {n} glyphs from {Path(args.ttf).name} to {args.out}")


def cmd_fonts_from_bdf(args):
    fw = Firmware.load(stock_image(args))
    font = fonts.Font.by_name(fw, args.font)
    advance = int(args.advance) if args.advance and args.advance.isdigit() else args.advance
    n, clipped = fonts.sheet_from_bdf(font, Path(args.bdf), fonts.parse_range(args.range), Path(args.out),
                                      base=args.baseline, advance=advance)
    print(f"wrote {n} glyphs from {Path(args.bdf).name} to {args.out}")
    if clipped:
        print(f"warning: {len(clipped)} glyphs do not fit the {font.size} px cell and were clipped: "
              + " ".join(chr(cp) for cp in clipped[:40]))


def cmd_fonts_preview(args):
    fw = Firmware.load(stock_image(args))
    fonts.preview(fonts.Font.by_name(fw, args.font), args.text).save(args.out)
    print(f"wrote {args.out}")


def cmd_build(args):
    fw = Firmware.load(stock_image(args))
    n, patch_files, mod = 0, [], None
    if args.mod:
        mod = modspec.load(Path(args.mod))
        print(mod.describe())
        n += modspec.apply(fw, mod)
        patch_files += mod.all_patch_files()
    extra = modspec.Mod(Path("."), "command line", images=[Path(d) for d in args.images or []],
                        fonts=[Path(args.fonts)] if args.fonts else [], strings=[Path(args.strings)] if args.strings else [],
                        patches=[Path(f) for f in args.patches or []])
    n += modspec.apply(fw, extra)
    patch_files += extra.patches
    if not n:
        raise FirmwareError("nothing to change; give --mod, --images, --strings, --fonts or --patches (or use `restore`)")
    version = _write(args, fw)
    verify.write_manifest(args.out, version, patch_files, mod.name if mod else None)


def cmd_restore(args):
    version = _write(args, Firmware.load(stock_image(args)))
    verify.write_manifest(args.out, version, [], "stock")


FLASH_TIPS = """\
Before running it: close File Explorer windows and apps showing the player, and leave the drive
alone until the tool's window closes (other programs reading the drive make it fail before copying).
If Sony's tool says "failed ... unknown error", check `nwe39x status` before retrying: the player
reports the new version if the install worked."""


def _write(args, fw: Firmware) -> str:
    version = pick_version(args, fw)
    updater.build(args.cab, fw, version, args.out)
    print(f"ready: `nwe39x flash --updater {args.out}` installs it as {version}")
    return version


def cmd_status(args):
    players = device.find_players()
    if not players:
        print("no NW-E390-series player found (is it plugged in and unlocked?)")
    for p in players:
        print(f"{p.root}  firmware {p.version}")


def one_player(args) -> device.Player:
    players = [device.read_player(Path(args.drive))] if args.drive else device.find_players()
    if len(players) != 1 or players[0] is None:
        raise FirmwareError(f"found {len([p for p in players if p])} connected players; plug one in or pass --drive")
    return players[0]


def cmd_devinfo(args):
    p = one_player(args)
    info = flash.devinfo(p.root)
    print(f"{p.root}  firmware {p.version}")
    print(f"DEVINFO: {info}")
    print(f"raw: {info.raw.hex()}")


def cmd_flash(args):
    """Every check runs before anything touches the player: the image is explained against Sony's,
    changes to the OS itself need --allow-code-patches, a stock-restore build must exist, and a
    person types "flash" (or passes --yes) after seeing what will be installed where."""
    img = Path(args.img) if args.img else args.updater / updater.IMG
    if not img.exists():
        raise FirmwareError(f"{img} not found; build it first or pass IMG")
    stock_path = args.cab / updater.IMG
    if not stock_path.exists():
        raise FirmwareError(f"{stock_path} not found to check the image against; run `nwe39x unpack` first")
    stock, built = Firmware.load(stock_path), Firmware.load(img)
    manifest = verify.read_manifest(img.parent.parent.parent)
    rep = verify.explain(stock, built, manifest["patches"] if manifest else [])
    for line in rep.lines():
        print("  " + line)
    if not args.force and rep.unknown:
        raise FirmwareError(f"{len(rep.unknown)} changed bytes are not explained by the build's manifest (first at "
                            f"{rep.unknown[0]:#x}); not flashing. Rebuild with `nwe39x build`, or look at `nwe39x diff`.")
    if not args.force and rep.mismatched:
        raise FirmwareError(f"{len(rep.mismatched)} bytes inside the manifest's patches are not the patches' new bytes "
                            f"(first at {rep.mismatched[0]:#x}); not flashing. Rebuild with `nwe39x build`.")
    if (os_bytes := verify.os_changes(stock, built)) and not args.allow_code_patches:
        in_os = set(os_bytes)
        names = sorted({n for f in (manifest["patches"] if manifest else [])
                        for s, e, n in patches.regions(stock, patches.parse_tsv(Path(f))) if in_os.intersection(range(s, e))})
        names = names or ["(no patch names them)"]
        raise FirmwareError(
            f"this image changes {len(os_bytes)} bytes of the OS itself (stage 3, first at {os_bytes[0]:#x}): "
            + "; ".join(names[:5]) + (f"; and {len(names) - 5} more" if len(names) > 5 else "")
            + ". Themes, fonts, strings and pictures never do; byte patches (volume-limit, menu hiding) do, and a "
            "wrong one can stop the player booting with no way back. Pass --allow-code-patches once you have checked them.")
    restore = args.restore / updater.IMG
    if restore.resolve() != img.resolve():
        if not restore.exists():
            raise FirmwareError(f"no stock-restore build at {args.restore}; make one first with "
                                f"`nwe39x restore -o {args.restore}`, so there is a way back while the player still boots")
        if not verify.is_stock(stock, Firmware.load(restore)):
            raise FirmwareError(f"{restore} is not Sony's stock image (other than its version); rebuild it with "
                                f"`nwe39x restore -o {args.restore}`")
    p = one_player(args)
    print(f"about to install {img} ({updater.firmware_version(built)}) on the player at {p.root} "
          f"(now {p.version}). There is no recovery if an install breaks the player.")
    if not args.yes:
        if not sys.stdin.isatty():
            raise FirmwareError("flash asks for a typed confirmation; run it in a terminal, or pass --yes")
        if input('type "flash" to install: ').strip() != "flash":
            raise FirmwareError("not confirmed; nothing was sent to the player")
    version = flash.flash(img, p.root, wait=not args.no_wait)
    if version:
        print(f"done: the player reports {version}")


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

    p = sub.add_parser("devinfo", help="ask the player for its DEVINFO block over SCSI (read-only)")
    p.add_argument("--drive", help="player's drive, e.g. D:/ (default: the one connected player)")
    p.set_defaults(func=cmd_devinfo)

    p = sub.add_parser("flash", help="install an image without Sony's tool: copy it to the player and send START FW UPDATE")
    p.add_argument("img", nargs="?", help="RKNANOFW.IMG to install (default: the one in --updater)")
    p.add_argument("--updater", type=Path, default=DEFAULT_OUT, help="build folder holding Data/Device/RKNANOFW.IMG")
    p.add_argument("--drive", help="player's drive, e.g. D:/")
    p.add_argument("--no-wait", action="store_true", help="return right after sending the command")
    p.add_argument("--force", action="store_true", help="flash even if the image changes bytes the build did not declare")
    p.add_argument("--allow-code-patches", action="store_true",
                   help="allow changes to the OS itself (byte patches such as volume-limit or menu hiding); themes, "
                        "fonts, strings and pictures never need it")
    p.add_argument("--restore", type=Path, default=DEFAULT_RESTORE,
                   help=f"stock-restore build that must exist first (default: {DEFAULT_RESTORE})")
    p.add_argument("--yes", action="store_true", help="skip the typed confirmation (only once a person has approved this flash)")
    p.add_argument("--cab", type=Path, default=DEFAULT_EXTRACT / "cab", help="unpacked updater folder (stock image to verify against)")
    p.set_defaults(func=cmd_flash)

    p = sub.add_parser("diff", help="list what a built image changes compared with Sony's")
    p.add_argument("target", help="built RKNANOFW.IMG, e.g. out/updater/Data/Device/RKNANOFW.IMG")
    p.add_argument("--cab", type=Path, default=DEFAULT_EXTRACT / "cab", help="unpacked updater folder")
    p.add_argument("--patches", action="append", help="patches.tsv the build used (repeatable), so its bytes are named rather than UNEXPECTED")
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
    p.add_argument("--font", default="16", help="16 (font1, 16x16), 12 (font0, 12x12) or 12zh (font0 with its Chinese-UI CJK bank)")
    p.add_argument("--range", default="ascii", help=f"{', '.join(fonts.RANGES)} or U+XXXX-U+YYYY")
    image_args(p)
    p.set_defaults(func=cmd_fonts_export)
    p = fnt.add_parser("from-ttf", help="render a TrueType font into a glyph sheet")
    p.add_argument("ttf")
    p.add_argument("out")
    p.add_argument("--font", default="16", help="16, 12 or 12zh")
    p.add_argument("--range", default="ascii")
    p.add_argument("--size", type=int, help="pixel size (default: cell size - 3)")
    p.add_argument("--baseline", type=int, help="baseline row (default: where the firmware's H sits; lower it for deeper descenders)")
    p.add_argument("--advance", type=int, help="advance width for every glyph, space included (monospace); default: rightmost ink + 1")
    image_args(p)
    p.set_defaults(func=cmd_fonts_from_ttf)
    p = fnt.add_parser("from-bdf", help="copy a BDF bitmap font into a glyph sheet")
    p.add_argument("bdf")
    p.add_argument("out")
    p.add_argument("--font", default="12", help="16, 12 or 12zh")
    p.add_argument("--range", default="ascii")
    p.add_argument("--baseline", type=int, help="baseline row (default: the BDF's ascent, if the font fits the cell)")
    p.add_argument("--advance", help="widths: the BDF's own (default), 'ink' for rightmost ink + 1, or N for all")
    image_args(p)
    p.set_defaults(func=cmd_fonts_from_bdf)
    p = fnt.add_parser("preview", help="render text with the firmware's glyphs")
    p.add_argument("text", help='a backslash starts a new line')
    p.add_argument("out")
    p.add_argument("--font", default="16")
    image_args(p)
    p.set_defaults(func=cmd_fonts_preview)

    menu = sub.add_parser("menu", help="the home and Settings menus").add_subparsers(dest="menu_cmd", required=True)
    p = menu.add_parser("show", help="list the home menu's entries")
    image_args(p)
    p.set_defaults(func=cmd_menu_show)
    p = menu.add_parser("hide", help="write patches that drop entries from the home menu")
    p.add_argument("names", nargs="+", help="labels to drop, e.g. FM Photos")
    p.add_argument("-o", "--out", required=True, help="patches.tsv to write (use it with build --patches)")
    image_args(p)
    p.set_defaults(func=cmd_menu_hide)
    p = menu.add_parser("settings", help="print the Settings menu tree")
    image_args(p)
    p.set_defaults(func=cmd_menu_settings)
    p = menu.add_parser("settings-hide", help="write patches that drop submenus from the Settings menu")
    p.add_argument("names", nargs="+", help='submenu labels to drop, e.g. "FM Radio"')
    p.add_argument("-o", "--out", required=True, help="patches.tsv to write (use it with build --patches)")
    image_args(p)
    p.set_defaults(func=cmd_menu_settings_hide)

    p = sub.add_parser("theme", help="recolour the UI pictures into a folder for `build --images`")
    p.add_argument("theme", choices=["hue", *themes.PRESETS], help="hue: rotate colours by --hue DEG; or a preset: "
                   + "; ".join(f"{k}: {v[0]}" for k, v in themes.PRESETS.items()))
    p.add_argument("dir")
    p.add_argument("--hue", type=float, help="degrees for the hue theme (gold is ~40; 200 ice blue, 290 purple)")
    p.add_argument("--sheet", help="also write a contact sheet PNG of the whole themed set")
    p.add_argument("--artwork", action="store_true", help="also recolour the boot and power-off pictures")
    image_args(p)
    p.set_defaults(func=cmd_theme)

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
            p.add_argument("--mod", help="mod folder: mod.toml (see modspec.py), or images/, fonts/, strings.tsv, patches.tsv")
            p.add_argument("--images", action="append", help="folder of NNN.png / NNN_*.png pictures to swap in (repeatable; later folders win)")
            p.add_argument("--strings", help="TSV of lang<TAB>record<TAB>text lines")
            p.add_argument("--fonts", help="folder of glyph sheets from `nwe39x fonts export`")
            p.add_argument("--patches", action="append", help="patches.tsv of code changes (repeatable)")
        p.add_argument("--version", help="version to install as, e.g. 1.03 (default: one above the player's)")
        p.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT if name == "build" else DEFAULT_RESTORE)
        p.set_defaults(func=func)

    args = ap.parse_args(argv)
    try:
        args.func(args)
    except FirmwareError as e:
        sys.exit(f"error: {e}")
