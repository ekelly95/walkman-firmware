# NW-E394 firmware notes (2026-10-12)

Source: Sony's `NW-E390_V1_01.exe` (7,669,504 bytes, sha256 `870121a0...c809a4`), firmware
1.01 for NW-E393/E394/E395. Never executed; unpacked as data.

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
| font0, font1 | starts with a u16 identity table 0,1,2,... (glyph map?) - not decoded |
| gbk0 | Chinese GBK font - not decoded |
| strtbl0 | 13 languages, 1,388 UTF-16LE strings; `\` is a line break; German first |
| imageres0 | `ROCK26IMAGERES`, 234 images: 16-byte entries {u16 w,h,x,y; u32 size, offset}, RGB565 **big-endian** |

Images include the boot screen ("For Music Lovers, By Music Lovers"), the "POWER OFF / See You
Later" screen, icons, digits, the EQ graph, and factory test patterns (colour bars, diagonals),
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

## Flashing (worked 2026-10-12, "For Cat Lovers, By Cat Lovers" boot screen)

- Copying `RKNANOFW.IMG` to the player's root and power-cycling does nothing: the player
  never reads the file on its own (it was still there afterwards).
- The install routine (stage 3 section 9, runs at 0x306ca48) opens `RKNANOFWIMG`, checks the
  `RKnanoFW` magic, that the file size is the header size rounded up to 1 MiB plus 4, and that the
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
- An earlier attempt (cat-lovers mod as 1.03 over 1.02) also said "failed" and did NOT install
  (still 1.02, no file left on the drive). Not yet explained; the drive was not being polled then.
- Cat-lovers mod as 1.04, polled twice a second from launch: the tool quit after 10 s without ever
  copying the image. Same build again with **nothing touching the drive**: installed (cat, Meowsic,
  nap-time power-off screen), and the tool still ended with the "failed" message.
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
  SCSI command. Find out in M5 (`WmFwUpdater.dll`, USB capture).

## font12 advance widths (2026-10-12, found while checking the font-test photos; not yet in fonts.py)

Why Consolas lost its `l` and `i` and clipped `o`/`b` on the player: font0 keeps each glyph's
advance in a **separate 1-byte-per-glyph table after the bitmaps**, which the sheet importer never
writes, so replacement glyphs are clipped to Sony's widths (the diag12 photo shows the solid `A`
block cut to ~8 px, Sony's `A` width 7 plus spacing). The TrueType rendering itself is fine.

Layout of font0 (blob at `0x559b9c`), corrected: a u16 table of **8,439** entries (U+0020-U+20F6,
last real entry `table[8438] = 423`), then **424 glyphs** of 24 bytes starting at `0x55dd8a` (2 bytes
earlier than fonts.py assumes, so every glyph is really one row lower: row 0 and row 11 blank), then
**424 width bytes at `0x56054a`** (`width[glyph]`, 2-12; rightmost ink + 1 for 406 of 418 ASCII/Latin
glyphs; space = 5), then the CJK structures from `0x5606f2`. Fix: on font12 import, write
`width[glyph] = rightmost ink + 1`; read it back for `preview`/`width()`; shift the glyph base by -2.

## Volume limit (2026-10-12, from disassembly of stage 3 v1.01; patches not yet tested on a player)

Thumb-2 via capstone, addresses are run addresses (`section` = stage 3 section index). A Gemini
read-only pass the same evening found the right routine in section 35 but misread it; what follows
was checked against the bytes.

- **Settings block at SRAM `0x4b70`** (literal in 30+ sections). `+0x4e` is the master volume,
  0-30. `+0x4a` is a byte that gates the limit: `0` means limited. Nothing in stage 3 writes it
  with an immediate offset, so it probably arrives with the block from flash (a region or
  destination byte?). Section 13 at `0x306c6d2` also uses it (values 0/1 vs 3 vs other) to pick a
  date layout, so it is not a plain on/off AVLS flag.
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
- **Section 35 `0x307890e` is not the cap.** It runs only when EqMode == 5 and lowers the EQ's
  `max_DbGain` from 12 dB to 2 dB in steps as the volume rises (a harder ladder when the byte is
  0), i.e. headroom so a boosted EQ does not clip. Patching it out makes nothing louder.
- The ACodec block is at `0x40090000` (section 0 literal pools around `0x3052168`, `0x30523c8`);
  which register is what is unknown, so analog gain is not something to touch blind.
- `mods/volume-limit/patches.tsv` flips the two decision points (sections 0 and 10) to the
  "byte != 0" path; the section 34 clamp is left in as a commented second step. `nwe39x build`
  applies `patches.tsv` from a mod (old bytes must match), `nwe39x diff --patches` names them.

## Not known yet

- The USB command Sony's tool sends to start the install (would allow flashing without Sony's tool).
- Brick recovery: Rockbox `utils/rknanoutils/rkload` loads code over USB in the RKnano boot-ROM
  mode. How to enter that mode on this player is unknown (possibly a test point inside).
