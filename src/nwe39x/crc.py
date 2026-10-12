"""Rockchip's image checksum: an MSB-first CRC-32 with polynomial 0x04C10DB7, initial value 0 and
no final XOR (boot_crc in Rockbox's rkboottool). RKNANOFW.IMG stores it little-endian in its last
4 bytes, computed over everything before them."""


def _table(poly: int = 0x04C10DB7) -> list[int]:
    table = []
    for i in range(256):
        c = i << 24
        for _ in range(8):
            c = ((c << 1) ^ poly if c & 0x80000000 else c << 1) & 0xFFFFFFFF
        table.append(c)
    return table


TABLE = _table()


def rk_crc(data: bytes) -> int:
    c = 0
    table = TABLE
    for b in data:
        c = ((c << 8) & 0xFFFFFFFF) ^ table[((c >> 24) ^ b) & 0xFF]
    return c
