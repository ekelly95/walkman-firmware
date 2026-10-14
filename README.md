# nwe39x

[![tests](https://github.com/ekelly95/walkman-firmware/actions/workflows/tests.yml/badge.svg)](https://github.com/ekelly95/walkman-firmware/actions/workflows/tests.yml)

Custom color themes, fonts, boot screens and menu tweaks for Sony's **NW-E393 / NW-E394 /
NW-E395** Walkman, made by editing Sony's own firmware updater on your PC.

![The ten color presets applied to a sample of the player's UI pictures](docs/theme_presets.png)

*The color presets, applied to a sample of the player's interface pictures (`nwe39x theme NAME
DIR --sheet SHEET.png`). This is a contact sheet of the pictures, not a photo of the screen.*

> [!WARNING]
> **Experimental, and there is no recovery.** If an install leaves the player unable to start,
> there is no known way to get it back: no recovery mode has been found for this player. Only one
> NW-E394 on Sony's firmware 1.01 has been tested. Don't use this on a player you can't afford to
> lose.

## What it is, and isn't

nwe39x takes the updater Sony publishes for this player, changes the pictures, fonts and text
inside it, and installs the result. The player still runs Sony's firmware, with your changes.

- It is **not** Rockbox or a new firmware, and it adds no audio formats. It can add one thing
  Sony's firmware never had: a launcher for small apps of your own (see [Apps](#apps)).
- It ships **no Sony files**. You download Sony's updater yourself; everything is built on your
  PC.
- Installing needs **Windows** (it talks to the player over USB the way Sony's tool does).
  Building and previewing work wherever Python does.

## What you can change

| | |
|---|---|
| **Color themes** | ten presets, each with a `mods/theme-*` folder (mono's is `theme-dark`): mono, ice, sony-blue, purple, mint, rose, amber, matrix, neon, ghost; or any hue. Themes recolor pictures only: the highlighted letter in the song list's letter jump is drawn by code and stays Sony's gold unless you add `mods/letter-jump-color` (a code patch) |
| **Fonts** | replace the 12 px menu font or the 16 px font from a TrueType or BDF bitmap font |
| **Boot and power-off screens** | from your own picture (128x160) |
| **Text** | any interface string, in any of the 13 languages |
| **Menus** | hide entries such as FM Radio from the home and Settings menus |
| **Volume limit** | remove the regional 17-step cap |
| **Apps** | a launcher that runs your own programs from the player's drive, such as Snake |

Themes, fonts, pictures and text only replace resources. **Menu, volume and launcher changes patch
the player's code**: a wrong one can stop it starting, so `flash` refuses them unless you pass
`--allow-code-patches`.

## Tested

| Player | Sony firmware | Result |
|---|---|---|
| NW-E394 | 1.01 | themes, fonts, boot screens, strings, menu and volume changes, the launcher and apps; stock restore |
| NW-E393, NW-E395 | 1.01 | **untested.** Sony uses the same updater for all three, so they probably behave the same |
| any | other versions | **untested.** Not supported |

If you try it on an untested combination, please file a
[compatibility report](https://github.com/ekelly95/walkman-firmware/issues/new?template=compatibility-report.yml):
model, Sony version (`nwe39x status`) and what happened. Leave out your serial number.

## First run: a color theme

You need Windows, [uv](https://docs.astral.sh/uv/) (it installs Python for you), and Sony's
updater for the NW-E390 series, version 1.01: `NW-E390_V1_01.exe`. Find it on Sony's support site
for your country under your model (NW-E393, NW-E394 or NW-E395), in its software and firmware
downloads. Check the file before using it:

```
certutil -hashfile NW-E390_V1_01.exe SHA256
870121a0d373adbbca204120c2018248719c08dda8c5894e4f5048b306c809a4
```

Charge the player, back up your music, and close anything that has the player's drive open.

```
git clone https://github.com/ekelly95/walkman-firmware
cd walkman-firmware
uv sync

uv run nwe39x unpack NW-E390_V1_01.exe             # unpacks Sony's updater into extract/
uv run nwe39x status                               # finds the player, shows its firmware version

uv run nwe39x restore                              # 1. a stock build first: your way back
uv run nwe39x build --mod mods/theme-ice -o out/theme-ice   # 2. the theme
uv run nwe39x diff out/theme-ice/Data/Device/RKNANOFW.IMG   # 3. what changed: pictures, version, CRC
uv run nwe39x flash --updater out/theme-ice        # 4. install; type "flash" when asked
```

The install takes about 15 seconds. The player disconnects, installs, restarts and comes back
reporting the new version. Leave it plugged in and don't touch the drive until `flash` finishes.

No administrator rights are needed, and installs leave your music and playlists alone.

**Going back to Sony's look:** `uv run nwe39x flash --updater out/stock-restore`. This works for any
player that still starts; it can't help one that doesn't.

## What `flash` checks first

Before it touches the player, `flash` refuses:

- an image whose changes it can't account for against Sony's original, byte by byte (`nwe39x diff`
  shows the same check);
- an image that fails the checks the player's own installer makes;
- changes to the player's code, unless you pass `--allow-code-patches`;
- any install while there is no stock build in `out/stock-restore` to go back to.

Then it shows what it is about to install, on which player, and waits for you to type `flash`.

## Make your own boot screen

![A boot screen and a power-off screen made from photos, captioned "Hello Again" and "See You Later"](docs/bootscreen-demo.png)

*Boot and power-off screens from photos by [Jack Young](https://unsplash.com/photos/green-northern-lights-xGltqb1ChYw)
and [Alex Middleton](https://unsplash.com/photos/green-light-in-dark-room-aka-hHVgZQ8) on Unsplash, captioned in
Terminus. Shown at 2x; the screen is 128x160.*

Any photo can be the boot screen (picture 044) or the power-off screen (083), with your own words
in place of "For Music Lovers, By Music Lovers":

```
uv run nwe39x bootscreen photo.jpg mine/044.png --caption "Hello Again" --preview boot-preview.png
uv run nwe39x bootscreen photo2.jpg mine/083.png --caption "See You Later" --focus 0.75,0.75 --zoom 1.6
uv run nwe39x build --images mine -o out/mine
```

`--caption` takes lines separated by `|`, `--focus` (fractions across and down) and `--zoom` choose
the crop, and `--font`/`--font-size` set the caption font. `--preview` writes a 3x enlargement to
check before you build. [mods/bootscreen-photo](mods/bootscreen-photo) has the exact commands for
the screens above.

## Apps

![The launcher listing two apps, and a game of Snake](docs/apps-demo.png)

*The launcher and Snake, rendered with the player's own font and layout (`scripts/render_apps.py`);
shown at 2x. Both run on the tested NW-E394.*

Sony's firmware has room for 17 apps and left two of them, Record and Ebook, empty.
`mods/launcher` puts a launcher there and makes the home menu's **Photos** icon open it. It lists
`APP0.BIN` .. `APP9.BIN` from the top folder of the player's drive and runs the one you pick, so
once the launcher is installed a new app is a file copy, not a flash.

```
uv run python -I scripts/build_app.py mods/launcher        # needs arm-none-eabi-gcc (WSL is fine)
uv run nwe39x build --mod mods/launcher -o out/launcher
uv run nwe39x flash --updater out/launcher --allow-code-patches

uv run python -I scripts/build_app.py --bin apps/snake     # then copy SNAKE.BIN to the player as APP2.BIN
```

Apps are small C programs (up to 19.5 KiB) that call the firmware's own drawing, text, key and
file routines; [apps/README.md](apps/README.md) shows how to write one. The launcher is a code
patch like the menu changes, with the same warning: experimental, tested on one player. An app that
crashes or hangs leaves the firmware alone; hold OPTION/PWR to turn the player off.

## More

- [mods/README.md](mods/README.md): the mods, how to combine them, and how to make your own.
- [apps/README.md](apps/README.md): the apps and how to write one.
- `uv run nwe39x --help`: every command (exporting pictures, strings and font sheets, previews).
- [NOTES.md](NOTES.md): reverse-engineering notes on the firmware: layout, addresses, how the
  installer works.

## License

GPL-2.0-or-later; see [LICENSE](LICENSE) and [NOTICE](NOTICE). The firmware image format and CRC
code are ported from [Rockbox](https://github.com/Rockbox/rockbox)'s rkboottool. "Sony" and
"Walkman" are trademarks of Sony Group Corporation; this project is not affiliated with or endorsed
by Sony.
