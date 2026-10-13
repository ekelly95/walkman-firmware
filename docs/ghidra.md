# Loading the firmware into Ghidra

The NW-E390's operating system (stage 3 of `RKNANOFW.IMG`) is ARM Thumb-2 code for a Cortex-M
class core, but Ghidra cannot open it directly: it is a table of 146 sections, and most of them
share run addresses.

## The overlay scheme

Each section has a code part, a data part and a bss part, each with a run address (`*_pa`). The
RTOS keeps section 0 (the core: file system, display, debug log) resident at `0x03050000`, and
swaps the other sections into a few shared slots when their code is needed. The 146 sections make
199 memory blocks but only 25 fit side by side; 174 overlap something else.

Ghidra's answer to this is overlay blocks: same addresses, separate address spaces.
`ghidra/LoadRknanoStage.java` gives the first block to claim an address range a normal block and
turns every later overlapping block into an overlay named after its section (`s009_code`,
`s041_data`, …). Calls from an overlay into section 0 resolve to the normal block, which is
how the firmware is linked: each overlay carries its own copies of small helpers (section 9 has
its own `memcmp` and `memset`) and calls the core for everything else.

## Running it

Requirements: Ghidra 12 and a JDK 21.

```
nwe39x unpack NW-E390_V1_01.exe
nwe39x blobs work/blobs
analyzeHeadless work/ghidra NWE390 -import placeholder.bin -overwrite \
    -processor ARM:LE:32:Cortex -loader BinaryLoader -loader-baseAddr 0xF0000000 \
    -scriptPath ghidra \
    -preScript LoadRknanoStage.java work/blobs/stage3.bin \
    -postScript AnnotateRknano.java work/ghidra/out
```

`placeholder.bin` is any small file; the pre-script removes it and builds the real memory map
before auto-analysis runs. Then open the `NWE390` project in Ghidra's GUI.

`AnnotateRknano.java` names the functions identified so far and writes
`work/ghidra/out/install_routine.c`, the decompiled install routine, as a check that the map is
right. Names ending in `_maybe` are inferred from how they are called.

## Known functions

| Where | Address | Name | Evidence |
|---|---|---|---|
| core | 0x3068888 | `debug_printf` | called with the `\n…` debug strings |
| core | 0x3057fda | `file_open_maybe` | called with `RKNANOFWIMG`, returns -1 on failure |
| core | 0x305824a | `file_read_maybe` | (buffer, 0x200, handle) before the magic check |
| core | 0x305867e | `file_size_maybe` | result compared with the expected image size |
| core | 0x30586e0 | `file_seek_maybe` | seeks to `size` before reading the backup header |
| core | 0x305a896 | `file_delete_maybe` | deletes `RKNANOFWIMG` after the install |
| core | 0x3058086 | `file_rename_maybe` | turns the internal `DEFAULT XML` into `default-capability.xml` |
| core | 0x306200a | `lcd_fill_rect_maybe` | draws the progress bar, one 1×8 column at y=151 per step |
| core | 0x30628d4 | `lcd_flush_maybe` | follows every progress-bar draw |
| core | 0x3060f30 | `watchdog_kick_maybe` | once per 8 KiB chunk while flashing |
| s009 | 0x306cc96 | `fw_install_from_file` | the install routine, see `docs/format.md` §3 |

## What the decompiled install routine shows

After the checks in `docs/format.md` §3, the routine:

1. writes an erased (0xFF) 8 KiB chunk where the image's first chunk goes;
2. copies the rest of the file to NAND in 8 KiB chunks, drawing the progress bar;
3. writes the real first chunk (with the header) **last**, so an interrupted flash leaves no
   valid header behind;
4. hands over to `fw_write_image_maybe`, closes and deletes `RKNANOFW.IMG`, and recreates
   `default-capability.xml` from the firmware's built-in copy (which is why the player's reported
   version follows the image).

A run of the scripts on firmware 1.01 builds 199 blocks and finds 1,942 functions in about a
minute of auto-analysis.
