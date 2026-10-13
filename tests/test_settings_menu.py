import pytest

from nwe39x import menus, patches, strtbl
from nwe39x.rknanofw import Firmware, FirmwareError

TOP = [111, 128, 135, 142, 148, 167]


def test_node_roundtrip():
    raw = bytes.fromhex("6e00ffff00006f006d00ffffffff0600" + "6f008000870 08e009400a700".replace(" ", "")) + b"\xff\xff" * 7
    n = strtbl.Node.unpack(raw)
    assert (n.record, n.parent, n.first_child, n.prev, n.value, n.count) == (110, None, 111, 109, None, 6)
    assert n.children == TOP and n.pack() == raw


def test_stock_tree(stock_bytes):
    fw = Firmware.from_bytes(stock_bytes)
    nodes = menus.settings_menu(fw)
    assert nodes[110].children == TOP and nodes[110].label == "Settings"
    for _, n in menus.walk(nodes):
        assert n.count == len(n.children)
        for i, c in enumerate(n.children):
            assert nodes[c].parent == n.record and nodes[c].index == i
    for lang in strtbl.LANGS:  # the same tree in every language
        assert {r: n.pack() for r, n in strtbl.tree(fw, lang).items()} == {r: n.pack() for r, n in nodes.items()}


def test_hide_fm_settings(stock_bytes):
    fw = Firmware.from_bytes(stock_bytes)
    plist = menus.hide_settings(fw, ["FM Radio"])
    assert all(p.section == patches.FILE and len(p.old) == strtbl.HEAD for p in plist)
    assert len(plist) == 5 * len(strtbl.LANGS)  # 110, 128 (next), 142, 148, 167 (index; 142 prev)
    patches.apply(fw, plist)
    for lang in strtbl.LANGS:
        nodes = strtbl.tree(fw, lang)
        root = nodes[110]
        assert root.children == [111, 128, 142, 148, 167] and root.count == 5
        assert [nodes[c].index for c in root.children] == list(range(5))
        assert nodes[128].next == 142 and nodes[142].prev == 128


def test_hide_refusals(stock_bytes):
    fw = Firmware.from_bytes(stock_bytes)
    with pytest.raises(FirmwareError):
        menus.hide_settings(fw, ["Normal"])  # an option, not a submenu
    with pytest.raises(FirmwareError):
        menus.hide_settings(fw, ["Settings"])  # ambiguous
    with pytest.raises(FirmwareError):
        menus.hide_settings(fw, ["Bluetooth"])
    with pytest.raises(FirmwareError):
        menus.hide_settings(fw, ["Display", "Slide Show"])  # would empty Photo Settings
