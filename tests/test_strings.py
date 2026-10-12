import pytest

from nwe39x import strtbl
from nwe39x.rknanofw import Firmware, FirmwareError


def test_synthetic_strings_decode(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    en = strtbl.texts(fw, "en")
    assert [t.text for t in en] == ["L1 R0", "L1 R1", "L1 R2"]
    assert len(strtbl.texts(fw)) == 13 * 3


def test_export_import_roundtrip(image_bytes, tmp_path):
    fw = Firmware.from_bytes(image_bytes)
    strtbl.export(fw, tmp_path / "all.tsv")
    assert strtbl.import_tsv(fw, tmp_path / "all.tsv") == []
    assert bytes(fw.buf) == image_bytes


def test_set_text_changes_only_that_slot(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    target = strtbl.texts(fw, "en")[1]
    assert strtbl.set_text(fw, "en", 1, "Tunes\\for cats")
    assert strtbl.texts(fw, "en")[1].text == "Tunes\\for cats"
    assert strtbl.texts(fw, "de")[1].text == "L0 R1"
    diff = [i for i in range(len(image_bytes)) if fw.buf[i] != image_bytes[i]]
    assert target.offset <= diff[0] and diff[-1] < target.offset + strtbl.SLOT
    fw.fix_crc()
    assert fw.problems() == []


def test_limits(image_bytes, tmp_path):
    fw = Firmware.from_bytes(image_bytes)
    with pytest.raises(FirmwareError, match="limit is 99"):
        strtbl.set_text(fw, "en", 0, "x" * 100)
    with pytest.raises(FirmwareError, match="unknown language"):
        strtbl.set_text(fw, "xx", 0, "hi")
    with pytest.raises(FirmwareError, match="no record"):
        strtbl.set_text(fw, "en", 99, "hi")
    (tmp_path / "bad.tsv").write_text("en 1 missing tabs\n", encoding="utf-8")
    with pytest.raises(FirmwareError, match="bad.tsv:1"):
        strtbl.import_tsv(fw, tmp_path / "bad.tsv")


def test_tsv_comments_and_unicode(image_bytes, tmp_path):
    fw = Firmware.from_bytes(image_bytes)
    (tmp_path / "mod.tsv").write_text("# a comment\n\nen\t0\tMiau ♪\nja\t2\t猫\n", encoding="utf-8")
    assert strtbl.import_tsv(fw, tmp_path / "mod.tsv") == [("en", 0), ("ja", 2)]
    assert strtbl.texts(fw, "ja")[2].text == "猫"


def test_stock_strings(stock_bytes, tmp_path):
    fw = Firmware.from_bytes(stock_bytes)
    en = strtbl.texts(fw, "en")
    assert len(en) == 181 and en[11].text == "Music" and en[169].text == "English"
    assert strtbl.texts(fw, "ru")[3].text == "Отмена"
    strtbl.export(fw, tmp_path / "all.tsv")
    assert strtbl.import_tsv(fw, tmp_path / "all.tsv") == []
    assert bytes(fw.buf) == stock_bytes
