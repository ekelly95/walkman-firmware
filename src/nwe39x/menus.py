"""The home menu, as a table in stage 3 you can rewrite.

The home screen (section 17) is a carousel over a table at its data address 0x302302c: six
entries of {u16 id, u16 icon, u16 string}. `id` is what the firmware dispatches on when an entry
is chosen, `icon` is the picture drawn (icon + 1 is its highlighted twin), `string` is the label.
The entry count 6 is hard-coded in the cursor wrap-around and the draw loop (eight 16-bit
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


def write_tsv(path: Path, plist: list[patches.Patch], header: str):
    lines = [f"# {header}", "# section\trun address\told\tnew\tnote"]
    lines += [f"{'file' if p.section == patches.FILE else p.section}\t{p.addr:x}\t{p.old.hex()}\t{p.new.hex()}\t{p.note}" for p in plist]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
