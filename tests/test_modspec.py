import pytest

from nwe39x import modspec, verify
from nwe39x.rknanofw import Firmware, FirmwareError


def test_folder_without_toml_uses_its_contents(tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "patches.tsv").write_text("")
    m = modspec.load(tmp_path)
    assert m.name == tmp_path.name and len(m.images) == 1 and len(m.patches) == 1 and not m.fonts


def test_toml_with_include_and_theme(tmp_path):
    base = tmp_path / "base"; base.mkdir()
    (base / "mod.toml").write_text('name = "base"\ntheme = "mono"\n')
    top = tmp_path / "top"; top.mkdir()
    (top / "mod.toml").write_text('include = ["../base"]\npatches = []\n')
    m = modspec.load(top)
    assert m.name == "top" and m.include[0].name == "base" and m.include[0].theme == "mono"
    assert "base: theme mono" in m.describe()


def test_toml_errors(tmp_path):
    (tmp_path / "mod.toml").write_text('images = ["missing"]\n')
    with pytest.raises(FirmwareError, match="not found"):
        modspec.load(tmp_path)
    (tmp_path / "mod.toml").write_text('bogus = 1\n')
    with pytest.raises(FirmwareError, match="unknown keys"):
        modspec.load(tmp_path)
    (tmp_path / "mod.toml").write_text('include = ["."]\n')
    with pytest.raises(FirmwareError, match="itself"):
        modspec.load(tmp_path)


def test_apply_theme_in_place_and_verify_explains_it(image_bytes, tmp_path):
    stock = Firmware.from_bytes(image_bytes)
    fw = Firmware.from_bytes(image_bytes)
    (tmp_path / "mod.toml").write_text('theme = "neon"\n')
    n = modspec.apply(fw, modspec.load(tmp_path), log=lambda *_: None)
    assert n >= 1
    rep = verify.explain(stock, fw)
    assert rep.unknown == [] and any(k.startswith("picture") for k in rep.hits)
    fw.buf[0x300] ^= 1  # a stray byte in the header area
    assert verify.explain(stock, fw).unknown == [0x300]


def test_verify_checks_patch_bytes_not_just_their_place(image_bytes, tmp_path):
    from nwe39x import patches
    stock, fw = Firmware.from_bytes(image_bytes), Firmware.from_bytes(image_bytes)
    tsv = tmp_path / "p.tsv"
    tsv.write_text("0\t306c004\t0000\t0102\tnote\n")
    patches.apply(fw, patches.parse_tsv(tsv))
    rep = verify.explain(stock, fw, [tsv])
    assert rep.ok and rep.hits == {"patch note": 2}
    off = patches.code_offset(fw, 0, 0x306C004, 2)
    fw.buf[off + 1] = 0xFF  # still inside the patch, but not what it declares
    rep = verify.explain(stock, fw, [tsv])
    assert rep.mismatched == [off + 1] and rep.unknown == [] and not rep.ok


def test_manifest_roundtrip(tmp_path):
    verify.write_manifest(tmp_path, "1.17", [tmp_path / "p.tsv"], "my-walkman")
    m = verify.read_manifest(tmp_path)
    assert m["version"] == "1.17" and m["mod"] == "my-walkman" and m["patches"][0].endswith("p.tsv")
    assert verify.read_manifest(tmp_path / "nope") is None
