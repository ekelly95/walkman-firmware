"""Byte patches to stage 3 (the OS), addressed the way the code runs.

Stage 3 is an overlay scheme: many sections run at the same address, so a patch names its
section as well as the run address. A patches.tsv line is

    section<TAB>run address<TAB>old bytes<TAB>new bytes<TAB>note

with hex bytes (spaces allowed) and `#` comments. Old and new must be the same length, and the old
bytes must match the image exactly, so a patch written for one firmware version cannot silently
land somewhere else in another. The section may also be `file`: the address is then an absolute
offset in RKNANOFW.IMG (used for image-table entries).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .rknanofw import HEADER_SIZE, Firmware, FirmwareError, Section, stage_sections


FILE = -1  # pseudo-section: absolute file offset


@dataclass
class Patch:
    section: int
    addr: int
    old: bytes
    new: bytes
    note: str = ""

    def __str__(self) -> str:
        return f"{'file' if self.section == FILE else f'sec {self.section}'} {self.addr:#x} {self.old.hex()} -> {self.new.hex()}" + (f"  {self.note}" if self.note else "")


def thumb_b(from_addr: int, to_addr: int) -> bytes:
    """Encoding of the 16-bit Thumb `b <to>` placed at `from`, for turning a conditional branch
    (cbz/cbnz/b<cond>, also 16-bit) into an unconditional one."""
    off = to_addr - (from_addr + 4)
    if off & 1 or not -2048 <= off < 2048:
        raise FirmwareError(f"b from {from_addr:#x} to {to_addr:#x} is out of range for a 16-bit branch")
    return (0xE000 | ((off >> 1) & 0x7FF)).to_bytes(2, "little")


def parse_tsv(path: Path) -> list[Patch]:
    patches = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            raise FirmwareError(f"{path}:{n}: expected section, address, old, new[, note]")
        try:
            sec, addr = (FILE if parts[0].strip() == "file" else int(parts[0], 0)), int(parts[1], 16)
            old, new = bytes.fromhex(parts[2]), bytes.fromhex(parts[3])
        except ValueError as e:
            raise FirmwareError(f"{path}:{n}: {e}") from None
        if len(old) != len(new) or not old:
            raise FirmwareError(f"{path}:{n}: old and new must be the same non-zero length")
        patches.append(Patch(sec, addr, old, new, parts[4].strip() if len(parts) > 4 else ""))
    return patches


def code_offset(fw: Firmware, section: int, addr: int, size: int = 1) -> int:
    """File offset in the image of `size` bytes of code at run address `addr` in `section`."""
    if section == FILE:
        if not HEADER_SIZE <= addr and addr + size <= fw.size_field:
            raise FirmwareError(f"file offset {addr:#x}+{size} is outside the payload")
        return addr
    stage = fw.blob("stage", 3)
    base, secs = stage_sections(fw.read(stage))
    try:
        s: Section = secs[section]
    except IndexError:
        raise FirmwareError(f"stage 3 has no section {section}") from None
    if s.code_pa <= addr and addr + size <= s.code_pa + s.code_sz:
        return stage.offset + (s.code_va - base) + (addr - s.code_pa)
    if s.data_pa <= addr and addr + size <= s.data_pa + s.data_sz:  # initialised data works the same way
        return stage.offset + (s.data_va - base) + (addr - s.data_pa)
    raise FirmwareError(f"{addr:#x}+{size} is outside section {section}'s code ({s.code_pa:#x}+{s.code_sz:#x}) "
                        f"and data ({s.data_pa:#x}+{s.data_sz:#x})")


def apply(fw: Firmware, patches: list[Patch]) -> list[Patch]:
    """Write every patch after checking that the image holds its old bytes. All or nothing."""
    plan = []
    for p in patches:
        off = code_offset(fw, p.section, p.addr, len(p.old))
        have = bytes(fw.buf[off:off + len(p.old)])
        if have != p.old:
            raise FirmwareError(f"{p}: image has {have.hex()} there, not {p.old.hex()}; wrong firmware version?")
        plan.append((off, p))
    for off, p in plan:
        fw.write(off, p.new)
    return patches


def regions(fw: Firmware, patches: list[Patch]) -> list[tuple[int, int, str]]:
    """(start, end, name) of every patch's bytes, for `nwe39x diff`."""
    return [(off := code_offset(fw, p.section, p.addr, len(p.old)), off + len(p.old), f"patch {p.note or f'{p.addr:#x}'}")
            for p in patches]
