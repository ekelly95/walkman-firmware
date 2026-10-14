import sys
from pathlib import Path

import pytest

from nwe39x import flash
from nwe39x.rknanofw import FirmwareError


def test_cdbs_match_sonys_updater():
    # From WmFwUpdater.dll: FUN_10020444 (REQUEST DEVINFO) and FUN_10020480 (START FW UPDATE).
    assert flash.cdb_devinfo() == bytes.fromhex("fc0020") + b"dbmn" + bytes.fromhex("0080000000")
    assert flash.cdb_start_update() == bytes.fromhex("fc0004") + b"dbmn" + bytes(5)
    assert len(flash.cdb_devinfo()) == len(flash.cdb_start_update()) == 12


def test_devinfo_parse():
    raw = bytes.fromhex(
        "444556494e464f800000000000000000534f4e59202020204e572d453339342020202020202020"
        "20312e3130313020202020305831323334353637382039303132333435") + bytes(0x80 - 0x44)
    info = flash.DevInfo(raw)
    assert info.ok
    assert (info.vendor, info.model, info.version, info.serial) == ("SONY", "NW-E394", "1.1010", "0X12345678 9012345")
    assert not flash.DevInfo(bytes(0x80)).ok


def test_flash_refuses_bad_image(tmp_path):
    bad = tmp_path / "RKNANOFW.IMG"
    bad.write_bytes(bytes(0x400))
    with pytest.raises(FirmwareError):
        flash.flash(bad, tmp_path)


def test_mount_devnum_reads_mountinfo():
    info = ("22 1 259:2 / / rw - ext4 /dev/nvme0n1p2 rw\n"
            "90 22 8:17 / /media/me/WALKMAN rw - vfat /dev/sdb1 rw\n"
            "91 22 8:33 / /media/me/MY\\040DISK rw - vfat /dev/sdc1 rw\n")
    assert flash.mount_devnum(info, Path("/media/me/WALKMAN")) == "8:17"
    assert flash.mount_devnum(info, Path("/media/me/MY DISK/")) == "8:33"
    with pytest.raises(FirmwareError):
        flash.mount_devnum(info, Path("/media/me/OTHER"))


@pytest.mark.skipif(sys.platform == "win32", reason="sysfs names like 8:17 can't be Windows file names")
def test_scsi_device_prefers_sg(tmp_path):
    sysfs, proc = tmp_path / "sys", tmp_path / "proc"
    (proc / "self").mkdir(parents=True)
    (proc / "self/mountinfo").write_text("90 22 8:17 / /media/me/WALKMAN rw - vfat /dev/sdb1 rw\n"
                                         "91 22 8:32 / /media/me/RAW rw - vfat /dev/sdc rw\n")
    disk = sysfs / "dev/block"  # stands in for /sys/block/sdb: the partition's parent
    (disk / "8:17").mkdir(parents=True)
    (disk / "8:17/partition").write_text("1")
    (disk / "device/scsi_generic/sg2").mkdir(parents=True)
    assert flash.scsi_device(Path("/media/me/WALKMAN"), sysfs, proc) == "/dev/sg2"
    (disk / "8:32").mkdir()  # a whole disk with no sg node falls back to its own block device
    assert flash.scsi_device(Path("/media/me/RAW"), sysfs, proc) == "/dev/8:32"
