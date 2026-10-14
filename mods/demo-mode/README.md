# demo-mode

Sony's firmware has a store-demo mode ("Enter Demo mode" / "Exit Demo mode" in its debug log),
toggled by a secret sequence of 15 key presses. The sequence itself is a table in SRAM at `0x100`
that nothing in `RKNANOFW.IMG` fills, so its keys are unknown. This mod replaces the table lookup
with a fixed key: **press key 1 fifteen times in a row** to enter demo mode, and fifteen more to
leave. Any other key resets the count.

**Slide HOLD on and go to the home screen first**: presses only count while HOLD is on and the
home menu (`MainMenu`) is the current app. Key 1 is very likely OPTION/PWR: holding key 1 for 200
ticks (about 2 s) sends the long-press shutdown, so tap, don't hold.

One code patch, section 0 `0x306043c`: `cmp r2, r1` (`8a42`, the pressed key vs `table[counter]`)
becomes `cmp r1, #1` (`0129`). Background: NOTES.md, "Hidden modes".

What entering does (section 0 `0x30647ca`): volume 13, settings `+0x4f = 4`, `+0xa2/+0x9d/+0x9a =
1`, `+0xa7 = 6`, `+0x9c = 0`, then playback restarts. Leaving restores. The flag lives in the
settings block, which the firmware saves, so demo mode may survive a power cycle (untested).

The two gates, both in the stock code: the word at RAM `0x4b3c` is the HOLD switch state (set to 1
by `0x30601c4`, which reads GPIO port 1 pin 7 and reports `0x41000000` HOLD on / `0x42000000` HOLD
off as key codes), and the byte at RAM `0xa30` is the current app index (0 = `MainMenu`; names
from `0x3066ad8`). For any 15 presses instead of key 1, use new bytes `8042` (`cmp r0, r0`); the
HOLD gate still keeps normal use from toggling it.

Code patch, so stack it after the build you use and flash with `--allow-code-patches`.

**Tested 2026-10-13** on the NW-E394 as 1.26 (`my-walkman` plus this mod): home screen, HOLD on,
15 taps of OPTION/PWR shows "DEMO" on screen; the same again turns it off. What the demo itself
does beyond the label is not yet written down.
