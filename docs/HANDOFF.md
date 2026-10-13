# Handoff: walkman-firmware (nwe39x)

*Development notes, written to brief an AI coding session on the project; users want the README.*

Paste this into a new session. It is the state of the project as of 2026-10-13 and how to work on it.

## What this is

Firmware modding tools for Sony's NW-E393/E394/E395 Walkman (Rockchip RKnano SoC, Rockchip's own
RTOS, ARM Thumb-2). Repo: GitHub `ekelly95/walkman-firmware`, branch `main`; work from its root.
Python 3.12, `uv`, package `nwe39x` in `src/`, CLI `uv run nwe39x ...`. Tests:
`uv run pytest -q` (80 pass). **NOTES.md is the knowledge base**:
every reverse-engineering fact, with addresses, lives there; read it first and keep it current.

The player (one unit, serial in `nwe39x devinfo`) is on **1.24 = `mods/my-walkman`**: matrix
theme (everything green, alert rings included) with the letter-jump letter green too
(`letter-jump-color`), Terminus 12 in the menu font, matching boot/power-off screens, volume
cap off. FM Radio is back in both menus (the user uses it; `no-fm`/`no-fm-settings` stay as
opt-in examples). Sony's stock image is 1.01; our versions only count upward so Unit
Information tells builds apart (the installer itself never checks versions).

## Daily commands

```
uv run nwe39x status / devinfo                       # connected player, firmware, DEVINFO over SCSI
uv run nwe39x build --mod mods/my-walkman -o out/x   # version = player's + 1 unless --version
uv run nwe39x diff out/x/Data/Device/RKNANOFW.IMG    # names every changed byte; reads manifest.json
uv run nwe39x restore                                # Sony's image, re-versioned, in out/stock-restore (flash needs it)
uv run nwe39x flash --updater out/x                  # checks, asks "flash", copies, sends START FW UPDATE, waits (~15 s)
```

`flash` refuses, before touching the player, an image with unexplained or mismatched bytes
(`--force` skips only that), one that changes the OS itself (stage 3: byte patches such as
volume-limit and menu hiding; pass `--allow-code-patches` once checked; themes, fonts, strings and
pictures never need it), and any flash without a stock build in `out/stock-restore`. Then it asks
for "flash" to be typed. An assistant passes `--yes` only after the user has approved that flash.

Sony's files live in `extract/cab/` (ignored by git; `nwe39x unpack NW-E390_V1_01.exe` recreates
it from the updater .exe in `download/`). Generated assets (theme pictures, glyph sheets,
no-fm patches, clean boot screens) are ignored too; each mod's README says how to regenerate.

## Mods and manifests

A mod is a folder with `mod.toml` (`src/nwe39x/modspec.py`): `include` (other mods, applied
first), `theme` (preset name), `images`, `fonts`, `strings`, `patches`. `mods/README.md` lists
them. `patches.tsv` lines are `section<TAB>run address<TAB>old<TAB>new<TAB>note`; `section` may
be `file` for an absolute offset. Old bytes must match or the build refuses. `build` writes
`manifest.json` beside the image; `flash` refuses unexplained bytes unless `--force`, and OS
changes unless `--allow-code-patches`.

## Hard rules

- **No brick recovery exists.** Tested: no key held at USB plug-in enters the RKnano boot-ROM
  loader (071b:3226). The installer (stage 3 section 9) checks magic, size rule and backup header,
  not the CRC, and writes the header last. Nothing in the tools stops a patch from breaking boot:
  `problems()` and `diff` check the image's shape and that every changed byte is declared, not
  what a patch does. So patch pre-UI code only when needed and minimally (the volume-limit
  section 10 patch is one, running on the player now), check each encoding with capstone, never
  touch the entry vector, the loader or the installer (section 9), never bypass
  `Firmware.problems()` or the flash gate, and keep `out/stock-restore` current.
- Flashing is the user's hardware; ask before anything that is not a normal build-and-flash.
- Commit style: short title, body says what and why, `Co-Authored-By` line. Push to `origin main`.
- Don't commit Sony's files, the user's photos, or generated assets. `.gitignore` already covers them.

## Firmware facts you will need (details and addresses in NOTES.md)

- `RKNANOFW.IMG`: header 0x200, blobs stage3 (the OS, 146 overlay sections, base 0x3050000),
  font0 (12 px), font1 (16 px), gbk0, strtbl0 (13 languages), imageres0 (234 RGB565-BE pictures).
  `rknanofw.py` parses it; `Section` has `code_va/pa`, `data_va/pa`. Many sections share run
  addresses: always name the section with an address. Ghidra project `work/ghidra/NWE390` has
  the overlays loaded; `ghidra/Xrefs.java` (`callers@0x...`, `@0x...`, `range@a-b`, overlay form
  `s017_code::0306c4a4`) and `ghidra/DecompileByString.java` run headless:
  `analyzeHeadless work/ghidra NWE390 -process -noanalysis -scriptPath ghidra -postScript Xrefs.java OUT.c args...`
  For quick scans, capstone (Thumb) over section bytes in Python is faster than Ghidra.
- Settings block in SRAM at `0x4b70`: `+0x4e` volume (0-30), `+0x4a` region/limit byte (0 =
  limited), `+0x353` demo-mode flag, `+0x355` selected home entry id.
- Pictures: `draw_picture_at(index, x, y)` `0x3062400`, `draw_picture(index, dx, dy)` `0x3062212`,
  stored-position variant `0x3062250`, blit `0x306200a`; list screens use 26 px rows from y=30,
  highlight = picture 109, separator 133, title bar 107. Event flags, not widgets:
  `0x3066950` set / `0x306696c` test-and-clear / `0x3066992` clear / `0x30669b0` test.
- Home menu: section 17 data `0x302302c`, six `{u16 id, u16 icon, u16 string}`, count hard-coded in
  eight Thumb immediates (`menus.py`). Music menu: section 18 data `0x3023010`, `{picture, string}`.
- font12: 8,439-entry map, 424 glyphs of 24 bytes from `0x55dd8a`, then one advance byte per glyph
  at `0x56054a` (the player clips to it; the importer writes rightmost ink + 1).
- Strings: `strtbl.py`; `nwe39x strings export` for ids (en 110 Settings, 111 Music Settings,
  128 Photo Settings, 135 FM Radio Settings, 142 Sleep Timer Settings, 148 Common Settings,
  167 Language Settings).
- SCSI: `FC 00 04 "dbmn"` = START FW UPDATE, `FC 00 20 "dbmn"` + 0x80 in = DEVINFO
  (`flash.py`, Windows pass-through, no elevation). The handler is in the NAND loader, not stage 3.

## Open items, in the order I would take them

1. **Settings menu**: done, verified on the player as 1.20. The menu is a tree in the string
   table's record headers (NOTES.md); `nwe39x menu settings` / `settings-hide`;
   `mods/no-fm-settings` is in my-walkman. Hiding FM from the home menu also needed the OK
   dispatch table and the returning cursor fixed (both now in `menu hide`; FM had opened from
   Settings since 1.13).
2. **Volume follow-up on the device**: does anything still pull the volume down after a long
   session or a headphone replug? If yes, enable the commented section 34 line in
   `mods/volume-limit/patches.tsv`. Also: what writes settings `+0x4a`.
3. **Fonts**: done. `fonts from-ttf --advance N`; `fonts from-bdf` (Terminus BDF regular imports
   pixel-identical to the TTF sheet on the player); font12's CJK part is mapped (`--font 12` /
   `12zh`, ranges kana/cjk/hangul/...; see NOTES). The player keeps Terminus regular, ink + 1.
4. **Whole-language string import** (one TSV per language) in `strtbl.py`.
5. **Gold letter-jump highlight**: found, not patched. Section 20 `0x306f234`
   `movw r0, #0xf5e0` (`4ff2e050`) sets the text color (RAM `0x551c`) for the current letter
   of the song list's letter jump; NOTES "Text color" has the encodings for each preset.
   `mods/letter-jump-color` carries the patch (matrix green `0x47a6`, `44f2a670`) as an
   opt-in mod, so the themes stay picture-only; a build that includes it needs
   `--allow-code-patches`.
6. Later: EQ tables in section 35 (`max_DbGain` ladder at `0x307890e`), the demo-mode key
   sequence (RAM `0x100`, populated outside the image), FM section.

## Session notes worth keeping

- Gemini's earlier analysis got the font cause wrong (it was the width table, not rasterization)
  and the SCSI opcode wrong (`FC 20` is DEVINFO, `FC 04` reboots); don't trust its conclusions
  without checking bytes.
- Pictures 087-091 (test patterns) are never drawn; there is no factory test mode in stage 3.
- The user prefers short, factual replies, likes to see a preview image before flashing, and
  tests on the device between steps. Flash only after `diff` is clean.
