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
    assert len([p for p in plist if p.section == 17]) == 12  # table, dispatch, cursor helper + bl, 8 count sites
    assert len([p for p in plist if p.section == patches.FILE]) == 6  # 3 kept entries x icon pair
    patches.apply(fw, plist)
    assert [e.label for e in menus.home_menu(fw)][:5] == ["Photos", "Music", "Settings", "Playlists", "Go to song playback\\screen"]
    with pytest.raises(FirmwareError):
        menus.hide(Firmware.from_bytes(stock_bytes), ["Bluetooth"])


def test_thumb_bl():
    assert menus.thumb_bl(0x306C4B6, 0x306C5D8) == bytes.fromhex("00f08ff8")
    assert menus.thumb_bl(0x306C5D8, 0x306C4B6) == bytes.fromhex("fff76dff")


def test_cursor_helper_layout():
    code = menus.cursor_helper(0x306C5D8, bytes([0, 1, 2, 2, 3, 4]))
    assert len(code) == 28 and code[16:22] == bytes([0, 1, 2, 2, 3, 4])
    assert code[24:] == (0x3023050).to_bytes(4, "little")


def test_moved_icons_get_the_backdrop_of_their_new_slot(stock_bytes):
    from nwe39x import imageres
    fw = Firmware.from_bytes(stock_bytes)
    before = [(p.x, p.y) for p in imageres.pictures(fw)]
    patches.apply(fw, menus.hide(fw, ["FM"]))
    pics = imageres.pictures(fw)
    bd = pics[menus.BACKDROP]
    bg = imageres.decode(fw, bd).convert("RGB")

    def edge_error(i):  # mean RGB distance between an icon's border and the backdrop behind it
        p, img = pics[i], imageres.decode(fw, pics[i]).convert("RGB")
        pts = [(x, y) for x in range(p.width) for y in range(p.height) if x in (0, p.width - 1) or y in (0, p.height - 1)]
        return sum(sum(abs(a - b) for a, b in zip(img.getpixel(q), bg.getpixel((p.x - bd.x + q[0], p.y - bd.y + q[1]))))
                   for q in pts) / len(pts)

    moved = [p.index for p in pics if (p.x, p.y) != before[p.index]]
    assert len(moved) == 6  # Settings, Playlists, Go to song: icon and highlighted twin each
    assert max(edge_error(i) for i in moved) > 50  # the squares
    untouched = bytes(fw.buf)
    assert sorted(menus.rebase_moved_icons(fw, before)) == sorted(moved)
    assert max(edge_error(i) for i in moved) < 8
    others = [p for p in pics if p.index not in moved]
    assert all(fw.buf[p.offset:p.offset + p.size] == untouched[p.offset:p.offset + p.size] for p in others)
    assert menus.rebase_moved_icons(Firmware.from_bytes(stock_bytes), before) == []  # nothing moved, nothing done
