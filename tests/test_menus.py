import pytest

from nwe39x import menus, patches
from nwe39x.rknanofw import Firmware, FirmwareError


def test_count_encodings():
    assert menus._encode("adds", 6) == bytes.fromhex("801d") and menus._encode("adds", 5) == bytes.fromhex("401d")
    assert menus._encode("subs", 6) == bytes.fromhex("801f")
    assert menus._encode("cmp0", 5) == bytes.fromhex("0528") and menus._encode("cmp4", 6) == bytes.fromhex("062c")
    assert menus._encode("mov0", 5) == bytes.fromhex("0520")


def test_file_patch_offsets(image_bytes):
    fw = Firmware.from_bytes(image_bytes)
    assert patches.code_offset(fw, patches.FILE, 0x400, 4) == 0x400
    with pytest.raises(FirmwareError):
        patches.code_offset(fw, patches.FILE, 0x10, 4)


def test_parse_file_section(tmp_path):
    f = tmp_path / "p.tsv"
    f.write_text("file\tb76c22\t06004e00\t56002100\tmove\n")
    (p,) = patches.parse_tsv(f)
    assert p.section == patches.FILE and p.addr == 0xB76C22


def test_stock_home_menu(stock_bytes):
    fw = Firmware.from_bytes(stock_bytes)
    entries = menus.home_menu(fw)
    assert [e.label for e in entries][:4] == ["Photos", "Music", "FM Radio", "Settings"]
    assert [e.id for e in entries] == list(range(6))
    plist = menus.hide(fw, ["FM"])
    assert plist[0].section == 17 and len(plist[0].old) == 36
    assert len([p for p in plist if p.section == 17]) == 9  # table + 8 count sites
    assert len([p for p in plist if p.section == patches.FILE]) == 6  # 3 kept entries x icon pair
    patches.apply(fw, plist)
    assert [e.label for e in menus.home_menu(fw)][:5] == ["Photos", "Music", "Settings", "Playlists", "Go to song playback\screen"]
    with pytest.raises(FirmwareError):
        menus.hide(Firmware.from_bytes(stock_bytes), ["Bluetooth"])
