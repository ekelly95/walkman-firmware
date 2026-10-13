# no-fm

Drops FM Radio from the home menu: the five remaining entries close up over the 3x2 icon grid and
the carousel's hard-coded entry count becomes 5. The FM screens themselves are untouched, just
unreachable. Regenerate after changing the firmware version, and stack it on any build:

```
nwe39x menu show
nwe39x menu hide FM -o mods/no-fm/patches.tsv
nwe39x build --patches mods/volume-limit/patches.tsv --patches mods/no-fm/patches.tsv -o out/combo
nwe39x diff out/combo/Data/Device/RKNANOFW.IMG --patches mods/volume-limit/patches.tsv --patches mods/no-fm/patches.tsv
```
