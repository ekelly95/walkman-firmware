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


def _fake_sysfs(tmp_path, mountinfo):
    """/sys/dev/block/MAJ:MIN are symlinks into /sys/devices, as on a real kernel."""
    sysfs, proc = tmp_path / "sys", tmp_path / "proc"
    (proc / "self").mkdir(parents=True)
    (proc / "self/mountinfo").write_text(mountinfo)
    usb = sysfs / "devices/pci0000:00/usb1/1-2/host6/target6:0:0/6:0:0:0/block"
    (usb / "sdb/sdb1").mkdir(parents=True)
    (usb / "sdb/sdb1/partition").write_text("1")
    (usb / "sdb/device/scsi_generic/sg2").mkdir(parents=True)
    (usb / "sdc").mkdir()  # a whole-disk filesystem, and no sg driver for it
    (sysfs / "dev/block").mkdir(parents=True)
    (sysfs / "dev/block/8:17").symlink_to(usb / "sdb/sdb1")
    (sysfs / "dev/block/8:32").symlink_to(usb / "sdc")
    return sysfs, proc, usb


@pytest.mark.skipif(sys.platform == "win32", reason="sysfs names like 8:17 can't be Windows file names")
def test_linux_target_follows_sysfs_links(tmp_path):
    media = tmp_path / "run/media/me"
    sysfs, proc, usb = _fake_sysfs(tmp_path, f"90 22 8:17 / {media}/WALKMAN rw - vfat /dev/sdb1 rw\n"
                                             f"91 22 8:32 / {media}/RAW rw - vfat /dev/sdc rw\n")
    (media / "WALKMAN").mkdir(parents=True)
    t = flash.linux_target(media / "WALKMAN", sysfs, proc)
    assert (t.dev, t.part, t.devnum, t.disk) == ("/dev/sg2", "/dev/sdb1", "8:17", usb / "sdb")
    assert flash.scsi_device(media / "RAW", sysfs, proc) == "/dev/sdc"
    (tmp_path / "link").symlink_to(media)  # through a symlink, and relative: mountinfo has the real path
    assert flash.scsi_device(tmp_path / "link/WALKMAN", sysfs, proc) == "/dev/sg2"
    with pytest.MonkeyPatch.context() as m:
        m.chdir(media)
        assert flash.scsi_device(Path("WALKMAN"), sysfs, proc) == "/dev/sg2"


def _devinfo(serial):
    raw = (b"DEVINFO\x80" + bytes(8) + b"SONY    " + b"NW-E394".ljust(16) + b"1.1010  " + serial.ljust(20).encode())
    return flash.DevInfo(raw.ljust(0x80, b"\0"))


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the Linux flash sequence")
def test_linux_flash_unmounts_survives_a_dropped_link_and_waits_for_the_same_player(image_bytes, tmp_path, monkeypatch):
    from nwe39x import device
    img = tmp_path / "RKNANOFW.IMG"
    img.write_bytes(image_bytes)
    root, other, back = (tmp_path / n for n in ("WALKMAN", "WALKMAN1", "WALKMAN2"))
    for d in (root, other, back):
        d.mkdir()
    disk = tmp_path / "sys/block/sdb"
    disk.mkdir(parents=True)
    serials = {root: "AAA", other: "BBB", back: "AAA"}  # another player is plugged in too
    mounted = {root, other}
    calls = []
    monkeypatch.setenv("NWE39X_LINUX_FLASH", "1")
    monkeypatch.setattr(flash.time, "sleep", lambda s: None)
    monkeypatch.setattr(device, "read_player", lambda r: device.Player(r, "1.01" if r == root else "1.02") if r in mounted else None)
    monkeypatch.setattr(device, "find_players", lambda: [device.Player(r, "x") for r in sorted(mounted)])
    monkeypatch.setattr(flash, "devinfo", lambda r: _devinfo(serials[r]))
    monkeypatch.setattr(flash, "linux_target", lambda r: flash.LinuxTarget("/dev/sg2", "/dev/sdb1", "8:17", disk))

    def unmount(t, r):
        assert (r / "RKNANOFW.IMG").read_bytes() == image_bytes  # written before unmounting
        calls.append("unmount")
        mounted.discard(r)

    def start(r, dev):
        calls.append(("start", dev))
        disk.rmdir()  # the player resets as it takes the command...
        polls = iter(range(3))
        monkeypatch.setattr(device, "find_players",  # ...and only comes back at WALKMAN2 a few polls later
                            lambda: [device.Player(r, "x") for r in sorted(mounted | ({back} if next(polls, 3) >= 2 else set()))])
        mounted.add(back)
        raise flash.TransportError("SG_IO on /dev/sg2: host status 0x1, driver status 0x0")

    monkeypatch.setattr(flash, "unmount", unmount)
    monkeypatch.setattr(flash, "start_update", start)
    log = []
    assert flash.flash(img, root, log=log.append) == "1.02"
    assert calls == ["unmount", ("start", "/dev/sg2")]
    assert any("probably started installing" in l for l in log)
    assert "WALKMAN2" in log[-1]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the Linux gate")
def test_linux_flash_is_gated(image_bytes, tmp_path, monkeypatch):
    monkeypatch.delenv("NWE39X_LINUX_FLASH", raising=False)
    with pytest.raises(FirmwareError, match="NWE39X_LINUX_FLASH"):
        flash.check_platform()
    monkeypatch.setattr(flash, "LINUX", False)
    monkeypatch.setattr(flash.sys, "platform", "darwin")
    with pytest.raises(FirmwareError, match="only implemented on Windows and Linux, not darwin"):
        flash.check_platform()
