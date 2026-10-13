# no-fm

Drops FM Radio from the home menu: the five remaining entries close up over the 3x2 icon grid and
the carousel's hard-coded entry count becomes 5. The FM screens themselves are untouched, just
unreachable. `build` re-fits the background behind the three icons that move up a slot, so they
show no square of the old slot's backdrop. Regenerate after changing the firmware version, and stack it on any build:

```
nwe39x menu show
nwe39x menu hide FM -o mods/no-fm/patches.tsv
nwe39x build --mod mods/no-fm -o out/no-fm
nwe39x diff out/no-fm/Data/Device/RKNANOFW.IMG
```
