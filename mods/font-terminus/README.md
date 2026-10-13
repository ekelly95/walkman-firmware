# font-terminus

Terminus 12 px in the menu font (font12). Sony's 16 px font is kept: Terminus 16 is monospaced
8 px wide and looks gappy in titles. The baseline is one row above Sony's so the descenders of
g, j, p, q, y fit. The sheet is rendered from the TTF, not committed (Terminus is OFL-licensed;
reference/terminus/ holds the download):

```
nwe39x fonts from-ttf reference/terminus/terminus-ttf-4.49.3/TerminusTTF-4.49.3.ttf mods/font-terminus/fonts/font12_terminus.png --font 12 --size 12 --baseline 10
nwe39x build --images mods/theme-dark/images --fonts mods/font-terminus/fonts --patches mods/volume-limit/patches.tsv --patches mods/no-fm/patches.tsv -o out/combo
nwe39x flash --updater out/combo
```
