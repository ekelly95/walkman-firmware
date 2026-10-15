"""Sony's updater (NW-E390_V1_01.exe) in and out.

In: the .exe is an InstallShield self-extractor; the payload is one Microsoft CAB holding
SoftwareUpdateTool.exe, Data/App/WmFwUpdater.dll, Data/Device/SWUpdate.xml and
Data/Device/RKNANOFW.IMG.

Out: a copy of that folder with our RKNANOFW.IMG and a higher version. Sony's tool only installs
a version newer than the one the player reports, and the player reports the version from the
`<firmwareversion>` element compiled into the firmware (its only version string), so both change.
"""

from __future__ import annotations

import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from .rknanofw import Firmware, FirmwareError

IMG = Path("Data") / "Device" / "RKNANOFW.IMG"
SWUPDATE = Path("Data") / "Device" / "SWUpdate.xml"
VERSION_RE = re.compile(rb"<firmwareversion>(\d\.\d\d)</firmwareversion>")


def carve_cab(exe: bytes) -> bytes:
    """The one CAB inside the self-extractor whose header size and file count are plausible."""
    off = 0
    while (off := exe.find(b"MSCF", off)) != -1:
        size = struct.unpack_from("<I", exe, off + 8)[0]
        files = struct.unpack_from("<H", exe, off + 28)[0]
        if 0 < size <= len(exe) - off and 0 < files < 1000:
            return exe[off:off + size]
        off += 4
    raise FirmwareError("no CAB archive found in the updater")


def expand_cab(cab: Path, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        cmd = ["expand.exe", "-F:*", str(cab), str(outdir)]
    elif shutil.which("cabextract"):
        cmd = ["cabextract", "-q", "-d", str(outdir), str(cab)]
    else:
        raise FirmwareError("install cabextract to unpack the updater on this system")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    # cabextract keeps Windows separators as literal backslashes on some versions; normalize.
    for path in list(outdir.iterdir()):
        if "\\" in path.name:
            target = outdir.joinpath(*path.name.split("\\"))
            target.parent.mkdir(parents=True, exist_ok=True)
            path.rename(target)


def unpack(exe_path: Path, outdir: Path) -> Path:
    """Unpack Sony's updater into outdir/cab and return that folder."""
    cab_dir = outdir / "cab"
    cab_file = outdir / "payload.cab"
    outdir.mkdir(parents=True, exist_ok=True)
    cab_file.write_bytes(carve_cab(exe_path.read_bytes()))
    expand_cab(cab_file, cab_dir)
    cab_file.unlink()
    if not (cab_dir / IMG).exists():
        raise FirmwareError(f"{IMG} missing after unpacking; is this the NW-E390 updater?")
    return cab_dir


def firmware_version(fw: Firmware) -> str:
    found = VERSION_RE.findall(bytes(fw.buf))
    if len(found) != 1:
        raise FirmwareError(f"expected one <firmwareversion> in the image, found {len(found)}")
    return found[0].decode()


def set_firmware_version(fw: Firmware, version: str):
    """Set both places the version lives: the capability XML (reported to the PC) and the BCD
    version in the header and its backup (shown on the player's Unit Information screen)."""
    check_version(version)
    m = VERSION_RE.search(bytes(fw.buf))
    fw.write(m.start(1), version.encode())
    major, minor = version.split(".")
    fw.set_header_version(int(major), int(minor))


def check_version(version: str):
    if not re.fullmatch(r"\d\.\d\d", version):
        raise FirmwareError(f"version must look like 1.02 (same length as Sony's), not {version!r}")


def next_version(version: str) -> str:
    major, minor = version.split(".")
    n = int(major) * 100 + int(minor) + 1
    return f"{n // 100}.{n % 100:02d}"


def clear_outdir(cab_dir: Path, outdir: Path):
    """Remove `outdir` before a build, but only if it is empty or an earlier build (it holds the
    updater and an image), and never the unpacked updater itself or a folder around it, so a
    mistyped -o (".", "~", "extract/cab") cannot delete anything else."""
    if not outdir.exists():
        return
    if not outdir.is_dir():
        raise FirmwareError(f"{outdir} is a file, not a build folder")
    out, cab = outdir.resolve(), Path(cab_dir).resolve()
    if out == cab or out in cab.parents:
        raise FirmwareError(f"{outdir} holds Sony's unpacked updater ({cab_dir}); build somewhere else")
    if any(out.iterdir()) and not ((out / "SoftwareUpdateTool.exe").is_file() and (out / IMG).is_file()):
        raise FirmwareError(f"{outdir} is not empty and is not an earlier build; not deleting it. "
                            "Pick another -o or remove it yourself")
    shutil.rmtree(out)


def build(cab_dir: Path, fw: Firmware, version: str, outdir: Path) -> Path:
    """Write a runnable copy of Sony's updater that installs `fw` as `version`."""
    set_firmware_version(fw, version)
    clear_outdir(cab_dir, outdir)
    shutil.copytree(cab_dir, outdir)
    fw.save(outdir / IMG)
    xml = outdir / SWUPDATE
    text = xml.read_text(encoding="iso-8859-1")
    text, n = re.subn(r"<Version>[^<]*</Version>", f"<Version>{version}</Version>", text, count=1)
    if n != 1:
        raise FirmwareError("SWUpdate.xml has no <Version>")
    xml.write_text(text, encoding="iso-8859-1")
    return outdir / "SoftwareUpdateTool.exe"
