# bootscreen-clean

Boot (044) and power-off (083) screens to match the dark theme and the Terminus menus: Sony's
logo grayed, the taglines re-set from the firmware's own glyphs (Terminus 12 for the lines,
Sony's 16 px font for POWER OFF) instead of the anti-aliased artwork. The pictures are generated
by `scripts/bootscreen_clean.py` and not committed:

```
uv run python -I scripts/bootscreen_clean.py extract/cab/Data/Device/RKNANOFW.IMG mods/bootscreen-clean/images mods/font-terminus/fonts/font12_terminus.png
nwe39x build --mod mods/my-walkman -o out/my-walkman
```
