import json
from pathlib import Path

import pytest
from PIL import Image

from nwe39x import fonts
from nwe39x.rknanofw import Firmware, FirmwareError

REPO = Path(__file__).resolve().parent.parent
TTFS = [*sorted(REPO.glob("reference/terminus/*/TerminusTTF-*.ttf")), Path("C:/Windows/Fonts/consola.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")]


def test_font16_glyph_and_width(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    f = fonts.Font.font16(fw)
    assert f.has(ord("A")) and not f.has(0x4E00)  # synthetic font only has 0x80 glyphs
    assert f.width(ord("A")) == 9
    img = f.image(ord("A"))
    assert img.size == (16, 16) and img.getpixel((ord("A") % 8, 0)) == 255


def test_font12_table_lookup(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    f = fonts.Font.font12(fw)
    assert f.has(ord("A")) and not f.has(0x7F) and not f.has(0x10)
    rows = f.rows(ord("A"))  # glyph = table[0x21] = 33
    assert rows[0] == 0x8000 >> (33 % 12)
    assert f.width(ord("A")) == 33 % 12 + 1 and f.width(ord(" ")) == 5


def test_font12_import_writes_width(image_bytes, tmp_path):
    fw = Firmware.from_bytes(image_bytes)
    f = fonts.Font.font12(fw)
    img = Image.new("L", (12, 12), 0)
    for x in range(2, 8):
        img.putpixel((x, 4), 255)  # ink in columns 2-7
    assert f.set_image(ord("A"), img)
    assert f.width(ord("A")) == 8  # rightmost ink 7, plus 1
    diff = [i for i in range(len(image_bytes)) if fw.buf[i] != image_bytes[i]]
    off = f.offset(ord("A"))
    assert all(off <= i < off + 24 or i == f.widths_offset + 33 for i in diff)
    assert not f.set_image(ord(" "), Image.new("L", (12, 12), 0)) and f.width(ord(" ")) == 5


@pytest.mark.parametrize("name", ["16", "12"])
def test_sheet_roundtrip_is_lossless(image_bytes, tmp_path, name):
    fw = Firmware.from_bytes(image_bytes)
    f = fonts.Font.by_name(fw, name)
    assert fonts.export_sheet(f, fonts.parse_range("ascii"), tmp_path / "s.png") == 95
    assert fonts.import_sheet(fw, tmp_path / "s.png") == []
    assert bytes(fw.buf) == image_bytes


def test_edited_glyph_changes_only_that_record(image_bytes, tmp_path):
    fw = Firmware.from_bytes(image_bytes)
    f = fonts.Font.font16(fw)
    fonts.export_sheet(f, [ord("B")], tmp_path / "b.png")
    sheet = Image.open(tmp_path / "b.png")
    meta = sheet.text
    sheet = sheet.convert("L")
    for x in range(1, 11):
        sheet.putpixel((x, 5), 255)  # a bar across glyph x 0-9 (sheet has a 1 px grid)
    from PIL.PngImagePlugin import PngInfo
    info = PngInfo()
    info.add_text(fonts.META_KEY, meta[fonts.META_KEY])
    sheet.save(tmp_path / "b.png", pnginfo=info)
    assert fonts.import_sheet(fw, tmp_path / "b.png") == [ord("B")]
    off = f.offset(ord("B"))
    diff = [i for i in range(len(image_bytes)) if fw.buf[i] != image_bytes[i]]
    assert off <= diff[0] and diff[-1] < off + 33
    assert f.width(ord("B")) == 11  # recomputed: rightmost ink at x=9, plus 2 (was 9)
    fw.fix_crc()
    assert fw.problems() == []


def test_sheet_without_metadata_rejected(image_bytes, tmp_path):
    fw = Firmware.from_bytes(image_bytes)
    Image.new("L", (10, 10)).save(tmp_path / "plain.png")
    with pytest.raises(FirmwareError, match="metadata"):
        fonts.import_sheet(fw, tmp_path / "plain.png")


def test_parse_range():
    assert fonts.parse_range("U+0041-U+0043") == [0x41, 0x42, 0x43]
    assert fonts.parse_range("4e00") == [0x4E00]
    with pytest.raises(FirmwareError):
        fonts.parse_range("klingon")


def test_stock_fonts(stock_bytes, tmp_path):
    fw = Firmware.from_bytes(stock_bytes)
    f16, f12 = fonts.Font.font16(fw), fonts.Font.font12(fw)
    assert f16.has(0xAC00) and f16.has(0x4E00) and f16.width(ord("A")) == 8
    assert f12.has(ord("A")) and f12.has(0x0104) and f12.has(0x0410)
    assert f12.glyph_count == 424 and f12.widths_offset == 0x56054A and f12.width(ord("A")) == 7
    assert f12.rows(ord("A"))[0] == 0 and f12.rows(ord("A"))[11] == 0  # blank top and bottom rows
    for f in (f16, f12):
        fonts.export_sheet(f, fonts.parse_range("ascii") + fonts.parse_range("cyrillic"), tmp_path / f"{f.name}.png")
        assert fonts.import_sheet(fw, tmp_path / f"{f.name}.png") == []
    assert bytes(fw.buf) == stock_bytes


@pytest.mark.parametrize("name", ["16", "12"])
def test_advance_applies_to_every_glyph(image_bytes, tmp_path, name):
    fw = Firmware.from_bytes(image_bytes)
    f = fonts.Font.by_name(fw, name)
    ttf = next((t for t in TTFS if t.exists()), None)
    if ttf is None:
        pytest.skip("no TrueType font on this machine")
    cps = [ord(" "), ord("i"), ord("M")]
    fonts.sheet_from_ttf(f, ttf, cps, tmp_path / "m.png", advance=6)
    assert json.loads(Image.open(tmp_path / "m.png").text[fonts.META_KEY])["advance"] == 6
    fonts.import_sheet(fw, tmp_path / "m.png")
    assert [f.width(cp) for cp in cps] == [6, 6, 6]
    with pytest.raises(FirmwareError):
        fonts.sheet_from_ttf(f, ttf, cps, tmp_path / "x.png", advance=f.size + 1)


def test_advance_alone_rewrites_width(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    f = fonts.Font.font12(fw)
    img = f.image(ord("A"))
    assert not f.set_image(ord("A"), img)  # same rows, no advance: untouched
    assert f.set_image(ord("A"), img, advance=6) and f.width(ord("A")) == 6
    assert not f.set_image(ord("A"), img, advance=6)


BDF = """STARTFONT 2.1
FONT -test-tiny-medium-r-normal--8-80-75-75-c-50-iso10646-1
SIZE 8 75 75
FONTBOUNDINGBOX 5 8 0 -2
STARTPROPERTIES 4
FONT_ASCENT 6
FONT_DESCENT 2
CHARSET_REGISTRY "ISO10646"
CHARSET_ENCODING "1"
ENDPROPERTIES
CHARS 3
STARTCHAR A
ENCODING 65
SWIDTH 500 0
DWIDTH 5 0
BBX 3 3 1 0
BITMAP
40
A0
E0
ENDCHAR
STARTCHAR g
ENCODING 103
DWIDTH 4 0
BBX 2 3 0 -2
BITMAP
C0
40
C0
ENDCHAR
STARTCHAR unmapped
ENCODING -1
DWIDTH 4 0
BBX 1 1 0 0
BITMAP
80
ENDCHAR
ENDFONT
"""


def test_parse_bdf():
    bdf = fonts.parse_bdf(BDF)
    assert (bdf.ascent, bdf.descent) == (6, 2) and sorted(bdf.glyphs) == [65, 103]
    assert bdf.glyphs[65].bbx == (3, 3, 1, 0) and bdf.glyphs[65].rows == [0x40, 0xA0, 0xE0]
    with pytest.raises(FirmwareError, match="charset"):
        fonts.parse_bdf(BDF.replace('"ISO10646"', '"KOI8"').replace('"1"', '"R"'))


@pytest.mark.parametrize("advance, left, want", [(None, 0, 5), ("ink", 1, 5), (6, 0, 6)])
def test_sheet_from_bdf(image_bytes, tmp_path, advance, left, want):
    fw = Firmware.from_bytes(image_bytes)
    f = fonts.Font.font12(fw)
    (tmp_path / "t.bdf").write_text(BDF)
    n, clipped = fonts.sheet_from_bdf(f, tmp_path / "t.bdf", [65, 103, 0x2603], tmp_path / "t.png", advance=advance)
    assert n == 2 and clipped == []  # U+2603 is in neither font
    fonts.import_sheet(fw, tmp_path / "t.png")
    img = f.image(65)
    # baseline = ascent 6: the 3-row A sits on rows 3-5, x offset 1 (+1 more in ink mode)
    assert [img.getpixel((x + left, 3)) for x in range(4)] == [0, 0, 255, 0]
    assert [img.getpixel((x + left, 5)) for x in range(5)] == [0, 255, 255, 255, 0]
    assert f.width(65) == want
    g = f.image(103)
    assert g.getpixel((left, 5)) == 255 and g.getpixel((left + 1, 7)) == 255  # 2 below the baseline


def test_sheet_from_bdf_reports_clipping(image_bytes, tmp_path):
    fw = Firmware.from_bytes(image_bytes)
    (tmp_path / "t.bdf").write_text(BDF)
    _, clipped = fonts.sheet_from_bdf(fonts.Font.font12(fw), tmp_path / "t.bdf", [65, 103], tmp_path / "t.png", base=11)
    assert clipped == [103]  # g's descender falls below row 11


def test_stock_font12_cjk(stock_bytes, tmp_path):
    fw = Firmware.from_bytes(stock_bytes)
    f, zh = fonts.Font.font12(fw), fonts.Font.by_name(fw, "12zh")
    assert len([v for v in f.cjk if v]) == 31682
    for cp in (0x4E00, 0x3042, 0xAC00, 0xD55C, 0x2460, 0xFF01):
        assert f.has(cp) and f.is_cjk(cp) and f.width(cp) == 12
    assert f.width(0xFF71) == 6  # halfwidth katakana
    assert not f.is_cjk(ord("A")) and not f.is_cjk(0x0410)  # the Latin table wins where both have it
    assert f.rows(0x0410) == zh.rows(0x0410)
    assert f.rows(0x76F4) != zh.rows(0x76F4)  # 直: the banks differ in 7,262 glyphs
    assert f.offset(0x00A1) is not None and f.is_cjk(0x00A1) is False  # ¡ is in the Latin table
    for font in (f, zh):
        fonts.export_sheet(font, fonts.parse_range("kana"), tmp_path / f"{font.name}.png")
        assert fonts.import_sheet(fw, tmp_path / f"{font.name}.png") == []
    assert bytes(fw.buf) == stock_bytes


def test_cjk_import_writes_rows_only(stock_bytes):
    fw = Firmware.from_bytes(stock_bytes)
    f = fonts.Font.font12(fw)
    img = Image.new("L", (12, 12), 0)
    img.putpixel((3, 3), 255)
    assert f.set_image(0x3042, img, advance=5)
    off = f.offset(0x3042)
    diff = [i for i in range(len(stock_bytes)) if fw.buf[i] != stock_bytes[i]]
    assert diff and all(off <= i < off + 24 for i in diff) and f.width(0x3042) == 12


def test_synthetic_font12_has_no_cjk(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    assert fonts.Font.font12(fw).cjk == () and not fonts.Font.font12(fw).has(0x4E00)
    with pytest.raises(FirmwareError):
        fonts.Font.by_name(fw, "12zh")
