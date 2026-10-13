# bootscreen-clean

Boot (044) and power-off (083) screens to match the dark theme and the Terminus menus: Sony's
logo greyed, the taglines re-set from the firmware's own glyphs (Terminus 12 for the lines,
Sony's 16 px font for POWER OFF) instead of the anti-aliased artwork. The pictures are generated
by the snippet in NOTES.md ("Boot screen to match") and not committed; build with

```
nwe39x build --images mods/theme-dark/images --images mods/bootscreen-clean/images --fonts mods/font-terminus/fonts --patches mods/volume-limit/patches.tsv --patches mods/no-fm/patches.tsv -o out/combo
```
