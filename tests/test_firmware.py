import struct

import pytest
from PIL import Image

from nwe39x import imageres, updater
from nwe39x.crc import rk_crc
from nwe39x.rknanofw import Firmware, FirmwareError, rc4


def test_crc_table_matches_rkboottool():
    from nwe39x.crc import TABLE
    assert TABLE[1] == 0x04C10DB7 and TABLE[2] == 0x09821B6E and TABLE[255] == 0xB1F880B4


def test_rc4_is_its_own_inverse():
    data = bytes(range(256)) * 3
    assert rc4(rc4(data)) == data and rc4(data) != data


def test_synthetic_image_passes_player_checks(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    assert fw.problems() == []
    assert fw.vendor == "Rockchip" and fw.model == "RKnano SDK 1.0" and fw.date == "2016-10-14"


def test_missing_magic_rejected(image_bytes):
    with pytest.raises(FirmwareError, match="magic"):
        Firmware.from_bytes(image_bytes[:0x1F8] + b"XXXXXXXX" + image_bytes[0x200:])


def test_wrong_file_size_detected(image_bytes):
    fw = Firmware.from_bytes(image_bytes[:-8] + image_bytes[-4:])
    assert any("requires" in p for p in fw.problems())


def test_backup_header_mismatch_detected(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    fw.buf[fw.size_field + 0x40] ^= 0xFF
    assert any("backup header" in p for p in fw.problems())


def test_write_refuses_header_and_tail(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    with pytest.raises(FirmwareError):
        fw.write(0x10, b"x")
    with pytest.raises(FirmwareError):
        fw.write(fw.size_field, b"x")


def test_picture_roundtrip_is_lossless(image_bytes, tmp_path):
    fw = Firmware.from_bytes(image_bytes)
    assert imageres.export(fw, tmp_path) == 2
    assert imageres.import_dir(fw, tmp_path) == []
    assert bytes(fw.buf) == image_bytes


def test_replace_picture_changes_only_its_pixels(image_bytes, tmp_path):
    fw = Firmware.from_bytes(image_bytes)
    pic = imageres.pictures(fw)[0]
    Image.new("RGB", (pic.width, pic.height), (255, 0, 0)).save(tmp_path / "000.png")
    assert imageres.import_dir(fw, tmp_path) == [0]
    fw.fix_crc()
    assert fw.problems() == []
    diff = [i for i in range(len(image_bytes) - 4) if fw.buf[i] != image_bytes[i]]
    assert diff and pic.offset <= diff[0] and diff[-1] < pic.offset + pic.size
    assert bytes(fw.buf[pic.offset:pic.offset + 2]) == b"\xf8\x00"  # red in RGB565 big-endian


def test_wrong_size_picture_rejected(image_bytes, tmp_path):
    fw = Firmware.from_bytes(image_bytes)
    Image.new("RGB", (9, 9)).save(tmp_path / "001_whatever.png")
    with pytest.raises(FirmwareError, match="2x2"):
        imageres.import_dir(fw, tmp_path)


def test_version_bump(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    assert updater.firmware_version(fw) == "1.01"
    updater.set_firmware_version(fw, "1.07")
    assert updater.firmware_version(fw) == "1.07"
    assert fw.header_version[:2] == (1, 7)
    assert fw.buf[4:8] == b"\x01\x00\x07\x00"
    fw.fix_crc()
    assert fw.problems() == []  # backup header updated too
    assert updater.next_version("1.09") == "1.10" and updater.next_version("1.99") == "2.00"
    with pytest.raises(FirmwareError):
        updater.set_firmware_version(fw, "1.100")


def test_build_writes_runnable_folder(image_bytes, tmp_path):
    cab = tmp_path / "cab"
    (cab / "Data" / "Device").mkdir(parents=True)
    (cab / "SoftwareUpdateTool.exe").write_bytes(b"MZ")
    (cab / updater.IMG).write_bytes(image_bytes)
    (cab / updater.SWUPDATE).write_text("<Common>\n<Version>1.01</Version>\n</Common>", encoding="iso-8859-1")
    out = tmp_path / "out"
    updater.build(cab, Firmware.from_bytes(image_bytes), "1.03", out)
    built = Firmware.load(out / updater.IMG)
    assert built.problems() == [] and updater.firmware_version(built) == "1.03"
    assert "<Version>1.03</Version>" in (out / updater.SWUPDATE).read_text(encoding="iso-8859-1")
    assert (cab / updater.IMG).read_bytes() == image_bytes  # Sony's copy untouched


def test_build_only_replaces_an_empty_folder_or_an_earlier_build(image_bytes, tmp_path):
    cab = tmp_path / "extract" / "cab"
    (cab / "Data" / "Device").mkdir(parents=True)
    (cab / "SoftwareUpdateTool.exe").write_bytes(b"MZ")
    (cab / updater.IMG).write_bytes(image_bytes)
    (cab / updater.SWUPDATE).write_text("<Common>\n<Version>1.01</Version>\n</Common>", encoding="iso-8859-1")
    fw = lambda: Firmware.from_bytes(image_bytes)
    out = tmp_path / "out"
    updater.build(cab, fw(), "1.02", out)
    updater.build(cab, fw(), "1.03", out)  # an earlier build is replaced
    assert updater.firmware_version(Firmware.load(out / updater.IMG)) == "1.03"
    (tmp_path / "empty").mkdir()
    updater.build(cab, fw(), "1.02", tmp_path / "empty")
    other = tmp_path / "notes"
    other.mkdir()
    (other / "keep.txt").write_text("mine")
    for target, msg in ((other, "not an earlier build"), (cab, "Sony's unpacked updater"),
                        (tmp_path / "extract", "Sony's unpacked updater"), (other / "keep.txt", "is a file")):
        with pytest.raises(FirmwareError, match=msg):
            updater.build(cab, fw(), "1.02", target)
    assert (other / "keep.txt").read_text() == "mine"
    assert (cab / updater.IMG).read_bytes() == image_bytes


def test_carve_cab_skips_false_headers():
    real = b"MSCF" + bytes(4) + struct.pack("<I", 40) + bytes(16) + struct.pack("<H", 3) + bytes(10)
    exe = b"MZ" + b"MSCF" + b"\xff" * 30 + real + b"tail"
    assert updater.carve_cab(exe) == real


# Against Sony's real image, when it has been unpacked locally.

def test_stock_image_checks(stock_bytes):
    fw = Firmware.from_bytes(stock_bytes)
    assert fw.problems() == []
    assert fw.stored_crc == 0xE3AE9225 == rk_crc(stock_bytes[:-4])
    assert updater.firmware_version(fw) == "1.01"
    assert fw.header_version == (1, 1, 10)
    assert len(imageres.pictures(fw)) == 234


def test_stock_pictures_roundtrip_byte_identical(stock_bytes, tmp_path):
    fw = Firmware.from_bytes(stock_bytes)
    imageres.export(fw, tmp_path)
    assert imageres.import_dir(fw, tmp_path) == []
    fw.fix_crc()
    assert bytes(fw.buf) == stock_bytes
