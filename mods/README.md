# Mods

A mod is a folder. `mod.toml` says what it holds and what it builds on (see `src/nwe39x/modspec.py`):

```toml
name = "my-walkman"
include = ["../theme-matrix", "../letter-jump-color", "../bootscreen-photo", "../font-terminus", "../volume-limit"]
```

Pieces a mod can have: `theme` (a preset, applied to Sony's pictures at build time), `images`
(folders of NNN.png), `fonts` (folders of glyph sheets), `strings` (TSVs), `patches` (TSVs). A
folder without a mod.toml uses its own images/, fonts/, strings.tsv and patches.tsv.

```
nwe39x build --mod mods/my-walkman -o out/my-walkman      # version: one above the player's
nwe39x diff out/my-walkman/Data/Device/RKNANOFW.IMG       # every changed byte, named
nwe39x flash --updater out/my-walkman --allow-code-patches  # it has OS patches (volume-limit, letter-jump-color)
```

`build` writes `manifest.json` beside the image (version, mod, patch files used); `diff` and
`flash` read it so the check needs no flags. Generated pieces (theme pictures, glyph sheets, the
no-fm patches, the clean boot screens) are not committed; each mod's README says how to make them.

| mod | what |
|---|---|
| my-walkman | the build on the player: theme-matrix, letter-jump-color, bootscreen-photo, font-terminus, volume-limit |
| theme-dark, theme-ice, ... | recolor presets (`nwe39x theme`); pictures only, so the letter-jump highlight stays gold |
| letter-jump-color | the letter-jump highlight in a theme color (one code patch; matrix by default) |
| bootscreen-clean | gray logo, taglines in the UI fonts |
| bootscreen-photo | boot and power-off screens from photos, captioned in Terminus (`nwe39x bootscreen`) |
| font-terminus | Terminus 12 in the menu font |
| volume-limit | no 17-step cap |
| hello-app | our own code as app 7, opened from the Photos icon: lists key events (`scripts/build_app.py` compiles it) |
| demo-mode | Sony's hidden store-demo mode on 15 presses of OPTION/PWR (one code patch; HOLD on, home screen) |
| no-fm | FM Radio dropped from the home menu |
| no-fm-settings | FM Radio Settings dropped from the Settings menu |
| font-test | Comic Sans / Consolas: which screens use which font |
| font-diag, font-diag12 | test-pattern glyph sheets (committed; `scripts/font_diag.py` makes them) showing which part of a glyph cell the player draws |
