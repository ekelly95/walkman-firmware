# theme-dark

Monochrome UI: the gold highlight bars, icons and battery frame become light gray; the red alert
and low-battery rings stay red. The pictures are generated, not committed:

```
nwe39x theme mono mods/theme-dark/images --sheet work/theme_dark_sheet.png
nwe39x build --mod mods/my-walkman -o out/my-walkman
nwe39x flash --updater out/my-walkman --allow-code-patches
```
