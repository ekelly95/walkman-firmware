# launcher

Runs apps from the player's drive. Sony's firmware has 17 app slots; slots 6 (Record) and 7
(Ebook) were compiled out and their sections (26, 27) are empty. This mod puts the launcher in
slot 7 and makes the home menu's **Photos** icon open it.

The launcher lists `APP0.BIN` .. `APP9.BIN` from the top folder of the player's drive (by the name
in each file's header) and runs the one you pick. Apps are built from `apps/` (see
[apps/README.md](../../apps/README.md)); adding or changing one is a file copy, not a flash.

| | |
|---|---|
| + or ◀◀ / − or ▶▶ | move in the list |
| play/pause | run the app |
| OPTION/PWR | back to the home menu |
| hold BACK, in an app | back to the list, whatever the app does with keys |

Holding OPTION/PWR still turns the player off, and USB still connects from inside an app: the core
handles both, not the app.

## Building

Needs `arm-none-eabi-gcc` (in WSL: `sudo apt install gcc-arm-none-eabi binutils-arm-none-eabi`).

```
uv run python -I scripts/build_app.py mods/launcher        # compiles, writes patches.tsv
uv run nwe39x build --mod mods/launcher -o out/launcher    # or include it from another mod
uv run nwe39x diff out/launcher/Data/Device/RKNANOFW.IMG
uv run nwe39x flash --updater out/launcher --allow-code-patches
```

`patches.tsv` is generated (ignored by git). It holds:

- the launcher's code and data, written to the free space after the last blob (file offset
  `0xc94200`);
- section 27's header pointing at them: code runs at `0x306c4a4` (the shared app slot, and must
  end below `0x306d000` where .BIN apps load), data at `0x3023010` beginning with the app
  descriptor;
- the descriptor pointer for app 7 in the app table (section 2 data `0x3090a50`, was 0);
- two home-menu patches in section 17: skip the "no photos" check (`0x306c5a2`) and switch to app 7
  instead of 16 (`0x306c5ac`).

## How it runs an app

On a pick it opens `\APPn.BIN`, reads it in 2 KiB chunks to `0x306d000`, checks the header
(magic `NWAP`, ABI 1, load address, size at most 0x4e00), zeroes any bss past the end of the file,
and calls the app's `start`. From then on its own `keys` hands each key event to the app's `key`
and its `draw` calls the app's `draw` every pass. The firmware's dispatcher (section 0
`0x3066a08`) only ever sees the launcher. NOTES.md, "Apps and the overlay loader", has the details.
