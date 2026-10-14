# NW-E394 firmware notes (2026-10-12)

Source: Sony's `NW-E390_V1_01.exe` (7,669,504 bytes, sha256 `870121a0...c809a4`), firmware
1.01 for NW-E393/E394/E395. Never executed; unpacked as data.

Early entries name `tools/*.py` scripts from before the `nwe39x` CLI; those jobs are now
`nwe39x unpack`, `images`, `bootscreen`, `build` and `restore`.

## Unpacking

1. The .exe is an InstallShield SFX. One real CAB at offset `0x485d8` (7,365,077 bytes);
   carve it and run Windows `expand.exe -F:*`.
2. The CAB holds `SoftwareUpdateTool.exe`, `Data\App\WmFwUpdater.dll`,
   `Data\Device\SWUpdate.xml` and `Data\Device\RKNANOFW.IMG` (13,631,492 bytes).
   `SWUpdate.xml` says the updater writes the image to `\RKNANOFW.IMG` on the player.
3. `python -I tools/rknanofw.py RKNANOFW.IMG extract/fw` splits the image;
   `python -I tools/imageres.py extract/fw/imageres0.bin extract/images` dumps the UI images.

## RKNANOFW.IMG

- Rockchip **RKnano** SoC with Rockchip's own RTOS ("RKnano SDK 1.0"), not Linux.
- RKnanoFW format, as parsed by Rockbox `utils/rknanoutils/rkboottool`. Header: date 2016-10-14,
  vendor "Rockchip", magic `RKnanoFW` at 0x1f8, size field 0xc98000.
- **Not encrypted.** Stages 0-2 are empty; stage 3 (the whole OS, 5.6 MB) is plain. rkboottool's
  RC4 key is only needed for stages 0-2 and BOOT entries.
- Checksum: the last 4 bytes (LE) are Rockchip's `boot_crc` (the CRC table in rkboottool) over
  everything before them. Verified: `0xe3ae9225`. A modified image can be re-signed.
- After `size` (0xc98000) there is a 0x68004-byte tail: a copy of the header, padding, then the CRC.
- Stage 3: base 0x03050000, 146 code/data sections, but only 21 distinct run addresses, so it is an
  overlay scheme (79 sections run at 0x0). Load into Ghidra as ARM (Cortex-M, Thumb) with overlays.

## Resources

| Blob | Format |
|---|---|
| font0 | "font12": u16 code-point map, glyphs, widths, then the CJK part (see below) |
| font1 | "font16": 33-byte records indexed directly by code point, no map (`fonts.py`) |
| gbk0 | Chinese GBK font - not decoded |
| strtbl0 | 13 languages of 181 records (2,353 slots, 1,766 distinct UTF-16LE strings); `\` is a line break; German first |
| imageres0 | `ROCK26IMAGERES`, 234 images: 16-byte entries {u16 w,h,x,y; u32 size, offset}, RGB565 **big-endian** |

Images include the boot screen ("For Music Lovers, By Music Lovers"), the "POWER OFF / See You
Later" screen, icons, digits, the EQ graph, and factory test patterns (color bars, diagonals),
so there is probably a hidden test mode.

Firmware strings worth following: "Old version is: %d", "New version is: %d", "Version is not
changed", "Firmware upgrade", "Firmware downgrade", "Firmware update failed!/success!".

## Patching

`tools/patch_image.py IN.IMG 44 picture.png OUT.IMG` swaps the boot screen (image 44, 128x160)
and rewrites the CRC. Verified on a test build: only the 40,960 pixel bytes and the CRC change.
`tools/bootscreen.py` makes a 128x160 RGB565-accurate picture from a photo.

## Sony's updater

`WmFwUpdater.dll` has two paths: MTP (`CWmFwUpdateWorkerMtp`) and USB mass storage
(`CWmFwUpdateWorkerMsc`) with SCSI pass-through (`CSptIoCtl`), so it probably copies the image
and then sends a vendor SCSI command to make the player reboot into the update. The PC tool
compares versions (`VERSION_EQUAL`, `VERSION_OLDER`, `VERSION_NEWER`, `VERSION_CHECK_PASS`;
"Firmware version is not correct. ( pc:"%s" != device:"%s" )").

## Flashing (worked 2026-10-12, with a custom boot screen as the first test mod)

- Copying `RKNANOFW.IMG` to the player's root and power-cycling does nothing: the player
  never reads the file on its own (it was still there afterwards).
- The install routine (stage 3 section 9, runs at 0x306ca48) opens `RKNANOFWIMG`, checks the
  `RKnanoFW` magic, that the file size is the header size plus a 16 KiB margin rounded up to 1 MiB, plus 4, and that the
  backup header at `size` equals the main header, then writes NAND and deletes the file.
  **It has no version check.** It only runs when Sony's tool triggers it over USB.
- Sony's PC tool refuses an equal version, so `tools/build_update.py` sets 1.02 in both
  `SWUpdate.xml` and the firmware's `<firmwareversion>` (the only version string in the image).
- Steps: `uv run --no-project --with pillow python -I tools/build_update.py picture.png out/updater`,
  then run `out\updater\SoftwareUpdateTool.exe` with the player plugged in.
- Result: new boot screen, player reports 1.02, music and playlists untouched, image file deleted.
  For the next mod, use `--version 1.03` (the tool needs a newer version each time).
- Backup of the player's files from before the flash: `backup/`.

## Sony's tool and its false failures (2026-10-12, solved)

- Stock image re-versioned as 1.03 (`nwe39x restore --version 1.03`): the tool said "software
  update has been failed ... unknown error. Error Code:" (blank), yet a 1 s poll of the drive showed
  it unmount (player rebooting into the installer), then remount 4 s later reporting **1.03** with
  `RKNANOFW.IMG` consumed. The install worked; the tool's final check failed.
- Restoring stock over a mod works (cat 1.02 -> stock 1.03).
- An earlier attempt (the test mod as 1.03 over 1.02) also said "failed" and did NOT install
  (still 1.02, no file left on the drive). Not yet explained; the drive was not being polled then.
- The test mod as 1.04, polled twice a second from launch: the tool quit after 10 s without ever
  copying the image. Same build again with **nothing touching the drive**: installed (custom boot screen, strings
  and power-off screen), and the tool still ended with the "failed" message.
- Conclusions: (1) other processes reading the drive make the tool fail before it copies
  (probably it needs exclusive access to send its SCSI command); (2) the closing "failed" message
  is the tool's own post-install check and appears even on clean successful installs.
- M2 checkpoint passed: mod 1.02 -> stock 1.03 -> mod 1.04.
- Cause of the false "failed": the image has a second version, BCD major/minor/rev u16s at header
  0x4 (and in the backup header), which the Unit Information screen shows (it said 1.01 on the
  1.04 build). Setting it as well (1.05 build): Sony's tool reported **success**, the player reports
  1.05. So the tool's post-install check compares the package version with the header version.
- Windows sees the player only as USB mass storage (`SONY WALKMAN 1.00` SCSI inquiry, never
  changes), so the tool's post-install version check must use the capability XML or a vendor
  SCSI command. Answered: the vendor command `FC 00 20 "dbmn"` (REQUEST DEVINFO), which reports
  the header version; see "Flashing without Sony's tool" below.

## font12 advance widths (2026-10-12, found while checking the font-test photos; in fonts.py since)

Why Consolas lost its `l` and `i` and clipped `o`/`b` on the player: font0 keeps each glyph's
advance in a **separate 1-byte-per-glyph table after the bitmaps**, which the sheet importer never
writes, so replacement glyphs are clipped to Sony's widths (the diag12 photo shows the solid `A`
block cut to ~8 px, Sony's `A` width 7 plus spacing). The TrueType rendering itself is fine.

Layout of font0 (blob at `0x559b9c`): a u16 table of **8,439** entries (U+0020-U+20F6, last real
entry `table[8438] = 423`), then **424 glyphs** of 24 bytes at `0x55dd8a` = blob + `0x41ee`, right
after the table (the reader at section 0 `0x3053ef8` adds `movw r1, #0x41ee`; fonts.py once put the
base 2 bytes later, which drew every glyph a row high, and has used `0x55dd8a` since). Rows 0 and 11
are blank in most of Sony's glyphs (363 and 355 of 424), not all: `(`, `g`, `p` and others use
them. Then **424 width bytes at `0x56054a`** (`width[glyph]`, 2-12; rightmost ink + 1 for every
inked glyph except `1`, U+0031: width 6, ink ends at column 3; space = 5), then the CJK structures
from `0x5606f2`. fonts.py writes `width[glyph] = rightmost ink + 1` on import and reads it back for
`preview`/`width()`.

## font12 CJK part (2026-10-13; in fonts.py as `font12` / `font12zh`)

After font0's width table (blob `0x559b9c`, offsets relative to it):
- `+0x6b56` (`0x5606f2`): **bank 1**, 31,682 glyph records of 24 bytes (same row format as the
  Latin glyphs). `+0xc0586` (`0x61a122`): **bank 2**, the same 31,682 glyphs in the same order. They
  differ in 7,262 records: Chinese Han forms (直, 骨), and some sit a row lower (一).
- `+0x179fb6` (`0x6d3b52`): u16 index of all 65,536 code points, 0 = no glyph, else record + 1,
  strictly increasing with the code point. It covers 31,682 characters: Latin-1/Greek/Cyrillic
  symbols from legacy CJK charsets, U+2010-U+2FFB, 526 of U+3000-U+33FF (punctuation, kana, ...),
  all of CJK Extension A (6,582) and of U+4E00-U+9FA5 (20,902), the 2,350 KS X 1001 Hangul
  syllables (of 11,172; font16 has them all), 173 private-use characters U+E766-U+E864,
  compatibility ideographs, and full-width forms to U+FFE6.
- Then 155,694 bytes, almost all zero (455 non-zero), not decoded.

Readers in section 0: `0x3053fac` index, `0x3053f84` bank 1 glyph, `0x3053f5c` bank 2 glyph
(alongside `0x3053f40` Latin table, `0x3053ef8` Latin glyph, `0x3053f20` Latin width). Lookup
`0x30540ac(sel, &cp, out, ...)`: Latin table first (U+0020-U+20F6, after mapping a few
punctuation code points), then Thai checks, then the CJK index; a missing CJK glyph draws record
`0x23d`. `sel` = 0 when settings `+0x4c` (UI language) is 11 or 12 (Chinese) selects bank 2, else
bank 1 (`0x3061464`). CJK glyphs advance 12, halfwidth katakana U+FF61-U+FF9F 6; there is no width
table for them.

## Volume limit (2026-10-12, from disassembly of stage 3 v1.01; patches not yet tested on a player)

Thumb-2 via capstone, addresses are run addresses (`section` = stage 3 section index). A Gemini
read-only pass the same evening found the right routine in section 35 but misread it; what follows
was checked against the bytes.

- **Settings block at SRAM `0x4b70`** (literal in 30+ sections). `+0x4e` is the master volume,
  0-30. `+0x4a` is a byte that gates the limit: `0` means limited. Section 13 at `0x306c6d2` also
  uses it (values 0/1 vs 3 vs other) to pick a date layout, so it is not a plain on/off AVLS
  flag; a region/destination code fits. Where it comes from: see "Settings sector" below. `+0x355` is a u16, the selected home
  entry: read and written with `ldrh.w`/`strh.w [rX, #0x355]` off the block in 11 sections,
  including the home menu (section 17 `0x306c4aa`). `+0x353` (a byte) is the demo-mode flag.
- **The cap is 17** (`0x11`), applied when `+0x4a == 0`:
  - boot, section 10 `0x306ea96`: if the byte is 0, call `0x3064b66` and clamp volume > 17 to 17;
  - section 0 `0x3064b66`: adds elapsed time to a u32 counter at `+0x57` (cumulative listening
    time, guarded by a once-flag at `0x63f4`); also called from sections 17, 24, 25;
  - section 0 `0x3064b8e`: "may the volume exceed 17?" - returns 0 only when the byte is 0, the
    volume is above 17 and `+0x56` is set. Called from the volume-key handler in section 24
    (`0x306e2a2`, `0x30708fe`, `0x307126e`), which pops the dialog with string 63
    "Check the\volume level" (string 150 is the "AVLS (Vol. Limit)" menu item);
  - section 10 `0x306eb16`: a handler that resets the volume to 13 and sets `+0x56` - probably the
    rollback when the counter expires; not traced further;
  - section 34 `0x306c7d8`: a handler (also reached via a pointer in section 6's data) that clamps
    volume > 18 to 17 regardless of the byte, then shows something via section 57.
- **Settings sector (2026-10-13): the only writer of `+0x4a` is the boot-time settings loader.**
  The earlier search looked for immediate-offset stores off a known `0x4b70`; the loader holds the
  block in `sl`, so it was missed. Section 1 `0x306d176` (called from section 1 `0x306c746`):
  - reads 1 KiB from storage with `0x30677d6(0, sp+8, 0x400)` (the read twin of the save
    `0x3067848`) into a buffer in `r4`;
  - checks a CRC-8 (`0x3067b36(ptr, nbits)`, table at `0x3004528`, init `0x0f`, length `0x1b08`
    bits = 865 bytes) against the u32 at buffer `+0x361`, and the magic words `"SAVE"` at `+0`
    and `"INFO"` at `+0x35d`;
  - if either check fails, fills buffer `+0x4b..+0x3ff` with `0xff` but **keeps bytes
    `0..0x4a`**, so `+0x4a` survives a settings reset (a factory-provisioned field, not a user
    setting);
  - copies fields into the live block (`sl = 0x4b70`); at `0x306d4b4`:
    `ldrb r1, [r4, #0x4a]; strb r1, [sl, #0x4a]`, then `cmp r1, #5; movhi r1, #6; strbhi` -
    values 0-5 are kept, anything above (including erased `0xff`) becomes 6.
  - The save paths (section 0 `0x30678b0`, section 1 `0x306da0a`) recompute the CRC and write
    the live block back with `0x3067848`, so the byte round-trips unchanged.
  So the byte lives in the player's settings storage, not in `RKNANOFW.IMG`: no resource edit can
  change it, and nothing in stage 3 sets it from the UI. The two code patches in
  `mods/volume-limit` remain the way to lift the cap. Checked with a capstone scan of every
  section for stores resolving to `0x4bba` (it finds the known `+0x355` writers), every
  `strb/strh/str ... #0x4a]`, and every call with `r0 = 0x4b70`.
- **Section 35 `0x307890e` is not the cap.** It runs only when EqMode == 5 and lowers the EQ's
  `max_DbGain` from 12 dB to 2 dB in steps as the volume rises (a harder ladder when the byte is
  0), i.e. headroom so a boosted EQ does not clip. Patching it out makes nothing louder.
- The ACodec block is at `0x40090000` (section 0 literal pools around `0x3052168`, `0x30523c8`);
  which register is what is unknown, so analog gain is not something to touch blind.
- `mods/volume-limit/patches.tsv` flips the two decision points (sections 0 and 10) to the
  "byte != 0" path; the section 34 clamp is left in as a commented second step. `nwe39x build`
  applies `patches.tsv` from a mod (old bytes must match), `nwe39x diff --patches` names them.

## Flashing without Sony's tool (2026-10-12, works: `nwe39x flash`)

`WmFwUpdater.dll` (CWmFwUpdateWorkerMsc / CWmFwScsiCmd / sptioctl::CSptIoCtl, decompiled in
`work/ghidra-dll/startfw*.c`) copies `RKNANOFW.IMG` to the drive root, opens `\\.\X:` and sends a
12-byte vendor CDB through `IOCTL_SCSI_PASS_THROUGH_DIRECT`. Two commands, both
`FC 00 <op> 'd' 'b' 'm' 'n' ...`:

- op `0x20`, 0x80 bytes in: **REQUEST DEVINFO** -> `"DEVINFO"`, size, vendor `SONY`, model
  `NW-E394`, version `1.1010` (header BCD major.minor + rev), serial. This is the version Sony's
  tool compares with its package after the install (the "false failed" of 1.04: header said 1.01).
- op `0x04`, no data: **START FW UPDATE** -> the player unmounts within 2 s, installs, deletes the
  file and is back in about 15 s.

Both work without elevation. `nwe39x devinfo` is the read-only check; `nwe39x flash --updater
out/x` copies, sends, and waits. The player itself never checks the version, so with this there is
no need to count upwards any more (the builds still do, so Unit Information tells them apart).
Gemini's note that `FC 20` is the reboot command was wrong: `FC 20` is DEVINFO, `FC 04` reboots.

## Hidden modes (2026-10-12: looked for a factory test mode; found a demo mode instead)

- **The test patterns (pictures 087-091: color bars with crosshair, blue/green/red/gray ramps)
  are not referenced anywhere in stage 3**: not by index (as an immediate, a byte/u16/u32 table or
  a window of values), not by their entry or data offsets. The only matches for 87..91 are a
  coefficient table in section 122. Pictures the UI does use (044 boot, 083 power off) are not
  referenced by number either, so the UI reaches pictures through something indirect; but the
  five patterns never appear together in any table. Most likely they are leftovers of Rockchip's
  reference design, or driven by a factory tool over USB with code that is not in this image.
- **The vendor SCSI handler is not in stage 3 either**: no `dbmn`, no `0xFC` dispatch (the one
  `cmp #0xfc` ladder in section 31 is a UTF-8 lead-byte decoder). USB mass storage and the
  `FC 04` install trigger therefore live in the boot loader / NAND loader outside this image,
  which is also why the trigger works whatever firmware is installed.
- **Demo mode** (strings "Enter Demo mode" / "Exit Demo mode", section 0 at `0x30603f4`): a
  store-demo mode, not a test mode. Toggled by a secret sequence of **15 key events**: for key
  events with `[event+0x10] == 2`, a counter at `[event+3]` advances while each key `[event+8]`
  equals `table[counter]` and resets otherwise (`0x3060434`: `ldr r2, =0x100; ldr.w r2, [r2, r0,
  lsl #2]; cmp r2, r1`); at 15 (`cmp r0, #0xf` at `0x3060402`) the flag at settings `+0x353`
  flips. The table is in SRAM at `0x100`, which no section's data or bss covers, so its contents
  come from outside the image (boot loader parameters?). Entering (`0x30647ca`) sets volume 13,
  settings `+0x4f = 4`, `+0xa2/+0x9d/+0x9a = 1`, `+0xa7 = 6`, `+0x9c = 0`, then re-initializes
  playback; exiting restores. Correction (2026-10-13): NOPing the `bne` at `0x3060444` would not
  work; the increment is under `itt eq`, so a mismatch would neither advance nor reset. The key
  state is RAM `0x4b14` (written by section 0 `0x30602dc`): `+8` current key, `+0xc` previous,
  `+0x10` ticks held (the press counts at 2), `+4` event (key | `0x1..` press, `0x2..` long at 50,
  `0x3..` repeat, `0x4..`/`0x5..` release). Key 1 held 200 ticks raises event `0xc`, the long-press
  shutdown, so key 1 is OPTION/PWR. Counting also needs `[0x4b3c] == 1`, **HOLD on** (`0x30601c4`
  reads GPIO port 1 pin 7 via `0x3055aae(1, 7)` and reports `0x41000000` HOLD on / `0x42000000`
  off as key codes), and byte `[0xa30] == 0`, the current app index (`0x3066ad8` names 0-16:
  MainMenu, MediaLib, MediaBro, Music, Radio, Picture, Record, Ebook, Browser, Systemset, USB,
  Charge, MDB, M3UBRO, M3UWIN, PICBRO, PhotoMenu; set at `0x3066b6c`). So: home screen, HOLD on.
  The routine runs from the key poll at `0x306062e` when byte `[0x55a4]` is set.
  **Verified on the player (1.26, 2026-10-13)**: home screen, HOLD on, 15 taps of OPTION/PWR
  enters demo mode ("DEMO" shown); repeating it leaves. This confirms key 1 = OPTION/PWR.
- **Correction (2026-10-13): low RAM is section 2's data.** Section 2's data runs at `0x3090000`
  (0x4b0a bytes, bss to `0x3097e4c`) and the code addresses it through a mirror at `0x0`, so RAM
  `0x100`, `0xa30` and the like *are* in the image (stage 3 section 2 data + offset). The demo key
  table at `0x100` is **`0x10` x5, `0x2` x5, `0x20` x5** (then 0): Sony's sequence, with HOLD on, on
  the home screen. Key codes (`0x306024a`): the ADC ladder gives `0x80` (<0xa4), `0x40`, `0x20`,
  `0x10`, `0x8`, `0x4` (to 0x3d7); `0x1` (OPTION/PWR, verified) and `0x2` are the two non-ADC
  keys. **Buttons (read on the player with our key-test app, 2026-10-13):** the four-way pad is
  ▲ `0x40`, ▼ `0x8`, ◀◀ `0x10`, ▶▶ `0x20`, center (▶II) `0x2`; BACK/HOME `0x80`,
  OPTION/PWR `0x1`; volume − `0x100` (not from the ADC ladder: the key poll passes `0x100` through
  next to the HOLD codes). Volume + is `0x4` by the firmware's own volume handler (`0x3067cdc` turns
  `0x10000004` into flag `0x12`, volume up, and `0x10000100` into `0x13`); not yet pressed on the
  player. (A first reading took the volume − button for the pad's ▼.)
  So Sony's demo sequence is **◀◀ x5, center x5, ▶▶ x5** (HOLD on, home screen). Events seen:
  press `0x1…` on the way down, release `0x4…` on the way up. `mods/demo-mode` turns `cmp r2, r1` at `0x306043c` into `cmp r1, #1` (`8a42` ->
  `0129`): 15 presses of key 1 toggle it. Enter/exit go through the debug print `0x3068888`,
  so a serial port, if there is one, should log them.
- Other hidden strings: "Shutdown because power on with hold key!!!", "Long press back key: Back
  to home screen", "Long press power key: Shutdown", the "Os idle Wakeup by X key" set. Nothing
  that names a test, factory, aging or service screen, in the code or in the UI strings.

## Apps and the overlay loader (2026-10-13)

- The current app index is the byte at RAM `0xa30` (section 2 data `+0xa30`); `0x3066b6c(idx, msg)`
  switches app (called from about 150 places), `0x3066b3a` loads it: `0x3066eda(section, 7)` reads
  that stage 3 section's 32-byte header from NAND and loads its code, data and bss, then the app's
  descriptor is called through `+0x14` (start) and `+0x10` (stop).
- Per-app tables in section 2 data: names via `0x3066ad8`, descriptors at `0xa34`, overlay section
  at `0xa78`:

  | idx | name | section | | idx | name | section |
  |---|---|---|---|---|---|---|
  | 0 | MainMenu | 17 | | 9 | Systemset | 34 |
  | 1 | MediaLib | 18 | | 10 | USB | 10 |
  | 2 | MediaBro | 20 | | 11 | Charge | 7 |
  | 3 | Music | 24 | | 12 | MDB | 6 |
  | 4 | Radio | 25 | | 13 | M3UBRO | 29 |
  | 5 | Picture | 13 | | 14 | M3UWIN | 31 |
  | 6 | Record | 26 | | 15 | PICBRO | 32 |
  | 7 | Ebook | 27 | | 16 | PhotoMenu | 33 |
  | 8 | Browser | 28 | | | | |

- **Record and Ebook are compiled out**: sections 26 and 27 have zero bytes of code, data and bss,
  their descriptors are 0, and no code switches to index 6 or 7. Launching one would call through a
  null descriptor. Browser (28) is the folder browser and in normal use.

## Our own app in slot 7 (2026-10-13, works: first a hello app, now `mods/launcher`)

- `scripts/build_app.py` compiles `app.c` with arm-none-eabi-gcc (WSL) for `-mcpu=cortex-m3
  -mthumb`, code linked at `0x306c4a4`, data at `0x3023010` starting with the 7-word descriptor
  `{0, 0, event, keys, draw, start(msg), stop}` (dispatcher `0x3066a08`: a nonzero return from
  `event`/`keys` switches app; `draw` runs each pass while `0x305458e()` is true).
- Code and data go in the free space after the last blob (file `0xc94200`; blobs end at
  `0xc9411e`, `size` is `0xc98000`). Section 27's header points there: the overlay loader
  `0x3066eda` copies from `stage + (va - base)` in 512-byte NAND reads with no bounds check, and
  zeroes bss. Data is reloaded every time the app opens.
- The app table entry for app 7 (section 2 data `0x3090a50`) gets the descriptor address; home's
  Photos handler (section 17) skips its photo-count check (`0x306c5a2`) and switches to app 7
  (`0x306c5ac`).
- Verified on the player (1.27, 1.28): text and pictures draw, key events arrive through
  `0x306067c`, short OPTION/PWR returns home via `app_switch(0, msg)`, and USB still switches to
  "Connected USB" from inside the app (the core handles USB and power-off, not the app).
- `verify.os_changes` also counts the free space after the last blob, so `flash` needs
  `--allow-code-patches` for an image with app code.

## The launcher and .BIN apps (2026-10-13, works on the player as 1.29)

- `mods/launcher` (slot 7) lists `\APP0.BIN`..`\APP9.BIN` and runs one: `file_open("\\",
  "APPn    BIN", "R")` (section 0 `0x3057fda`: 8 handle slots, resolves the folder with
  `0x3057a60`, finds the 8.3 entry with `0x3057842`, refuses folders, mode with `W` opens for
  writing), `file_size` `0x305867e`, `file_read(buf, len, h)` `0x305824a` (through a 512-byte
  stack buffer, any destination), `file_close` `0x30581c8`. These are general FAT calls, not
  installer-only: section 0 itself uses the same family at boot to write DevLogo.fil and friends.
- Apps load at `0x306d000`, up to `0x4e00` bytes (`apps/sdk/nwapp.h`): the app overlay region runs
  from `0x306c4a4` to `0x3071e64` (end of section 24, the largest app); section 14 starts there.
  While an app is in front, nothing else loads into that region: section 0's own overlay loads are
  section 8 at boot (`0x30612f6`) and the audio code's sections 142-145 at `0x1000000` (called
  from section 35 via `0x3067f30`). Sub-overlays in the region (19, 21-23, 12, 30, 39-41) are
  loaded by the apps that use them.
- The core has hardware divide (155 `udiv`/`sdiv` in section 0), so `-mcpu=cortex-m3` code works.
- The folder browser (section 28) lists files with a cluster-based API instead: `0x30594d4(dir
  cluster, type)` counts files, `0x305888c` counts folders, `0x3059628(dir, index, ?, buf)` gets a
  name. Not used yet; a real directory listing would start there.

## Timing and the screen timeout (2026-10-13, for apps)

- The system tick is the Cortex-M SysTick at 10 ms (`0x3060160(10)` writes LOAD at `0xE000E014`;
  "System tick initial... period: 10ms"). Handlers are installed at runtime: both vector tables
  (section 0 code and RAM `0x0` in section 2 data) hold only default handlers. Soft timers are
  records in section 2 data such as RAM `0x140` `{0, period 1, 0, callback, next}` (the key poll
  `0x306062e`). Nothing in the firmware reads SysTick's COUNTFLAG, so `apps/sdk` counts ticks by
  polling it.
- The screen timeout lives at RAM `0x55a4`: `+0` screen off, `+1` hold count, `+4` last activity.
  `0x3062dc0` (every dispatcher pass) turns the backlight off once the timeout from settings
  `+0x50` passes, unless the hold count is nonzero; `0x3062ea8` does it (sets `+0`, event flag
  `0x2f`), `0x3062e72`/`0x3062e80` turn it back on. While `+0` is set the dispatcher skips the
  app's `draw` (`0x305458e`) and the key poll runs the wake/demo routine `0x3060384` instead of
  the normal one. `0x3062d8e` is "activity" (last activity = now), `0x3062db6` holds the screen on,
  `0x3062d9c` releases it; Sony's apps call these themselves (the picture viewer holds it). A game
  that ignored this froze after one timeout: the first snake build.
- `0x3067cdc(ev)` is the global key handler (not a "keys blocked" check): volume ± (`0x10000004`,
  `0x10000100`) become event flags `0x12`/`0x13`, HOLD `0x800` shows its icon; the home menu calls
  it with each event before its own handling.

## Brick insurance (2026-10-12)

- **What the installer checks** (section 9, `work/ghidra/out/install_routine.c`): magic, file size
  = roundup(size + 16 KiB, 1 MiB) + 4, backup header equal to the main header. **Not the CRC.**
  So a corrupted body with a good header is written as-is; the CRC only protects against our
  own tooling mistakes (`Firmware.problems()` refuses to save or flash a bad one). Order of
  writes: 8 KiB of 0xFF at the start, the body from 0x2000 on, then the first 8 KiB (header)
  last, then `fw_write_image_maybe`. A power cut mid-install therefore leaves no valid header,
  which is the case the boot loader should treat as "no firmware".
- **Boot-ROM USB loader** (Rockbox `utils/rknanoutils/rkload/rkloader.c`, copy in
  `reference/rockbox/`): the RKnano boot ROM enumerates as USB **071b:3226** and takes code by
  vendor control transfer, bRequest 12, wValue 0, wIndex 1137, 4,096-byte chunks, payload
  RC4-scrambled with the rkboottool key plus a 16-bit CRC. How this player enters that mode is
  still unknown: nothing in stage 3 (the loader is in NAND and is not part of RKNANOFW.IMG).
  **Tried 2026-10-12**: player off, one key held while plugging USB in, six keys in six clean
  cycles watched on the USB bus; every time the normal 054c:0b83 drive came back and the player
  showed its "Connected USB" screen, never 071b:3226. So no key at plug-in enters the loader.
  The remaining trigger is presumably a NAND without a valid firmware header (the boot ROM's own
  fallback), which cannot be tested safely. Treat a failed install as unrecoverable; keep every
  build inside the installer's checks and `flash`'s verification; no patches that touch boot.
- **Stock restore kept ready**: `out/stock-restore` (stock 1.01 image as 1.13); `nwe39x flash
  --updater out/stock-restore` puts the player back. Rebuild with `nwe39x restore -o
  out/stock-restore --version N` when the version falls behind (cosmetic only: the installer
  ignores versions).
- **Refusal test passed** (2026-10-12): stock image with one byte of the backup header changed
  (CRC fixed, so only the installer's own check trips), copied and started with `nwe39x flash`'s
  command. The player unmounted after 1 s, came back after 34 s (vs 15 s for a real install, so
  it did reboot into the installer), still on 1.12 with the same DEVINFO, and the image file was
  deleted. So the pre-write checks work from our flasher and a rejected image costs nothing.

## Picture drawing and the UI layout (2026-10-12, Ghidra: `ghidra/Xrefs.java`, `work/ghidra/out/pictures.c`)

Pictures are drawn by index after all, through two section 0 routines (names now in
`AnnotateRknano.java`):

- `draw_picture_at(index, x, y)` at `0x3062400` and `draw_picture(index, dx, dy)` at `0x3062212`
  (the stored x,y of the entry plus an offset). Both read the 16-byte entry at
  `ImageLogicAddress + 0x20 + 16*index` and call `blit_picture_rows(x, y, w, h, offset)` at
  `0x3062110`, which streams the RGB565 rows from NAND in 512-byte chunks into
  `lcd_blit(x, y, w, h, 16, rows)` (`0x306200a`, the function the notes used to call
  `lcd_fill_rect_maybe`; with bpp 1 it draws glyph bitmaps). `ImageLogicAddress` is RAM `0x4b5c`,
  set by `image_select(n)` in section 1 (`0x306c9cc`), which reads the firmware header and takes
  the offset of `imageres[n]`; the resource reader `0x3066c34(0x30000, offset, len, buf)` reads
  the firmware image region of NAND at that offset. The earlier searches failed because the
  index is a plain first argument and sits in registers or tables far from the call.
- **List screens** (music menu in section 18 `0x306cc70`, the same geometry in sections 20, 22,
  25, 28, 29, 31, 33, 34): title bar = picture 107 at (0,14); rows are 26 px tall starting at
  y=30; per row: separator 133 at y+25, highlight bar **109** on the selected row at (0,y), icon
  at (6, y+3), text at x=28 with a 12 px font. So the highlight look is one picture (109), and the
  gold bars 106/108/110-117 are the same bar for other screens.
- **The music menu table** is at section 18 data `0x3023010`: six entries of `{u16 picture, u16
  string id}` = (119, 56 All Songs), (118, 58 Album), (120, 57 Artist), (125, 59 Genre),
  (129, 60 Playlists), (124, 61 Folder). Editing it reorders the menu, swaps icons, or (with the
  row count byte it is drawn from) hides entries. Other menus use the same shape in their own
  section's data.
- Status bar: 188 is the background at (0,0); 216/217 play/pause at x=0; 191/198 at (14,0);
  219 at (26,0); 218 AVLS at (88,2); 215 HOLD at (16,0). Now-playing: 179 and the 149-159
  arrows at y=134; album-art frame 139 with the Walkman logo 185 or 229 (refresh) in a grid.
  Charging: battery 96 at (29,39), 97/98 at (8|64,110). EQ screen (section 34): 102, 104, 101.
- The test patterns 087-091 are still never drawn, which confirms they are unused.
- **Home menu** (section 17, `work/ghidra/out/home.c`): a 3x2 icon grid over the table at section 17
  data `0x302302c`, six entries of `{u16 id, u16 icon, u16 string}`: (0, 59, Photos), (1, 57,
  Music), (2, 55, FM Radio), (3, 63, Settings), (4, 61, Playlists), (5, 53, "Go to song playback
  screen"). Icons are drawn by `0x3062250` (index -> stored x,y) in a loop to 6, the selected one as
  icon+1; each icon pair carries its grid slot in its picture entry ((6|46|86, 33|78)). OK dispatches on the
  cursor *slot*, not the id: `ldrsb r1, [0x3023050]` then `tbb [pc, r1]` at `0x306c594` over a
  6-byte table at `0x306c598`, with handlers in id order (slot 3 `0x306c600` sends message 9 with
  record 110, the Settings tree). `menu hide` reorders that table too; before 1.19 it did not, so
  Settings in slot 2 opened FM Radio. Apps return with message 0 and the *id* to highlight. The home
  screen stores it as the slot at `0x306c4b6` (`ldrb r0,[r5]; ldr r1,=0x3023050; strb r0,[r1]`).
  Since 1.20, `menu hide` turns those first 4 bytes into `bl` to a 28-byte id -> slot helper placed
  in the dead FM handler (`0x306c5d8`, 40 bytes, unreachable once the dispatch table skips it). No
  other section 17 code branches there. Other overlays share the address, but they are not loaded
  with section 17. The count 6 lives in eight Thumb-1 immediates
  (`0x306c882` .. `0x306c922`). `nwe39x menu hide FM` rewrites the table, those constants and the
  kept icons' slots; verified on the player as 1.13.
- The home icons are opaque (RGB565): each pair has the backdrop (picture 105, 128x160 at 0,0)
  behind its own slot baked into its 36x36 square. Their borders match the backdrop in their own
  slot (91-100% of border pixels) and nowhere else (0-1%), so a moved icon showed as a faint square.
  `build` now re-fits the backdrop behind moved icons (`menus.rebase_moved_icons`, from the
  built, possibly themed, backdrop): mean border error 213/56/73 -> 0/0/4 for no-fm.

## Settings menu: a tree in the string table (2026-10-13)

The Settings menu is not a table in stage 3. It is the string table's record headers (strtbl0):
each 242-byte record starts with 21 u16s (0xffff = none) `{id, parent, index in parent, first
child, prev, next, value, child count, children[13]}`, then the 200-byte text. Record 110
"Settings" is the root, with children 111 Music, 128 Photo, 135 FM Radio, 142 Sleep Timer,
148 Common and 167 Language Settings. Menu nodes have value 0xffff. Leaves carry a value 0..52,
the option's setting index, numbered in tree order (113 Normal = 0 ... 180 = 52; 149 Unit
Information = 26, 163 Brightness = 37, 165/166 Reset/Format = 38/39 are leaves that act). Menu
siblings are linked by prev/next. Leaves chain across parents (119 On prev = 117). The headers
are byte-identical in all 13 language blocks; records below 110 are a flat chain.

- Only section 34 (the Settings screen) reads them, through `read_record_header(rec, buf)` at
  section 0 `0x3061f08` (callers s34 `0x306c592`, `0x306cc18`, `0x306d16a`). It uses `+0x2`
  (index in parent) to place the cursor, `+0xe` (count; more than 5 rows scroll), and the
  children. It special-cases record ids 121 Equalizer (`0x306d18e`, the EQ screen) and 167
  Language (`0x306cc40`). Leaves go through `0x306c908`. At `0x306c57c` it builds a u16 list of
  `0xa8 + byte` from a byte table (count at RAM `0x550e`), probably the languages on offer.
- The string fetch `0x3061c82` and `0x3061f08` index the table at RAM `[0x4b58]` + 0x36 with a
  language stride of 181 records when settings `+0x53` is nonzero and 172 records when it is zero.
  Probably for another SKU; unknown.
- `nwe39x menu settings` prints the tree. `nwe39x menu settings-hide NAME` rewrites the parent's
  children and count, the kept siblings' indices, and the prev/next links around the hidden entry,
  in every language. Options cannot be hidden (their row is their value). `mods/no-fm-settings`
  drops FM Radio Settings.
- Correction: `0x305cce6` is not a list drawer. It is a task callback in section 0's 7-pointer task
  table (data `0x300450c`). List screens copy small constant templates from section 0's code
  (`0x3069d54`: the music OPTION menu 112/118/121/85 and the Music list 56-61 with icons
  119/118/120/125/129/124; `0x3069df4`, `0x306a01c`, ...) to the stack in chunks and point r5 at
  them, which is why the earlier scans found nothing.

## Text color and the gold letter-jump letter (2026-10-13)

- **Text color is a RAM struct at `0x551c`**: u16 foreground `+0`, u16 background `+2`, u16 flags
  `+4` (bit 1 swaps fg/bg, bit 0 = transparent background). The glyph path of `lcd_blit`
  (`0x306200a` with bpp 1) reads it through the literal at section 0 `0x30623f0` and plots each
  pixel with `0x3061db0`. `draw_text(rect, rect, utf16, align)` at section 0 `0x3061774` (align
  0 left, 1 right, 2 center) draws in whatever color is there; callers store the color first,
  `strh` to `[0x551c]` (section 20 resets it to white `0xffff` after). 0x551c is in the literal pools
  of sections 0, 1, 13, 14, 17-20, 22, 24, 25, 28, 29, 31, 33, 34. Colors stored: white
  `0xffff` (most), gray `0x7bcf` (sections 20, 25), `0x8410` (section 34), and gold `0xf5e0` once.
- **The letter jump** is drawn by section 20's song-list routine `0x306e128` (code
  `0x306f096`..`0x306f59c`): picture 106 at (0,30) and separator 133 at (0,54), then three labels
  with `draw_text(..., 2)`: previous letter in (14,36)-(34,48), current letter in (51,36)-(71,48),
  next letter in (88,36)-(108,48). Labels are `A`-`Z`, `0-9` and `etc.`. Neighbors are white
  `0xffff` or gray `0x7bcf` (stored from `r4`, `movw r4, #0x7bcf` at `0x306f0c6`).
- **The gold is one instruction**: section 20 `0x306f234` `movw r0, #0xf5e0` = bytes `4f f2 e0 50`
  (file offset `0x4be8e0` in the stock 1.01 image), followed by `strh.w r0, [sl]` (sl = 0x551c)
  and the `draw_text` call at `0x306f244`. `0xf5e0` is RGB (246,190,0). No other section has
  `movw #0xf5e0`. The earlier immediate scan looked for other gold values and missed it.
- A recolor is a 4-byte patch of the `movw` immediate (T3: `f240 | i<<10 | imm4`,
  `imm3<<12 | rd<<8 | imm8`, little-endian halfwords). The preset accents mapped through
  `themes.py` give: ice `0x05de` -> `40f2de50`, sony-blue `0x029e` -> `40f29e20`, purple
  `0x901e` -> `49f21e00`, mint `0x07af` -> `40f2af70`, rose `0xf00f` -> `4ff20f00`, matrix
  `0x47a6` -> `44f2a670`, mono `0xf7be` -> `4ff2be70` (all checked with capstone as
  `movw r0, #...`). Patch line: `20	306f234	4ff2e050	40f2de50	letter-jump letter color`.
  It would be the first code patch in a theme, so a themed build would need
  `--allow-code-patches`. Not added to any mod yet.

## Not known yet
- Brick recovery: Rockbox `utils/rknanoutils/rkload` loads code over USB in the RKnano boot-ROM
  mode. How to enter that mode on this player is unknown (possibly a test point inside).
