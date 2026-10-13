from PIL import Image

from nwe39x import imageres, themes
from nwe39x.rknanofw import Firmware


def test_mono_greys_gold_but_keeps_red():
    img = Image.new("RGB", (2, 1))
    img.putpixel((0, 0), (255, 180, 0))  # gold
    img.putpixel((1, 0), (220, 20, 20))  # red
    out = themes.mono(img)
    r, g, b = out.getpixel((0, 0))
    assert r == g == b  # grey
    r, g, b = out.getpixel((1, 0))
    assert r > 200 and g < 40 and b < 40  # still red (HSV round trip may move it a notch)


def test_hue_shift_keeps_greys_and_moves_colours():
    img = Image.new("RGB", (2, 1))
    img.putpixel((0, 0), (128, 128, 128))
    img.putpixel((1, 0), (255, 0, 0))
    out = themes.hue_shift(img, 120)
    assert out.getpixel((0, 0)) == (128, 128, 128)
    r, g, b = out.getpixel((1, 0))
    assert g > 200 and r < 60 and b < 60  # red -> green


def test_generate_writes_only_changed_pictures(image_bytes, tmp_path):
    fw = Firmware.from_bytes(image_bytes)
    changed = themes.generate(fw, tmp_path, lambda im: im, skip=set())
    assert changed == [] and not list(tmp_path.iterdir())
    changed = themes.generate(fw, tmp_path, lambda im: Image.new("RGB", im.size, (255, 255, 255)), skip={1})
    assert changed == [0]
    assert [p.name for p in tmp_path.iterdir()] == [imageres.pictures(fw)[0].filename]
    assert imageres.import_dir(fw, tmp_path) == [0]


def test_accent_moves_gold_only():
    img = Image.new("RGB", (3, 1))
    img.putpixel((0, 0), (255, 170, 0))   # gold accent
    img.putpixel((1, 0), (220, 20, 20))   # red alert
    img.putpixel((2, 0), (20, 40, 220))   # blue ring
    out = themes.accent(img, 275)
    r, g, b = out.getpixel((0, 0))
    assert b > 200 and r > 100 and g < 60      # violet
    r, g, b = out.getpixel((1, 0))
    assert r > 200 and g < 40 and b < 40       # still red
    r, g, b = out.getpixel((2, 0))
    assert b > 200 and r < 40                  # still blue


def test_every_preset_runs():
    img = Image.new("RGB", (4, 4), (255, 170, 0))
    for name, (_, fn) in themes.PRESETS.items():
        assert fn(img).size == (4, 4), name
