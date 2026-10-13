# Audit prompt: walkman-firmware

Paste this into a fresh session in `C:\Users\edmun\Projects\walkman-firmware`. Read
`docs/HANDOFF.md` first for context, then do the audit below. Report findings ranked by
severity, each with the file and line or the firmware address, what is wrong, how you confirmed
it, and the fix. Confirm against the bytes or the code before reporting; a claim that does not
survive a check is not a finding. Do not flash the player during the audit.

## 1. Reverse-engineering claims in NOTES.md

For every address, offset and structure stated in NOTES.md, verify it against
`extract/cab/Data/Device/RKNANOFW.IMG` (stock 1.01) with capstone or the Ghidra project. In
particular:

- The installer's checks (section 9 `0x306cc96`): confirm magic, size rule, backup-header compare,
  no CRC check, header written last. Confirm `Firmware.problems()` and `expected_file_size`
  implement exactly the installer's rule.
- The settings block at SRAM `0x4b70`: confirm `+0x4e` is the volume and `+0x4a` gates the cap,
  by listing every reader and writer of those offsets. Say what writes `+0x4a` if you can find it.
- The two volume patches (`mods/volume-limit/patches.tsv`): confirm each old byte sequence, that
  the new encoding is the intended unconditional branch to the stated target, and that the
  branch target is the "byte != 0" path. State what the unpatched section 34 clamp and the
  section 10 volume-to-13 reset handler are triggered by.
- font12 layout: 8,439-entry map, glyph base `0x55dd8a`, 424 glyphs, width table `0x56054a`,
  rows 0 and 11 blank. Check the table length by finding the last non-0xFFFF entry and that
  glyph 423's last row is clean. Check how the firmware reads the width (find the code).
- Picture drawing: `0x3062400`, `0x3062212`, `0x3062250`, `0x3062110`, `0x306200a`,
  `image_select` `0x306c9cc`, ImageLogicAddress `0x4b5c`. Confirm the entry read is
  `base + 0x20 + 16*index` and the blit chunking.
- Home menu: section 17 table `0x302302c`, entry layout `{id, icon, string}`, the eight count
  immediates in `menus.COUNT_SITES` (confirm each encoding formula in `menus._encode` against the
  bytes), the 3x2 slot positions, and that the dispatch uses the `id` field, not the row index.
- The SCSI commands in `flash.py` against the decompiles in `work/ghidra-dll/startfw*.c`.
- Anything in NOTES.md that is stated as fact but was only inferred: mark it as such.

## 2. Code

`src/nwe39x/*.py`, `scripts/*.py`, `ghidra/*.java`, `tests/`. Look for:

- Correctness: off-by-one in offsets, wrong endianness, Thumb encoding mistakes (`patches.thumb_b`,
  `menus._encode`), `code_offset` for addresses on section boundaries, `FILE` pseudo-section
  bounds, `Firmware.write` bounds, CRC coverage, the version regex finding exactly one match.
- Safety: can `build` or `flash` ever write an image the installer would reject or that changes
  bytes outside what `manifest.json` explains? Can `flash` run against a non-player drive letter?
  Does `modspec` allow include cycles or paths outside the mod tree? Does any path skip
  `Firmware.problems()`?
- Font import: does `set_image` for font12 write the width byte for every imported glyph, and
  keep it for empty glyphs? Does `sheet_from_ttf` with `--baseline` clip anything? Are font16
  widths consistent with Sony's rule?
- Themes: does `accent()` leave reds and blues alone for the pictures that matter (alert rings
  015-024, boot rings 000-014)? Does `mono()` handle the gradient bars without banding?
- Tests: what is not covered (flash on Linux, `modspec.apply` ordering, `verify` with
  overlapping regions, `menus.hide` with two entries, `theme hue` with missing `--hue`)? Add tests
  where a bug is plausible; don't add tests that only restate the code.
- Style: dead code (anything unused after the manifest refactor), docstrings that disagree with
  behaviour, CLI help that is out of date, README commands that no longer run.

## 3. Process

- Is anything in `.gitignore` too broad or too narrow (Sony's files, user photos, generated
  assets, the Ghidra project)? Is anything committed that should not be?
- Is `docs/HANDOFF.md` accurate against the repo and NOTES.md?

## Output

A ranked list. For each: severity (bricks the player / wrong result / misleading note / cleanup),
location, evidence, fix. Then a short paragraph on what you did not check and why. Apply only
the cleanup-level fixes yourself; propose the rest.
