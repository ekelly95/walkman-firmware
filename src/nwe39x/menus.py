"""The home menu, as a table in stage 3 you can rewrite.

The home screen (section 17) is a carousel over a table at its data address 0x302302c: six
entries of {u16 id, u16 icon, u16 string}. `id` names the entry, `icon` is the picture drawn
(icon + 1 is its highlighted twin), `string` is the label. OK dispatches on the cursor slot
through a jump table in id order, so hiding an entry reorders that table too. The entry count 6 is hard-coded in the cursor wrap-around and the draw loop (eight 16-bit
instructions), so hiding an entry rewrites the table and patches those constants to the new
count. Everything is expressed as patches.tsv lines for `build --patches`.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from . import imageres, patches, strtbl
from .rknanofw import Firmware, FirmwareError

SECTION = 17
TABLE = 0x302302C
COUNT = 6
ENTRY = 6  # bytes
# The icons form a 3x2 grid; entry i's icon pair (icon, icon+1) carries slot i's position in its picture entry.
SLOTS = [(6, 33), (46, 33), (86, 33), (6, 78), (46, 78), (86, 78)]

# (run address, kind): Thumb-1 encodings that carry the entry count N or its wrap value N-1.
#   adds r0, r0, #N   0x1C00 | N << 6       subs r0, r0, #N   0x1E00 | N << 6
#   cmp r0, #K        0x2800 | K            cmp r4, #K        0x2C00 | K      movs r0, #K  0x2000 | K
COUNT_SITES = [
    (0x306C882, "adds", 0), (0x306C896, "cmp0", -1), (0x306C8A4, "cmp0", -1), (0x306C8A8, "subs", 0),
    (0x306C8BC, "mov0", -1), (0x306C8C4, "cmp0", -1), (0x306C8CE, "cmp0", -1), (0x306C922, "cmp4", 0),
]
# OK on the home screen dispatches on the cursor slot, not the entry id: `tbb [pc, slot]` at
# 0x306C594 over this 6-byte table of handlers in id order (0x306C600, slot 3, opens Settings).
DISPATCH = 0x306C598
# Apps return to the home screen with the entry id to highlight; on entry it stores that byte as
# the cursor slot (`ldrb r0, [r5]; ldr r1, =0x3023050; strb r0, [r1]` at RECEIVE). When entries
# are hidden, those 4 bytes become a `bl` to a helper that maps id -> slot, placed in a hidden
# entry's handler (dead once the dispatch table no longer points at it).
RECEIVE = 0x306C4B6
CURSOR = 0x3023050
CAVES = {2: (0x306C5D8, 40)}  # id -> (handler address, bytes up to the next handler)


def thumb_bl(from_addr: int, to_addr: int) -> bytes:
    off = to_addr - (from_addr + 4)
    if off & 1 or not -(1 << 24) <= off < (1 << 24):
        raise FirmwareError(f"bl from {from_addr:#x} to {to_addr:#x} is out of range")
    s = (off >> 24) & 1
    i1, i2 = (off >> 23) & 1, (off >> 22) & 1
    j1, j2 = (1 - i1) ^ s, (1 - i2) ^ s
    hw1 = 0xF000 | s << 10 | (off >> 12) & 0x3FF
    hw2 = 0xD000 | j1 << 13 | j2 << 11 | (off >> 1) & 0x7FF
    return struct.pack("<2H", hw1, hw2)


def cursor_helper(at: int, slots: bytes) -> bytes:
    """Thumb code for `r0 = slots[byte [r5]] if < 6 else byte [r5]; r1 = &cursor; return`,
    with its 6-byte table and the literal, 28 bytes. `at` must be 4-aligned."""
    assert at % 4 == 0 and len(slots) == COUNT
    code = struct.pack("<7H",
                       0x7828,  # ldrb r0, [r5]
                       0x2800 | COUNT,  # cmp r0, #6
                       0xD201,  # bhs +2 (to the ldr)
                       0xA102,  # adr r1, table (at+16)
                       0x5C08,  # ldrb r0, [r1, r0]
                       0x4903,  # ldr r1, [pc, #12] (the literal at at+24)
                       0x4770)  # bx lr
    return code + b"\x00\xbf" + slots + b"\x00\x00" + struct.pack("<I", CURSOR)


def _read(fw: Firmware, section: int, addr: int, size: int) -> bytes:
    off = patches.code_offset(fw, section, addr, size)
    return bytes(fw.buf[off:off + size])


def _encode(kind: str, value: int) -> bytes:
    op = {"adds": 0x1C00 | value << 6, "subs": 0x1E00 | value << 6, "cmp0": 0x2800 | value,
          "cmp4": 0x2C00 | value, "mov0": 0x2000 | value}[kind]
    return op.to_bytes(2, "little")


@dataclass
class Entry:
    id: int
    icon: int
    string: int
    label: str

    def pack(self) -> bytes:
        return struct.pack("<3H", self.id, self.icon, self.string)


def home_menu(fw: Firmware) -> list[Entry]:
    off = patches.code_offset(fw, SECTION, TABLE, COUNT * ENTRY)
    labels = {t.record: t.text for t in strtbl.texts(fw, "en")}
    out = []
    for i in range(COUNT):
        ident, icon, string = struct.unpack_from("<3H", fw.buf, off + i * ENTRY)
        out.append(Entry(ident, icon, string, labels.get(string, "?")))
    return out


def hide(fw: Firmware, names: list[str]) -> list[patches.Patch]:
    """Patches that drop the named entries (matched case-insensitively against their labels)
    from the home menu and fix the count. Returns an empty list if nothing matched."""
    entries = home_menu(fw)
    keep = [e for e in entries if not any(n.lower() in e.label.lower() for n in names)]
    missing = [n for n in names if not any(n.lower() in e.label.lower() for e in entries)]
    if missing:
        raise FirmwareError(f"no home menu entry matches {', '.join(missing)}; entries are "
                            + ", ".join(e.label for e in entries))
    if len(keep) == len(entries):
        return []
    if len(keep) < 2:
        raise FirmwareError("the home menu needs at least two entries")
    n = len(keep)
    new_table = b"".join(e.pack() for e in keep) + keep[-1].pack() * (COUNT - n)  # tail never shown
    old_table = b"".join(e.pack() for e in entries)
    out = [patches.Patch(SECTION, TABLE, old_table, new_table,
                         "home menu: " + ", ".join(e.label for e in keep))]
    old_jumps = _read(fw, SECTION, DISPATCH, COUNT)
    new_jumps = bytes(old_jumps[e.id] for e in keep) + bytes([old_jumps[keep[-1].id]]) * (COUNT - n)
    out.append(patches.Patch(SECTION, DISPATCH, old_jumps, new_jumps, "home menu: OK dispatch follows the kept entries"))
    kept_ids = [e.id for e in keep]
    cave = next((CAVES[e.id] for e in entries if e.id not in kept_ids and e.id in CAVES), None)
    if cave:
        at, size = cave
        slots = bytes(kept_ids.index(i) if i in kept_ids else min(i, n - 1) for i in range(COUNT))
        helper = cursor_helper(at, slots)
        assert len(helper) <= size
        out.append(patches.Patch(SECTION, at, _read(fw, SECTION, at, len(helper)), helper,
                                 "home menu: id -> slot helper for the returning cursor"))
        out.append(patches.Patch(SECTION, RECEIVE, _read(fw, SECTION, RECEIVE, 4), thumb_bl(RECEIVE, at),
                                 "home menu: returning cursor goes through the helper"))
    else:
        print("note: no free handler for the cursor helper; returning to the home menu may highlight the wrong slot")
    for addr, kind, delta in COUNT_SITES:
        out.append(patches.Patch(SECTION, addr, _encode(kind, COUNT + delta), _encode(kind, n + delta),
                                 f"home menu count {COUNT}->{n} ({kind})"))
    pics = imageres.pictures(fw)
    table = fw.blob("imageres").offset + 0x20
    for slot, e in enumerate(keep):
        for icon in (e.icon, e.icon + 1):
            p = pics[icon]
            if (p.x, p.y) != SLOTS[slot]:
                out.append(patches.Patch(patches.FILE, table + 16 * icon + 4, struct.pack("<2H", p.x, p.y),
                                         struct.pack("<2H", *SLOTS[slot]), f"icon {icon} ({e.label}) to slot {slot}"))
    return out


# The Settings menu is a tree in the string table's record headers (see strtbl.py), rooted here.
SETTINGS = 110


def settings_menu(fw: Firmware) -> dict[int, strtbl.Node]:
    nodes = strtbl.tree(fw)
    if SETTINGS not in nodes or not nodes[SETTINGS].children:
        raise FirmwareError(f"record {SETTINGS} is not the Settings menu in this image")
    return nodes


def walk(nodes: dict[int, strtbl.Node], record: int = SETTINGS, depth: int = 0):
    """(depth, node) for the subtree at `record`, in menu order."""
    yield depth, nodes[record]
    for c in nodes[record].children:
        yield from walk(nodes, c, depth + 1)


def hide_settings(fw: Firmware, names: list[str]) -> list[patches.Patch]:
    """Patches that drop the named submenus (matched case-insensitively against their labels)
    from the Settings menu. Options (leaves with a value) cannot be hidden: their row is the
    setting's value. The hidden records stay in the table, unreachable."""
    nodes = settings_menu(fw)
    subs = [n for _, n in walk(nodes) if n.record != SETTINGS and n.value is None]
    targets = []
    for name in names:
        hits = [n for n in subs if name.lower() in n.label.lower()]
        if len(hits) != 1:
            raise FirmwareError(f"{name!r} matches {', '.join(n.label for n in hits) or 'no submenu'}; "
                                "submenus are " + ", ".join(n.label for n in subs))
        targets.append(hits[0])

    edited: dict[int, strtbl.Node] = {}

    def get(r: int) -> strtbl.Node:
        return edited.get(r, nodes[r])

    def edit(r: int) -> strtbl.Node:
        if r not in edited:
            n = nodes[r]
            edited[r] = strtbl.Node(**{**n.__dict__, "children": list(n.children)})
        return edited[r]

    hidden: set[int] = set()
    for t in targets:
        if t.record in hidden:
            continue
        hidden |= {n.record for _, n in walk(nodes, t.record)}
        parent = edit(t.parent)
        if len(parent.children) < 2:
            raise FirmwareError(f"{parent.label} needs at least one entry")
        parent.children.remove(t.record)
        parent.count, parent.first_child = len(parent.children), parent.children[0]
        for i, c in enumerate(parent.children):
            if get(c).index != i:
                edit(c).index = i
        t = get(t.record)  # earlier splices may have moved its links
        if t.prev is not None and get(t.prev).next == t.record:
            edit(t.prev).next = t.next
        if t.next is not None and get(t.next).prev == t.record:
            edit(t.next).prev = t.prev

    for r in list(edited):  # nothing still shown may point at a hidden record
        if r in hidden:
            del edited[r]
    view = {**nodes, **edited}
    for _, n in walk(view):
        links = [n.parent, n.first_child, n.prev, n.next, *n.children]
        if any(x in hidden for x in links if x is not None):
            raise FirmwareError(f"record {n.record} ({n.label}) still links to a hidden record")
    return strtbl.header_patches(fw, sorted(edited.values(), key=lambda n: n.record), "settings menu: ")


def write_tsv(path: Path, plist: list[patches.Patch], header: str):
    lines = [f"# {header}", "# section\trun address\told\tnew\tnote"]
    lines += [f"{'file' if p.section == patches.FILE else p.section}\t{p.addr:x}\t{p.old.hex()}\t{p.new.hex()}\t{p.note}" for p in plist]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
