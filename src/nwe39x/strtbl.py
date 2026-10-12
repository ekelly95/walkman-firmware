"""strtbl0, the firmware's UI text.

Layout (NW-E390 1.01): u16 language count (13), then one u32 offset per language (relative to the
blob). Each language block is 181 records of 242 bytes: a 42-byte header (u16 record id, then
u16 links to neighbouring records, 0xffff = none) and a 200-byte UTF-16LE text slot, so up to 99
characters plus a terminating NUL. In the text, a backslash is a line break.

Mods are TSV files: one `lang<TAB>record<TAB>text` per line, `#` starts a comment.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from .rknanofw import Firmware, FirmwareError

LANGS = ["de", "en", "es", "fr", "it", "pl", "pt", "ru", "tr", "ja", "ko", "zh-Hans", "zh-Hant"]
RECORD = 242
HEAD = 42
SLOT = RECORD - HEAD
MAX_CHARS = SLOT // 2 - 1


@dataclass
class Text:
    lang: str
    record: int
    text: str
    offset: int  # absolute offset of the text slot in the firmware file


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
