# letter-jump-color

The song list's letter jump (the `A`-`Z` / `0-9` / `etc.` index) draws its current letter in gold,
RGB565 `0xf5e0`, with a colour set in code rather than a picture, so themes leave it gold. This
is one code patch: the `movw r0, #0xf5e0` at section 20 `0x306f234` (file offset `0x4be8e0` in
stock 1.01), stored to the text colour right after. Background: NOTES.md, text colour.

`patches.tsv` sets matrix green. To match another preset, replace the new bytes with that
preset's (the gold run through the preset's own recolour, then encoded as `movw r0, #imm`):

| preset | colour | new bytes |
|---|---|---|
| matrix | `0x47a6` | `44f2a670` |
| ice | `0x05de` | `40f2de50` |
| sony-blue | `0x029e` | `40f29e20` |
| purple | `0x901e` | `49f21e00` |
| mint | `0x07af` | `40f2af70` |
| rose | `0xf00f` | `4ff20f00` |
| amber | `0xf5cc` | `4ff2cc50` |
| mono | `0xf7be` | `4ff2be70` |
| ghost | `0xa514` | `4af21450` |
| neon | `0xfde0` | `4ff6e050` (still gold, as neon keeps stock colours) |

It is a code patch, so `flash` needs `--allow-code-patches`; themes stay picture-only. Stack it
after a theme:

```
nwe39x build --mod mods/my-walkman -o out/my-walkman      # my-walkman includes it
nwe39x diff out/my-walkman/Data/Device/RKNANOFW.IMG
nwe39x flash --updater out/my-walkman --allow-code-patches
```
