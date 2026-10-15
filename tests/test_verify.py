"""verify.code_changes: everything in the payload that is not a resource blob counts as code."""

from conftest import make_image
from nwe39x import verify
from nwe39x.rknanofw import Firmware


def test_code_changes_cover_everything_but_resources():
    # The synthetic image has no gaps between blobs; a gap would count as code, like the free tail.
    stock = Firmware.from_bytes(make_image(stage0=bytes(range(64)), free=64))
    built = Firmware.from_bytes(bytes(stock.buf))
    stage0 = stock.blob("stage", 0).offset + 5
    stage3 = stock.blob("stage", 3).offset + 3
    string = stock.blob("strtbl").offset + 2 + 4 * 13 + 2
    picture = stock.blob("imageres").offset + 0x20
    tail = stock.blobs_end + 8
    assert tail < stock.size_field
    for off in (stage0, stage3, string, picture, tail):
        built.buf[off] ^= 0xFF
    assert verify.code_changes(stock, built) == [stage0, stage3, tail]


def test_version_string_is_not_code():
    stock = Firmware.from_bytes(make_image())
    built = Firmware.from_bytes(bytes(stock.buf))
    off = bytes(stock.buf).index(b"1.01</firmwareversion>")
    built.buf[off:off + 4] = b"1.02"
    assert verify.code_changes(stock, built) == []
