# theme-dark

Monochrome UI: the gold highlight bars, icons and battery frame become light grey; the red alert
and low-battery rings stay red. The pictures are generated, not committed:

```
nwe39x theme mono mods/theme-dark/images --sheet work/theme_dark_sheet.png
nwe39x build --images mods/theme-dark/images --patches mods/volume-limit/patches.tsv --patches mods/no-fm/patches.tsv -o out/combo
nwe39x flash --updater out/combo
```
