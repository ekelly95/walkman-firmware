"""Flash the player without Sony's tool.

What WmFwUpdater.dll does (CWmFwUpdateWorkerMsc, CWmFwScsiCmd, sptioctl::CSptIoCtl): copy
RKNANOFW.IMG to the root of the player's drive, open `\\\\.\\X:` and send one vendor SCSI command
through IOCTL_SCSI_PASS_THROUGH_DIRECT. The player then unmounts, runs its install routine
(which has no version check, only the magic/size/backup-header checks in `Firmware.problems`),
deletes the file and reboots. Two 12-byte CDBs, both `FC 00 <op> 'd' 'b' 'm' 'n' ...`:

    op 0x20, 0x80 bytes in   REQUEST DEVINFO   "DEVINFO" + info block ("SONY    ", model, ...)
    op 0x04, no data         START FW UPDATE   reboot into the installer

Windows sends them with the pass-through IOCTL, as Sony's tool does. Linux sends them with SG_IO
on the drive's /dev/sgN (the sg driver, which has no command filter; the /dev/sdX fallback needs
root for vendor opcodes), and unmounts the filesystem first so the kernel can't write to it while
the player rewrites it. Linux is untested on the player, so START FW UPDATE there also needs
NWE39X_LINUX_FLASH=1 in the environment: run `nwe39x devinfo` first and check its answer.
"""

from __future__ import annotations

import ctypes
import os
import posixpath
import re
import shutil
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import device
from .rknanofw import Firmware, FirmwareError

MAGIC = b"dbmn"
DEVINFO_LEN = 0x80
TIMEOUT_S = 30
LINUX = sys.platform.startswith("linux")


class TransportError(FirmwareError):
    """The link to the player failed mid-command, so the command may or may not have reached it."""


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

    def _send(root: Path, cdb: bytes, data_in: int = 0, dev: str | None = None) -> bytes:
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
                raise TransportError(f"DeviceIoControl(SCSI_PASS_THROUGH_DIRECT) failed, error {k32.GetLastError()}")
            if s.sptd.ScsiStatus != 0:
                sense = bytes(s.sense)
                raise FirmwareError(f"SCSI status {s.sptd.ScsiStatus:#x}, sense key {sense[2] & 0xF}, asc/ascq {sense[12]:#x}/{sense[13]:#x}")
            return buf.raw[:s.sptd.DataTransferLength] if data_in else b""
        finally:
            k32.CloseHandle(h)

elif LINUX:
    import fcntl

    SG_IO = 0x2285
    SG_DXFER_NONE, SG_DXFER_FROM_DEV = -1, -3
    DRIVER_SENSE = 0x08
    SENSE_LEN = 32

    class _SgIoHdr(ctypes.Structure):  # <scsi/sg.h> struct sg_io_hdr, natural alignment
        _fields_ = [("interface_id", ctypes.c_int), ("dxfer_direction", ctypes.c_int),
                    ("cmd_len", ctypes.c_ubyte), ("mx_sb_len", ctypes.c_ubyte), ("iovec_count", ctypes.c_ushort),
                    ("dxfer_len", ctypes.c_uint), ("dxferp", ctypes.c_void_p), ("cmdp", ctypes.c_void_p),
                    ("sbp", ctypes.c_void_p), ("timeout", ctypes.c_uint), ("flags", ctypes.c_uint),
                    ("pack_id", ctypes.c_int), ("usr_ptr", ctypes.c_void_p), ("status", ctypes.c_ubyte),
                    ("masked_status", ctypes.c_ubyte), ("msg_status", ctypes.c_ubyte), ("sb_len_wr", ctypes.c_ubyte),
                    ("host_status", ctypes.c_ushort), ("driver_status", ctypes.c_ushort), ("resid", ctypes.c_int),
                    ("duration", ctypes.c_uint), ("info", ctypes.c_uint)]

    def _send(root: Path, cdb: bytes, data_in: int = 0, dev: str | None = None) -> bytes:
        """`dev` is the /dev/sgN to use; without it, the one holding the filesystem mounted at `root`."""
        dev = dev or scsi_device(root)
        try:
            fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError:
            raise FirmwareError(f"no permission to open {dev} for SCSI pass-through. Add the udev rule in "
                                "docs/linux.md (then unplug and replug the player), or run this once with sudo") from None
        except OSError as e:
            raise FirmwareError(f"cannot open {dev} for SCSI pass-through: {e}") from None
        try:
            buf = ctypes.create_string_buffer(data_in or 1)
            cdb_buf = ctypes.create_string_buffer(cdb, len(cdb))
            sense = ctypes.create_string_buffer(SENSE_LEN)
            h = _SgIoHdr(interface_id=ord("S"), dxfer_direction=SG_DXFER_FROM_DEV if data_in else SG_DXFER_NONE,
                         cmd_len=len(cdb), mx_sb_len=SENSE_LEN, dxfer_len=data_in,
                         dxferp=ctypes.cast(buf, ctypes.c_void_p) if data_in else None,
                         cmdp=ctypes.cast(cdb_buf, ctypes.c_void_p), sbp=ctypes.cast(sense, ctypes.c_void_p),
                         timeout=TIMEOUT_S * 1000)
            try:
                fcntl.ioctl(fd, SG_IO, h)
            except OSError as e:
                raise TransportError(f"SG_IO on {dev} failed: {e}") from None
            if h.status != 0:
                s = sense.raw
                raise FirmwareError(f"SCSI status {h.status:#x}, sense key {s[2] & 0xF}, asc/ascq {s[12]:#x}/{s[13]:#x}")
            if h.host_status != 0 or h.driver_status & ~DRIVER_SENSE:
                raise TransportError(f"SG_IO on {dev}: host status {h.host_status:#x}, driver status {h.driver_status:#x}")
            return buf.raw[:data_in - h.resid] if data_in else b""
        finally:
            os.close(fd)

else:
    def _send(root: Path, cdb: bytes, data_in: int = 0, dev: str | None = None) -> bytes:
        raise FirmwareError(f"SCSI pass-through is only implemented on Windows and Linux, not {sys.platform}")


# Linux: from a mount point to the player's SCSI device ---------------------------------------
def mount_devnum(mountinfo: str, root: Path) -> str:
    """The "major:minor" of the filesystem mounted at `root`, from /proc/self/mountinfo text."""
    want = posixpath.normpath(root.as_posix())
    found = None
    for line in mountinfo.splitlines():
        f = line.split()
        if len(f) > 4 and re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), f[4]) == want:
            found = f[2]  # a later mount on the same point hides an earlier one
    if found is None:
        raise FirmwareError(f"{root} is not a mount point")
    return found


@dataclass
class LinuxTarget:
    dev: str    # /dev/sgN for SCSI commands, or /dev/sdX when the sg driver isn't loaded
    part: str   # the mounted block device, e.g. /dev/sdb1
    devnum: str  # its "major:minor"
    disk: Path  # the disk's sysfs directory, which goes away when the player drops off USB


def linux_target(root: Path, sysfs: Path = Path("/sys"), proc: Path = Path("/proc")) -> LinuxTarget:
    """Where the filesystem mounted at `root` lives. Needs the mount, so call it before unmounting."""
    devnum = mount_devnum((proc / "self/mountinfo").read_text(), Path(os.path.realpath(root)))
    block = (sysfs / "dev/block" / devnum).resolve()
    disk = block.parent if (block / "partition").exists() else block
    sg = sorted((disk / "device/scsi_generic").glob("sg*"))
    return LinuxTarget(f"/dev/{sg[0].name}" if sg else f"/dev/{disk.name}", f"/dev/{block.name}", devnum, disk)


def scsi_device(root: Path, sysfs: Path = Path("/sys"), proc: Path = Path("/proc")) -> str:
    """/dev/sgN for the disk holding `root`, or /dev/sdX when the sg driver isn't loaded."""
    return linux_target(root, sysfs, proc).dev


def unmount(t: LinuxTarget, root: Path, proc: Path = Path("/proc")):
    """Unmount the player's filesystem, so the host can't write to it (dirty bit, atime, another
    program's late writes) while the player reads the image and rewrites its FAT."""
    left = f"Nothing was sent to the player; {root / 'RKNANOFW.IMG'} is still on it."
    try:
        r = subprocess.run(["udisksctl", "unmount", "--no-user-interaction", "-b", t.part],
                           capture_output=True, text=True, timeout=60, check=False)
    except FileNotFoundError:
        raise FirmwareError(f"udisksctl (udisks2) is needed to unmount {root} before flashing. {left}") from None
    except subprocess.TimeoutExpired:
        raise FirmwareError(f"udisksctl did not unmount {root} within 60 s. {left}") from None
    if r.returncode != 0:
        raise FirmwareError(f"could not unmount {root}: {(r.stderr or r.stdout).strip()}. Close anything using the "
                            f"player (a Dolphin window, a terminal inside it) and try again. {left}")
    if any(len(f := line.split()) > 2 and f[2] == t.devnum for line in (proc / "self/mountinfo").read_text().splitlines()):
        raise FirmwareError(f"{t.part} is still mounted somewhere else; unmount it everywhere and try again. {left}")


# Commands ------------------------------------------------------------------------------------
def devinfo(root: Path) -> DevInfo:
    info = DevInfo(_send(root, cdb_devinfo(), DEVINFO_LEN))
    if not info.ok:
        raise FirmwareError(f"REQUEST DEVINFO returned {info.raw[:16].hex()}, not a DEVINFO block")
    return info


def start_update(root: Path, dev: str | None = None):
    _send(root, cdb_start_update(), dev=dev)


def check_platform():
    """Refuse to flash where it isn't implemented or hasn't been tried on a player."""
    if sys.platform == "win32":
        return
    if not LINUX:
        raise FirmwareError(f"flashing is only implemented on Windows and Linux, not {sys.platform}")
    if os.environ.get("NWE39X_LINUX_FLASH") != "1":
        raise FirmwareError("flashing from Linux has not been tested on a player. Run `nwe39x devinfo` first; if it "
                            "answers SONY and your model, see docs/linux.md for NWE39X_LINUX_FLASH=1")


def find_again(root: Path, serial: str) -> device.Player | None:
    """The flashed player once it is back, matched by its DEVINFO serial so another connected player
    can't stand in for it. Linux may remount it elsewhere (WALKMAN1), so look there too."""
    roots = [root] + ([p.root for p in device.find_players()] if LINUX and serial else [])
    for r in dict.fromkeys(roots):
        if (p := device.read_player(r)) is None:
            continue
        try:
            if devinfo(r).serial == serial:
                return p
        except FirmwareError:
            continue  # still starting up, or not one we can talk to
    return None


def flash(img: Path, root: Path, wait: bool = True, log=print) -> str | None:
    """Copy `img` to the player at `root`, send START FW UPDATE and (optionally) wait for it to come
    back. Returns the version the player reports afterwards, or None if not waited for."""
    fw = Firmware.load(img)
    if problems := fw.problems():
        raise FirmwareError("the player would reject this image: " + "; ".join(problems))
    player = device.read_player(root)
    if player is None:
        raise FirmwareError(f"{root} is not an NW-E390-series player")
    check_platform()
    info = devinfo(root)
    log(f"player at {root}: firmware {player.version}, {info}")
    linux = linux_target(root) if LINUX else None
    target = root / "RKNANOFW.IMG"
    free = shutil.disk_usage(root).free
    if free < len(fw.buf):
        raise FirmwareError(f"{free:,} bytes free on the player; the image needs {len(fw.buf):,}")
    log(f"copying {img.name} ({len(fw.buf):,} bytes) to {target}")
    with open(target, "wb") as f:
        f.write(fw.buf)
        f.flush()
        os.fsync(f.fileno())
    if sys.platform != "win32":  # the directory entry and FAT too, before the player reads them itself
        dfd = os.open(root, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        os.sync()
    if linux:
        log(f"unmounting {root} ({linux.part}) so only the player writes to it from here on")
        unmount(linux, root)
    log("sending START FW UPDATE")
    try:
        start_update(root, linux.dev if linux else None)
    except TransportError as e:
        # A player that resets as it takes the command looks like this too, so don't call it a failure.
        log(f"the link dropped as the player took the command ({e}); it has probably started installing. "
            "Do NOT unplug it. Waiting for it to come back.")
    if not wait:
        return None
    t0 = time.time()
    # Linux: the mount is gone already, so watch the USB disk itself, not a possibly cached file.
    still_there = (lambda: linux.disk.exists()) if linux else (lambda: device.read_player(root) is not None)
    while still_there():
        if time.time() - t0 > 60:
            raise FirmwareError("the player is still connected 60 s after START FW UPDATE, so it probably did not "
                                "start the update. Check its screen before unplugging it"
                                + ("; replug it to mount it again." if linux else "."))
        time.sleep(1)
    log(f"player restarted after {time.time() - t0:.0f} s, installing...")
    while (p := find_again(root, info.serial)) is None:
        if time.time() - t0 > 300:
            raise FirmwareError("the player did not come back within 5 min"
                                + ("; if it is back but not mounted, mount it in Dolphin and run `nwe39x status`"
                                   if linux else ""))
        time.sleep(2)
    target = p.root / "RKNANOFW.IMG"
    log(f"player back after {time.time() - t0:.0f} s at {p.root}, reports {p.version}; "
        + ("image file consumed" if not target.exists() else "WARNING: RKNANOFW.IMG still on the drive"))
    return p.version
