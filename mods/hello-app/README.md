# hello-app

Our own code running as an app on the player. Sony's firmware has 17 app slots; slots 6 (Record)
and 7 (Ebook) were compiled out and their sections (26, 27) are empty. This mod fills slot 7 with
`app.c` and makes the home menu's **Photos** icon open it.

The app shows the last key event as hex (`key code | type << 28`, see `fw.h`) and a count, so it
also tells you which button is which key code. A short press of OPTION/PWR goes back home; holding
OPTION/PWR still turns the player off (that is handled by the core, not the app).

## Building

Needs `arm-none-eabi-gcc` (in WSL: `sudo apt install gcc-arm-none-eabi binutils-arm-none-eabi`).

```
uv run python -I scripts/build_app.py mods/hello-app        # compiles, writes patches.tsv
uv run nwe39x build --mod mods/hello-app -o out/hello-app   # or include it from another mod
uv run nwe39x diff out/hello-app/Data/Device/RKNANOFW.IMG
uv run nwe39x flash --updater out/hello-app --allow-code-patches
```

`patches.tsv` is generated (ignored by git). It holds:

- the app's code and data, written to the free space after the last blob (file offset `0xc94200`);
- section 27's header pointing at them: code runs at `0x306c4a4` (the shared app slot), data at
  `0x3023010` beginning with the app descriptor;
- the descriptor pointer for app 7 in the app table (section 2 data `0x3090a50`, was 0);
- two home-menu patches in section 17: skip the "no photos" check (`0x306c5a2`) and switch to app 7
  instead of 16 (`0x306c5ac`).

## How an app works

The dispatcher (section 0 `0x3066a08`) loads the app's section with the overlay loader
(`0x3066eda`), calls `start(msg)`, then loops: `event()` and `keys()` (nonzero means an app switch
was requested), `draw()` when a redraw is due, and `stop()` before the next app loads. The core
handles power-off, USB and HOLD on its own each pass. NOTES.md, "Apps and the overlay loader", has
the details.
