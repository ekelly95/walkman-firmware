"""strtbl0, the firmware's UI text.

Layout (NW-E390 1.01): u16 language count (13), then one u32 offset per language (relative to the
blob). Each language block is 181 records of 242 bytes: a 42-byte header and a 200-byte UTF-16LE
text slot, so up to 99 characters plus a terminating NUL. In the text, a backslash is a line break.

The header is 21 u16s (0xffff = none): record id, parent, index in parent, first child, previous,
next, value, child count, then up to 13 children. It is the Settings menu: record 110 "Settings"
is the root, its children are the submenus, and leaves carry a value (the option's index). The
Settings screen (section 34) walks it through `read_record_header` (section 0 `0x3061f08`). The
headers are the same in every language block.

Mods are TSV files: one `lang<TAB>record<TAB>text` per line, `#` starts a comment.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from . import patches
from .rknanofw import Firmware, FirmwareError

LANGS = ["de", "en", "es", "fr", "it", "pl", "pt", "ru", "tr", "ja", "ko", "zh-Hans", "zh-Hant"]
RECORD = 242
HEAD = 42
SLOT = RECORD - HEAD
MAX_CHARS = SLOT // 2 - 1
NONE = 0xFFFF
MAX_CHILDREN = 13


@dataclass
class Text:
    lang: str
    record: int
    text: str
    offset: int  # absolute offset of the text slot in the firmware file


@dataclass
class Node:
    """One record header. Links are record numbers, None where the header has 0xffff."""
    record: int
    parent: int | None
    index: int | None
    first_child: int | None
    prev: int | None
    next: int | None
    value: int | None
    count: int | None
    children: list[int] = field(default_factory=list)
    label: str = ""

    @classmethod
    def unpack(cls, raw: bytes, label: str = "") -> Node:
        f = [None if v == NONE else v for v in struct.unpack_from(f"<{HEAD // 2}H", raw)]
        return cls(*f[:8], [c for c in f[8:] if c is not None], label)

    def pack(self) -> bytes:
        if len(self.children) > MAX_CHILDREN:
            raise FirmwareError(f"record {self.record} has {len(self.children)} children; the limit is {MAX_CHILDREN}")
        f = [self.record, self.parent, self.index, self.first_child, self.prev, self.next, self.value, self.count]
        f += self.children + [None] * (MAX_CHILDREN - len(self.children))
        return struct.pack(f"<{HEAD // 2}H", *(NONE if v is None else v for v in f))


def _layout(fw: Firmware) -> tuple[int, list[int], int]:
    blob = fw.blob("strtbl")
    data = fw.read(blob)
    count = struct.unpack_from("<H", data, 0)[0]
    if count != len(LANGS):
        raise FirmwareError(f"string table has {count} languages, expected {len(LANGS)}")
    offsets = list(struct.unpack_from(f"<{count}I", data, 2))
    records = (offsets[1] - offsets[0]) // RECORD
    if any(b - a != records * RECORD for a, b in zip(offsets, offsets[1:])):
        raise FirmwareError("language blocks are not all the same size")
    return blob.offset, offsets, records


def texts(fw: Firmware, lang: str | None = None) -> list[Text]:
    base, offsets, records = _layout(fw)
    out = []
    for li, code in enumerate(LANGS):
        if lang and code != lang:
            continue
        for r in range(records):
            slot = base + offsets[li] + r * RECORD + HEAD
            raw = bytes(fw.buf[slot:slot + SLOT])
            out.append(Text(code, r, raw.decode("utf-16-le").split("\0")[0], slot))
    return out


def tree(fw: Firmware, lang: str = "en") -> dict[int, Node]:
    """Every record's header, labelled with its text in `lang`."""
    base, offsets, records = _layout(fw)
    li = LANGS.index(lang)
    out = {}
    for r in range(records):
        at = base + offsets[li] + r * RECORD
        raw = bytes(fw.buf[at:at + RECORD])
        out[r] = Node.unpack(raw, raw[HEAD:].decode("utf-16-le").split("\0")[0])
    return out


def header_patches(fw: Firmware, nodes: list[Node], note: str = "") -> list[patches.Patch]:
    """File patches that write these headers into every language block (where they differ)."""
    base, offsets, records = _layout(fw)
    out = []
    for node in nodes:
        if not 0 <= node.record < records:
            raise FirmwareError(f"no record {node.record}")
        new = node.pack()
        for lang, off in zip(LANGS, offsets):
            at = base + off + node.record * RECORD
            old = bytes(fw.buf[at:at + HEAD])
            if old != new:
                out.append(patches.Patch(patches.FILE, at, old, new,
                                         f"{note}record {node.record} ({node.label}) header, {lang}"))
    return out


def set_text(fw: Firmware, lang: str, record: int, text: str) -> bool:
    """Write one string; returns False if it already had that text."""
    if lang not in LANGS:
        raise FirmwareError(f"unknown language {lang!r}; use one of {', '.join(LANGS)}")
    if len(text) > MAX_CHARS or "\0" in text:
        raise FirmwareError(f"{lang} {record}: text is {len(text)} characters; the limit is {MAX_CHARS}")
    current = next((t for t in texts(fw, lang) if t.record == record), None)
    if current is None:
        raise FirmwareError(f"{lang} has no record {record}")
    if current.text == text:
        return False
    encoded = text.encode("utf-16-le") + b"\0\0"
    fw.write(current.offset, encoded + bytes(SLOT - len(encoded)))
    return True


def export(fw: Firmware, path: Path, lang: str | None = None):
    lines = ["# lang\trecord\ttext   (a backslash in text is a line break)"]
    lines += [f"{t.lang}\t{t.record}\t{t.text}" for t in texts(fw, lang)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def import_tsv(fw: Firmware, path: Path) -> list[tuple[str, int]]:
    changed = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3 or not parts[1].isdigit():
            raise FirmwareError(f"{path.name}:{n}: expected lang<TAB>record<TAB>text")
        lang, record, text = parts[0], int(parts[1]), parts[2]
        if set_text(fw, lang, record, text):
            changed.append((lang, record))
    return changed
