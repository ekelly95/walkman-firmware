# NW-E390 firmware formats

Everything here was measured on Sony's `NW-E390_V1_01.exe` (firmware 1.01, NW-E393/E394/E395).
All integers are little-endian unless a field says otherwise. Offsets in `0x…` are bytes.

```
NW-E390_V1_01.exe  (InstallShield self-extractor, Authenticode-signed by Sony)
└── CAB at 0x485d8 (7,365,077 bytes, 18 files)
    ├── SoftwareUpdateTool.exe          Sony's GUI
    ├── Data/App/WmFwUpdater.dll        COM server that talks to the player (MTP or USB mass storage)
    ├── Data/Device/SWUpdate.xml        package version and the models it accepts
    └── Data/Device/RKNANOFW.IMG        the firmware (13,631,492 bytes)
        ├── header (0x200)
        ├── stage 3: the whole OS, ARM Thumb, 146 overlay sections
        ├── font0, font1, gbk0           glyph data
        ├── strtbl0                      UI text, 13 languages
        ├── imageres0                    234 UI pictures, RGB565
        ├── backup header (0x200) at `size`
        ├── padding to a 1 MiB boundary
        └── CRC (4)
```

## 1. Unpacking the updater

The `.exe` contains four `MSCF` signatures. Only the one at `0x485d8` has a plausible header
(`cbCabinet` at +8 = 7,365,077, `cFiles` at +28 = 18); the others are false matches inside
compressed data. Carve `cbCabinet` bytes from there and extract with `expand.exe -F:*` (Windows)
or `cabextract`.

`SWUpdate.xml` lists the package version (`<Common><Version>1.01</Version>`), the path the
image is written to on the player (`<SWPackageWritePathName>\RKNANOFW.IMG`) and the accepted
models (`<DevicePropertyProductInfo>NW-E393/E394/E395`).

## 2. RKNANOFW.IMG header (0x200 bytes)

The layout matches Rockbox's `rknano_header_t` (`utils/rknanoutils/rkboottool`).

| Offset | Size | Field | Value in 1.01 |
|---|---|---|---|
| 0x000 | 2 | year, BCD | `0x2016` |
| 0x002 | 1 | day, BCD | `0x14` |
| 0x003 | 1 | month, BCD | `0x10` (2016-10-14) |
| 0x004 | 6 | version: major, minor, rev as BCD u16s | `1`, `01`, `10`. The Unit Information screen shows major.minor |
| 0x00a | 6 | unknown | |
| 0x010 | 32 | vendor, ASCII | `Rockchip` |
| 0x030 | 32 | model, ASCII | `RKnano SDK 1.0` |
| 0x050 | 4 + 4×8 | stage table: count, then {offset, size} | 4 entries |
| 0x074 | 4 + 10×8 | font table | 2 entries |
| 0x0c8 | 4 + 5×8 | GBK font table | 1 entry |
| 0x0f4 | 4 + 10×8 | string table table | 1 entry |
| 0x148 | 4 + 10×8 | image resource table | 1 entry |
| 0x19c | 4 + 10×8 | unknown table | 1 empty entry |
| 0x1f0 | 4 | padding | 0 |
| 0x1f4 | 4 | `size`: payload length incl. header | `0xc98000` |
| 0x1f8 | 8 | magic | `RKnanoFW` |

Blob offsets are from the start of the file. In 1.01:

| Blob | Offset | Size |
|---|---|---|
| stage0-2 | 0x200 | 0 (empty) |
| stage3 | 0x0000200 | 5,609,884 |
| font0 | 0x0559b9c | 1,834,980 |
| font1 | 0x0719b80 | 2,169,862 |
| gbk0 | 0x092b786 | 1,835,008 |
| strtbl0 | 0x0aeb786 | 569,480 |
| imageres0 | 0x0b7680e | 1,169,680 |

**Scrambling.** rkboottool descrambles stages 0-2 with RC4 (key
`7C 4E 03 04 55 05 09 07 2D 2C 7B 38 17 0D 17 11`, one keystream per blob) and leaves stage 3
plain. In this firmware stages 0-2 are empty, so **nothing is encrypted**.

## 3. What the player checks before installing

From the install routine (stage 3, section 9, code at `0x306cc96`):

1. open `RKNANOFWIMG` (the 8.3 name of `\RKNANOFW.IMG`); read the first 0x200 bytes;
2. the magic at 0x1f8 must be `RKnanoFW`;
3. the file size must equal `((size + 0x103fff) & ~0xfffff) + 4`, i.e. `size` plus at least
   16 KiB, rounded up to 1 MiB, plus 4 (`0xd00004` for 1.01);
4. the 0x200 bytes at offset `size` must equal the header (a backup copy);
5. write the image to NAND in 0x2000-byte chunks with a progress bar, verify, delete the file.

There is **no version check and no signature**. The CRC is the only integrity check in the file.

## 4. Tail and CRC

After the payload (`size` bytes) comes the backup header, zero padding to the size in §3, and a
4-byte CRC. The CRC is Rockchip's `boot_crc`: CRC-32, polynomial `0x04C10DB7`, MSB-first, initial
value 0, no final XOR, over every byte before it, stored little-endian. 1.01: `0xe3ae9225`.

## 5. Stage 3: the operating system

```
u32 base            0x03050000
u32 count           146
count × section     8 × u32: code_va, code_pa, code_sz, data_va, data_pa, data_sz, bss_pa, bss_sz
```

`*_va` locate bytes in the stage file (`file offset = va - base`); `*_pa` are run addresses. The
146 sections use only **21 distinct code run addresses**: 79 of them run at 0x0, others share
addresses in the 0x0306xxxx range. It is an overlay scheme: the RTOS loads a section into its
slot when its code is needed. Examples:

| Section | Runs at | Size | Contents |
|---|---|---|---|
| 0 | 0x03050000 | 0x1a9a8 | resident core; data at 0x03004000 |
| 1 | 0x0306c4a4 | 0x1ad8 | system config check ("Old version is: %d") |
| 9 | 0x0306ca48 | 0x560 | firmware-file install routine |
| 10 | 0x0306ea8c | 0x3a0 | "Firmware Upgrade..." screen |

The firmware's capability XML (`<model>NW-E390 Series</model>`,
`<firmwareversion>1.01</firmwareversion>`, …) is stored in stage 3. It is the image's only
version string: the player writes it to `\default-capability.xml` on its drive and reports it as
its version; raising it is what makes Sony's tool accept a package (how the tool reads it is
not yet known). The USB mass-storage inquiry string is
`SONY    WALKMAN         1.00` and never changes.

## 6. strtbl0: UI text

```
u16 languages                   13
u32 offset[languages]           from the start of the blob; first is 0x36
languages × 181 × record:
    u16 id                      0..180
    20 × u16 links              neighbouring record ids, 0xffff = none
    200 bytes text              UTF-16LE, NUL-terminated, zero-filled (99 characters max)
```

Each language block is 43,802 bytes (181 × 242). Language order: de, en, es, fr, it, pl, pt, ru,
tr, ja, ko, zh-Hans, zh-Hant (the same order as the language menu, records 168-180). A backslash
in the text is a line break. Examples (en): 11 `Music`, 32 `Firmware:`, 115 `Shuffle`.

## 7. imageres0: UI pictures

```
char magic[16]                  "ROCK26IMAGERES  "
u32  count                      234
u8   zero[12]
count × entry:
    u16 width, height
    u16 x, y                    position on the 128×160 screen
    u32 size                    width × height × 2
    u32 offset                  from the start of the blob
```

Pixels are **RGB565, big-endian**, rows top to bottom. Notable pictures: 044 the boot screen
(128×160), 083 the power-off screen (128×160), and full-screen factory test patterns (colour bars,
diagonal stripes).

## 8. fonts

`font0` and `font1` start with an identity table of u16 values (0, 1, 2, …), probably a code-point
to glyph map; `gbk0` is a Chinese GBK font. Not decoded yet (milestone M7).
