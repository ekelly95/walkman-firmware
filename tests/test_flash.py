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
