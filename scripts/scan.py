"""Minimal binwalk: list known signatures and long ASCII strings in a binary, without executing it."""

import re
import sys
from collections import Counter
from math import log2

SIGNATURES = {
    b"PK\x03\x04": "zip local file",
    b"PK\x05\x06": "zip end of central dir",
    b"MSCF": "Microsoft CAB",
    b"7z\xbc\xaf\x27\x1c": "7z archive",
    b"ISc(": "InstallShield CAB",
    b"\x1f\x8b\x08": "gzip",
    b"BZh9": "bzip2",
    b"\xfd7zXZ\x00": "xz",
    b"\x5d\x00\x00\x80\x00": "lzma (raw, common props)",
    b"hsqs": "squashfs (LE)",
    b"UBI#": "UBI image",
    b"\x27\x05\x19\x56": "u-boot uImage",
    b"\x7fELF": "ELF",
    b"MZ": None,  # too common to report
    b"UPG": "Sony UPG?",
    b"<?xml": "XML",
    b"ANDROID!": "Android boot image",
}


def entropy(chunk: bytes) -> float:
    if not chunk:
        return 0.0
    counts = Counter(chunk)
    n = len(chunk)
    return -sum(c / n * log2(c / n) for c in counts.values())


def main(path: str):
    data = open(path, "rb").read()
    print(f"{path}: {len(data)} bytes")
    hits = []
    for sig, name in SIGNATURES.items():
        if name is None:
            continue
        for m in re.finditer(re.escape(sig), data):
            hits.append((m.start(), name))
    hits.sort()
    print(f"\n{len(hits)} signature hits (first 60):")
    for off, name in hits[:60]:
        print(f"  0x{off:08x}  {name}")
    print("\nentropy per 256 KiB block (8.0 = compressed/encrypted):")
    block = 256 * 1024
    for i in range(0, len(data), block):
        print(f"  0x{i:08x}  {entropy(data[i:i + block]):.3f}")
    words = re.findall(rb"[\x20-\x7e]{12,}", data)
    keep = [w.decode() for w in words if re.search(
        rb"(?i)nw-?e|walkman|firm|upg|\.bin|\.img|\.fw|\.dat|version|sony|update|key|aes|des", w)]
    print(f"\n{len(keep)} interesting strings (first 80):")
    for w in keep[:80]:
        print("  " + w[:160])


if __name__ == "__main__":
    main(sys.argv[1])
