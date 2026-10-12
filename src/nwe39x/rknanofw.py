"""RKNANOFW.IMG, the firmware image inside Sony's NW-E390 updater.

The header layout and the RC4 scrambling are ported from the RKnanoFW part of Rockbox's
utils/rknanoutils/rkboottool/rkboottool.c (GPL-2.0-or-later). The size rule, the backup header and
the CRC are what the player's own install routine checks before it writes flash.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from .crc import rk_crc

MAGIC = b"RKnanoFW"
HEADER_SIZE = 0x200
KEY = bytes([0x7C, 0x4E, 0x03, 0x04, 0x55, 0x05, 0x09, 0x07,
             0x2D, 0x2C, 0x7B, 0x38, 0x17, 0x0D, 0x17, 0x11])
# Resource tables in the header: name -> (offset of the u32 count, max entries). Each entry is
# {u32 offset, u32 size}, relative to the start of the file.
TABLES = {"stage": (0x50, 4), "font": (0x74, 10), "gbk": (0xC8, 5), "strtbl": (0xF4, 10),
          "imageres": (0x148, 10), "unk": (0x19C, 10)}
SIZE_FIELD = 0x1F4
MAGIC_FIELD = 0x1F8


class FirmwareError(Exception):
    pass


def rc4(data: bytes, key: bytes = KEY) -> bytes:
    """rkboottool's encode_page(): plain RC4 with the 16-byte key. Scrambles and unscrambles."""
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 0xFF
        s[i], s[j] = s[j], s[i]
    out = bytearray(len(data))
    i = j = 0
    for n, b in enumerate(data):
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        out[n] = b ^ s[(s[i] + s[j]) & 0xFF]
    return bytes(out)


def expected_file_size(size_field: int) -> int:
    """The install routine rounds the header's size up past a 16 KiB margin to 1 MiB, plus the CRC."""
    return ((size_field + 0x103FFF) & ~0xFFFFF) + 4


@dataclass
class Blob:
    table: str
    index: int
    offset: int
    size: int

    @property
    def end(self) -> int:
        return self.offset + self.size


@dataclass
class Firmware:
    buf: bytearray
    blobs: dict[str, list[Blob]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> Firmware:
        return cls.from_bytes(Path(path).read_bytes())

    @classmethod
    def from_bytes(cls, data: bytes) -> Firmware:
        fw = cls(bytearray(data))
        if len(data) < HEADER_SIZE or data[MAGIC_FIELD:MAGIC_FIELD + 8] != MAGIC:
            raise FirmwareError("not an RKnanoFW image (no magic at 0x1f8)")
        for name, (off, cap) in TABLES.items():
            count = struct.unpack_from("<I", data, off)[0]
            fw.blobs[name] = [Blob(name, k, *struct.unpack_from("<II", data, off + 4 + 8 * k))
                              for k in range(min(count, cap))]
        return fw

    # Header fields -------------------------------------------------------------------------
    @property
    def date(self) -> str:
        year, mday, month = struct.unpack_from("<HBB", self.buf, 0)
        return f"{year:x}-{month:02x}-{mday:02x}"  # BCD

    @property
    def vendor(self) -> str:
        return bytes(self.buf[0x10:0x30]).split(b"\0")[0].decode("ascii", "replace")

    @property
    def model(self) -> str:
        return bytes(self.buf[0x30:0x50]).split(b"\0")[0].decode("ascii", "replace")

    @property
    def size_field(self) -> int:
        return struct.unpack_from("<I", self.buf, SIZE_FIELD)[0]

    # Blobs ---------------------------------------------------------------------------------
    def blob(self, table: str, index: int = 0) -> Blob:
        try:
            return self.blobs[table][index]
        except (KeyError, IndexError):
            raise FirmwareError(f"no {table}{index} in this image") from None

    def read(self, blob: Blob, descramble: bool = True) -> bytes:
        """Blob contents; stages 0-2 are RC4-scrambled as one stream (stage 3 is plain)."""
        data = bytes(self.buf[blob.offset:blob.end])
        if descramble and blob.table == "stage" and blob.index != 3:
            data = rc4(data)
        return data

    def write(self, offset: int, data: bytes):
        """Overwrite bytes in place. The file layout never changes, so nothing else moves."""
        if offset < HEADER_SIZE or offset + len(data) > self.size_field:
            raise FirmwareError(f"write at {offset:#x}+{len(data):#x} is outside the payload")
        self.buf[offset:offset + len(data)] = data

    # Integrity -----------------------------------------------------------------------------
    @property
    def stored_crc(self) -> int:
        return struct.unpack_from("<I", self.buf, len(self.buf) - 4)[0]

    def compute_crc(self) -> int:
        return rk_crc(bytes(self.buf[:-4]))

    def fix_crc(self):
        struct.pack_into("<I", self.buf, len(self.buf) - 4, self.compute_crc())

    def problems(self) -> list[str]:
        """Everything the player's install routine checks, plus the CRC. Empty means installable."""
        found = []
        if self.buf[MAGIC_FIELD:MAGIC_FIELD + 8] != MAGIC:
            found.append("magic missing")
        want = expected_file_size(self.size_field)
        if len(self.buf) != want:
            found.append(f"file is {len(self.buf):#x} bytes; the player requires {want:#x}")
        backup = self.buf[self.size_field:self.size_field + HEADER_SIZE]
        if backup != self.buf[:HEADER_SIZE]:
            found.append(f"backup header at {self.size_field:#x} differs from the main header")
        for blobs in self.blobs.values():
            for b in blobs:
                if b.size and b.end > self.size_field:
                    found.append(f"{b.table}{b.index} runs past the payload")
        if self.stored_crc != self.compute_crc():
            found.append(f"CRC {self.stored_crc:#010x} should be {self.compute_crc():#010x}")
        return found

    def save(self, path: str | Path, fix_crc: bool = True):
        if fix_crc:
            self.fix_crc()
        if problems := self.problems():
            raise FirmwareError("refusing to save an image the player would reject: " + "; ".join(problems))
        Path(path).write_bytes(self.buf)


@dataclass
class Section:
    """One code/data pair of stage 3. `*_va` locate bytes in the stage file (base + offset);
    `*_pa` are where the code runs. Many sections share a run address: an overlay scheme."""
    index: int
    code_va: int
    code_pa: int
    code_sz: int
    data_va: int
    data_pa: int
    data_sz: int
    bss_pa: int
    bss_sz: int


def stage_sections(stage: bytes) -> tuple[int, list[Section]]:
    base, count = struct.unpack_from("<II", stage, 0)
    return base, [Section(i, *struct.unpack_from("<8I", stage, 8 + 32 * i)) for i in range(count)]
