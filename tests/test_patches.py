import pytest

from nwe39x import patches
from nwe39x.rknanofw import Firmware, FirmwareError

# The synthetic image's one stage-3 section runs at 0x0306C000; its body starts with 16 zero bytes.
SEC_PA = 0x0306C000


def test_thumb_b_encodings():
    # The two branches in mods/volume-limit, checked by hand against the Thumb encoding.
    assert patches.thumb_b(0x3064B94, 0x3064BAA) == bytes.fromhex("09e0")
    assert patches.thumb_b(0x306EA9A, 0x306EAAE) == bytes.fromhex("08e0")
    assert patches.thumb_b(0x1000, 0x1004) == bytes.fromhex("00e0")
    assert patches.thumb_b(0x1000, 0x1000) == bytes.fromhex("fee7")  # branch to self
    with pytest.raises(FirmwareError):
        patches.thumb_b(0x1000, 0x1001)
    with pytest.raises(FirmwareError):
        patches.thumb_b(0x1000, 0x2000)


def test_parse_tsv(tmp_path):
    f = tmp_path / "p.tsv"
    f.write_text("# c\n0\t3064b94\t49 b9\t09e0\tnote here\n\n10\t306ea9a\t40b9\t08e0\n")
    ps = patches.parse_tsv(f)
    assert [(p.section, p.addr, p.old, p.new, p.note) for p in ps] == [
        (0, 0x3064B94, b"\x49\xb9", b"\x09\xe0", "note here"),
        (10, 0x306EA9A, b"\x40\xb9", b"\x08\xe0", ""),
    ]
    f.write_text("0\t3064b94\t49b9\t09\n")
    with pytest.raises(FirmwareError):
        patches.parse_tsv(f)


def test_apply_checks_old_bytes_and_changes_only_them(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    off = patches.code_offset(fw, 0, SEC_PA + 4, 2)
    assert bytes(fw.buf[off:off + 2]) == b"\0\0"
    patches.apply(fw, [patches.Patch(0, SEC_PA + 4, b"\0\0", b"\x01\x02")])
    changed = [i for i in range(len(image_bytes)) if fw.buf[i] != image_bytes[i]]
    assert changed == [off, off + 1]
    with pytest.raises(FirmwareError, match="not"):
        patches.apply(Firmware.from_bytes(image_bytes), [patches.Patch(0, SEC_PA + 4, b"\x55\x55", b"\0\0")])


def test_apply_is_all_or_nothing(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    with pytest.raises(FirmwareError):
        patches.apply(fw, [patches.Patch(0, SEC_PA, b"\0", b"\x01"), patches.Patch(0, SEC_PA + 1, b"\x77", b"\0")])
    assert bytes(fw.buf) == image_bytes


def test_addresses_outside_the_section_are_rejected(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    with pytest.raises(FirmwareError):
        patches.code_offset(fw, 0, SEC_PA - 2, 2)
    with pytest.raises(FirmwareError):
        patches.code_offset(fw, 0, SEC_PA + 0x10000, 2)
    with pytest.raises(FirmwareError):
        patches.code_offset(fw, 7, SEC_PA, 2)


def test_file_offsets_outside_the_payload_are_rejected(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    with pytest.raises(FirmwareError):
        patches.code_offset(fw, patches.FILE, 0x10, 1)  # header
    with pytest.raises(FirmwareError):
        patches.code_offset(fw, patches.FILE, fw.size_field, 1)  # backup header
    with pytest.raises(FirmwareError):
        patches.code_offset(fw, patches.FILE, fw.size_field - 1, 2)  # straddles the end
    assert patches.code_offset(fw, patches.FILE, fw.size_field - 1, 1) == fw.size_field - 1


def test_apply_stays_all_or_nothing_past_the_payload(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    tail = fw.size_field + 0x100  # inside the file, past the payload
    bad = patches.Patch(patches.FILE, tail, bytes(fw.buf[tail:tail + 1]), b"\x55")
    with pytest.raises(FirmwareError):
        patches.apply(fw, [patches.Patch(0, SEC_PA, b"\0", b"\x01"), bad])
    assert bytes(fw.buf) == image_bytes
