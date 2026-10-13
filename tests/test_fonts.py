import pytest
from PIL import Image

from nwe39x import fonts
from nwe39x.rknanofw import Firmware, FirmwareError


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
    rows = f.rows(ord("A"))  # glyph = table[0x21] + 32 = 65
    assert rows[0] == 0x8000 >> (65 % 12)


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
    for f in (f16, f12):
        fonts.export_sheet(f, fonts.parse_range("ascii") + fonts.parse_range("cyrillic"), tmp_path / f"{f.name}.png")
        assert fonts.import_sheet(fw, tmp_path / f"{f.name}.png") == []
    assert bytes(fw.buf) == stock_bytes
