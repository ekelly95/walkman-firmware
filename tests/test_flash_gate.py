"""`nwe39x flash` refuses before anything reaches the player: OS changes need --allow-code-patches,
a stock-restore build must exist and be stock, and a person confirms. The player and the transfer
are stubbed, so these tests never touch a device."""

import pytest

from nwe39x import cli, device, flash, imageres, updater, verify
from nwe39x.rknanofw import Firmware

SEC_PA = 0x0306C000  # the synthetic image's one stage-3 section


@pytest.fixture
def env(image_bytes, tmp_path, monkeypatch):
    cab = tmp_path / "cab"
    (cab / "Data" / "Device").mkdir(parents=True)
    (cab / "SoftwareUpdateTool.exe").write_bytes(b"MZ")
    (cab / updater.IMG).write_bytes(image_bytes)
    (cab / updater.SWUPDATE).write_text("<Common>\n<Version>1.01</Version>\n</Common>", encoding="iso-8859-1")

    def build(name, edit=None, patch_files=()):
        fw = Firmware.from_bytes(image_bytes)
        if edit:
            edit(fw)
        out = tmp_path / name
        updater.build(cab, fw, "1.02", out)
        verify.write_manifest(out, "1.02", list(patch_files), name)
        return out

    sent = []
    monkeypatch.setattr(cli, "one_player", lambda args: device.Player(tmp_path, "1.01"))
    monkeypatch.setattr(flash, "flash", lambda img, root, wait=True: sent.append(img) or "1.02")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "flash")

    def run(*argv):
        cli.main(["flash", "--cab", str(cab), "--restore", str(tmp_path / "restore"), *map(str, argv)])

    return cab, tmp_path, build, run, sent


def theme(fw):  # one picture byte: a resource change, not the OS
    fw.write(imageres.pictures(fw)[0].offset, b"\x42")


def code_patch(tmp_path):
    tsv = tmp_path / "p.tsv"
    tsv.write_text(f"0\t{SEC_PA + 4:x}\t0000\t0102\tcode change\n")
    return tsv


def test_theme_flashes_once_a_restore_exists(env):
    cab, tmp, build, run, sent = env
    mod = build("mod", theme)
    with pytest.raises(SystemExit, match="no stock-restore build"):
        run("--updater", mod)
    build("restore")
    run("--updater", mod)
    assert sent == [mod / updater.IMG]


def test_os_changes_need_allow_code_patches(env):
    cab, tmp, build, run, sent = env
    build("restore")
    tsv = code_patch(tmp)
    mod = build("mod", lambda fw: fw.write(_sec_off(fw), b"\x01\x02"), [tsv])
    with pytest.raises(SystemExit, match="OS itself.*patch code change"):
        run("--updater", mod)
    assert sent == []
    run("--updater", mod, "--allow-code-patches")
    assert sent == [mod / updater.IMG]


def test_force_does_not_skip_the_os_check(env):
    cab, tmp, build, run, sent = env
    build("restore")
    mod = build("mod", lambda fw: fw.write(_sec_off(fw), b"\x01\x02"))  # no manifest names it
    with pytest.raises(SystemExit, match="OS itself"):
        run("--updater", mod, "--force")
    assert sent == []


def test_restore_must_be_stock(env):
    cab, tmp, build, run, sent = env
    build("restore", theme)  # a "restore" that is really a mod
    mod = build("mod", theme)
    with pytest.raises(SystemExit, match="not Sony's stock image"):
        run("--updater", mod)
    assert sent == []


def test_flashing_the_restore_itself_needs_no_other_restore(env):
    cab, tmp, build, run, sent = env
    restore = build("restore")
    run("--updater", restore)
    assert sent == [restore / updater.IMG]


def test_confirmation(env, monkeypatch):
    cab, tmp, build, run, sent = env
    build("restore")
    mod = build("mod", theme)
    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")
    with pytest.raises(SystemExit, match="not confirmed"):
        run("--updater", mod)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit, match="typed confirmation"):
        run("--updater", mod)
    assert sent == []
    run("--updater", mod, "--yes")
    assert sent == [mod / updater.IMG]


def test_unexplained_bytes_are_refused_without_suggesting_force(env):
    cab, tmp, build, run, sent = env
    build("restore")
    mod = build("mod", lambda fw: fw.write(0x300, b"\x01"))  # header area: nothing explains it
    with pytest.raises(SystemExit) as e:
        run("--updater", mod)
    assert "not explained" in str(e.value) and "--force" not in str(e.value)
    assert sent == []


def _sec_off(fw):
    from nwe39x import patches
    return patches.code_offset(fw, 0, SEC_PA + 4, 2)
