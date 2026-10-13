"""Flash the player without Sony's tool.

What WmFwUpdater.dll does (CWmFwUpdateWorkerMsc, CWmFwScsiCmd, sptioctl::CSptIoCtl): copy
RKNANOFW.IMG to the root of the player's drive, open `\\\\.\\X:` and send one vendor SCSI command
through IOCTL_SCSI_PASS_THROUGH_DIRECT. The player then unmounts, runs its install routine
(which has no version check, only the magic/size/backup-header checks in `Firmware.problems`),
deletes the file and reboots. Two 12-byte CDBs, both `FC 00 <op> 'd' 'b' 'm' 'n' ...`:

    op 0x20, 0x80 bytes in   REQUEST DEVINFO   "DEVINFO" + info block ("SONY    ", model, ...)
    op 0x04, no data         START FW UPDATE   reboot into the installer

Windows uses the pass-through IOCTL; Linux uses SG_IO on the block device (untested).
"""

from __future__ import annotations

import ctypes
import os
import shutil
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import device
from .rknanofw import Firmware, FirmwareError

MAGIC = b"dbmn"
DEVINFO_LEN = 0x80
TIMEOUT_S = 30


def cdb_devinfo() -> bytes:
    return bytes([0xFC, 0x00, 0x20]) + MAGIC + struct.pack(">H", DEVINFO_LEN) + bytes(3)


def cdb_start_update() -> bytes:
    return bytes([0xFC, 0x00, 0x04]) + MAGIC + bytes(5)


@dataclass
class DevInfo:
    """The 0x80-byte block: "DEVINFO", u8 size, 8 zero bytes, vendor[8], model[16], version[8]
    (the header's BCD major.minor and rev, e.g. "1.1010" for 1.10 rev 10, which is what Sony's
    tool compares with its package after installing), serial[20], zeros."""
    raw: bytes

    @property
    def ok(self) -> bool:
        return self.raw[:7] == b"DEVINFO"

    def _field(self, start: int, size: int) -> str:
        return self.raw[start:start + size].decode("ascii", "replace").strip("\0 ")

    @property
    def vendor(self) -> str:
        return self._field(0x10, 8)

    @property
    def model(self) -> str:
        return self._field(0x18, 16)

    @property
    def version(self) -> str:
        return self._field(0x28, 8)

    @property
    def serial(self) -> str:
        return self._field(0x30, 20)

    def __str__(self) -> str:
        return f"{self.vendor} {self.model}, header version {self.version}, serial {self.serial}"


# SCSI pass-through ---------------------------------------------------------------------------
if sys.platform == "win32":
    IOCTL_SCSI_PASS_THROUGH_DIRECT = 0x4D014
    SCSI_IOCTL_DATA_OUT, SCSI_IOCTL_DATA_IN, SCSI_IOCTL_DATA_UNSPECIFIED = 0, 1, 2
    SENSE_LEN = 32

    class _SPTD(ctypes.Structure):
        _fields_ = [("Length", ctypes.c_ushort), ("ScsiStatus", ctypes.c_ubyte), ("PathId", ctypes.c_ubyte),
                    ("TargetId", ctypes.c_ubyte), ("Lun", ctypes.c_ubyte), ("CdbLength", ctypes.c_ubyte),
                    ("SenseInfoLength", ctypes.c_ubyte), ("DataIn", ctypes.c_ubyte),
                    ("DataTransferLength", ctypes.c_ulong), ("TimeOutValue", ctypes.c_ulong),
                    ("DataBuffer", ctypes.c_void_p), ("SenseInfoOffset", ctypes.c_ulong),
                    ("Cdb", ctypes.c_ubyte * 16)]

    class _SPTDWithSense(ctypes.Structure):
        _fields_ = [("sptd", _SPTD), ("filler", ctypes.c_ulong), ("sense", ctypes.c_ubyte * SENSE_LEN)]

    def _send(root: Path, cdb: bytes, data_in: int = 0) -> bytes:
        k32 = ctypes.windll.kernel32
        letter = str(root)[0]
        h = k32.CreateFileW(f"\\\\.\\{letter}:", 0xC0000000, 3, None, 3, 0x80000000, None)
        if h == ctypes.c_void_p(-1).value or h == -1:
            raise FirmwareError(f"cannot open \\\\.\\{letter}: for SCSI pass-through (error {ctypes.get_last_error() or k32.GetLastError()})")
        try:
            buf = ctypes.create_string_buffer(data_in or 1)
            s = _SPTDWithSense()
            s.sptd.Length = ctypes.sizeof(_SPTD)
            s.sptd.CdbLength = len(cdb)
            s.sptd.SenseInfoLength = SENSE_LEN
            s.sptd.DataIn = SCSI_IOCTL_DATA_IN if data_in else SCSI_IOCTL_DATA_UNSPECIFIED
            s.sptd.DataTransferLength = data_in
            s.sptd.TimeOutValue = TIMEOUT_S
            s.sptd.DataBuffer = ctypes.cast(buf, ctypes.c_void_p) if data_in else None
            s.sptd.SenseInfoOffset = _SPTDWithSense.sense.offset
            ctypes.memmove(s.sptd.Cdb, cdb, len(cdb))
            returned = ctypes.c_ulong(0)
            ok = k32.DeviceIoControl(h, IOCTL_SCSI_PASS_THROUGH_DIRECT, ctypes.byref(s), ctypes.sizeof(s),
                                     ctypes.byref(s), ctypes.sizeof(s), ctypes.byref(returned), None)
            if not ok:
                raise FirmwareError(f"DeviceIoControl(SCSI_PASS_THROUGH_DIRECT) failed, error {k32.GetLastError()}")
            if s.sptd.ScsiStatus != 0:
                sense = bytes(s.sense)
                raise FirmwareError(f"SCSI status {s.sptd.ScsiStatus:#x}, sense key {sense[2] & 0xF}, asc/ascq {sense[12]:#x}/{sense[13]:#x}")
            return buf.raw[:s.sptd.DataTransferLength] if data_in else b""
        finally:
            k32.CloseHandle(h)

else:
    import fcntl

    SG_IO = 0x2285
    SG_DXFER_NONE, SG_DXFER_FROM_DEV = -1, -3

    def _send(root: Path, cdb: bytes, data_in: int = 0) -> bytes:
        dev = _block_device(root)
        buf = ctypes.create_string_buffer(data_in or 1)
        sense = ctypes.create_string_buffer(32)
        cdb_buf = ctypes.create_string_buffer(cdb, len(cdb))
        # struct sg_io_hdr (see <scsi/sg.h>)
        hdr = struct.pack("=iiBBHIPPPIIiPBBBBHHiII", ord("S"), SG_DXFER_FROM_DEV if data_in else SG_DXFER_NONE,
                          len(cdb), 32, 0, 0, 0, data_in, ctypes.addressof(buf), ctypes.addressof(cdb_buf),
                          ctypes.addressof(sense), TIMEOUT_S * 1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        hdr = ctypes.create_string_buffer(hdr, len(hdr))
        with open(dev, "rb") as f:
            fcntl.ioctl(f.fileno(), SG_IO, hdr)
        status = hdr.raw[struct.calcsize("=iiBBHIPPPIIiP")]
        if status != 0:
            raise FirmwareError(f"SCSI status {status:#x} from {dev}")
        return buf.raw[:data_in]

    def _block_device(root: Path) -> str:
        with open("/proc/mounts") as f:
            for line in f:
                dev, mnt = line.split()[:2]
                if Path(mnt) == root:
                    return dev.rstrip("0123456789") if dev.startswith("/dev/sd") else dev
        raise FirmwareError(f"no block device mounted at {root}")


# Commands ------------------------------------------------------------------------------------
def devinfo(root: Path) -> DevInfo:
    info = DevInfo(_send(root, cdb_devinfo(), DEVINFO_LEN))
    if not info.ok:
        raise FirmwareError(f"REQUEST DEVINFO returned {info.raw[:16].hex()}, not a DEVINFO block")
    return info


def start_update(root: Path):
    _send(root, cdb_start_update())


def flash(img: Path, root: Path, wait: bool = True, log=print) -> str | None:
    """Copy `img` to the player at `root`, send START FW UPDATE and (optionally) wait for it to come
    back. Returns the version the player reports afterwards, or None if not waited for."""
    fw = Firmware.load(img)
    if problems := fw.problems():
        raise FirmwareError("the player would reject this image: " + "; ".join(problems))
    player = device.read_player(root)
    if player is None:
        raise FirmwareError(f"{root} is not an NW-E390-series player")
    info = devinfo(root)
    log(f"player at {root}: firmware {player.version}, {info}")
    target = root / "RKNANOFW.IMG"
    free = shutil.disk_usage(root).free
    if free < len(fw.buf):
        raise FirmwareError(f"{free:,} bytes free on the player; the image needs {len(fw.buf):,}")
    log(f"copying {img.name} ({len(fw.buf):,} bytes) to {target}")
    with open(target, "wb") as f:
        f.write(fw.buf)
        f.flush()
        os.fsync(f.fileno())
    log("sending START FW UPDATE")
    start_update(root)
    if not wait:
        return None
    t0 = time.time()
    while device.read_player(root) is not None:
        if time.time() - t0 > 60:
            raise FirmwareError("the player did not unmount within 60 s; did it start the update?")
        time.sleep(1)
    log(f"player unmounted after {time.time() - t0:.0f} s, installing...")
    while (p := device.read_player(root)) is None:
        if time.time() - t0 > 300:
            raise FirmwareError("the player did not come back within 5 min")
        time.sleep(2)
    log(f"player back after {time.time() - t0:.0f} s, reports {p.version}; "
        + ("image file consumed" if not target.exists() else "WARNING: RKNANOFW.IMG still on the drive"))
    return p.version
