# Apps

Programs for the player, run by the [launcher](../mods/launcher/README.md). Each folder here builds
one `.BIN`; copy it to the top folder of the player's drive as `APP0.BIN` .. `APP9.BIN`, eject,
and open Photos. No flashing.

```
uv run python -I scripts/build_app.py --bin apps/keytest    # -> apps/keytest/build/KEYTEST.BIN
```

| app | what |
|---|---|
| keytest | the last 8 key events as hex: which button sends which code |

## Writing one

An app is a C file (or several) that ends with one `NWAPP(...)` line:

```c
#include "nwapp.h"
#include "ui.h"

static int dirty;
static void start(void) { dirty = 1; }
static int key(u32 ev) { return ev == ((EV_RELEASE << 28) | KEY_OPTION); }  /* 1: back to the list */
static void draw(void)
{
    if (!dirty) return;
    dirty = 0;
    ui_background();
    ui_text(4, 40, "Hello", UI_GREEN);
}
static void stop(void) {}

NWAPP("Hello", start, key, draw, stop);
```

- `key(ev)` gets every key event: `EV_KEY(ev)` is the button (`KEY_PLAY`, `KEY_PREV`, ...),
  `EV_TYPE(ev)` is press, long press, repeat or release. Return nonzero to go back to the list.
- `draw()` is called on every pass of the firmware's app loop, so it is also the place for anything
  that moves. Redraw only what changed: drawing the full background each pass is slow.
- The SDK (`sdk/`) has the firmware calls (`fw.h`: pictures, text, files, keys, switching apps),
  the header (`nwapp.h`) and helpers (`ui.h`). There is no C library; `memset` and `memcpy` are in
  `rt.c`.
- The whole app (code, data and bss) gets 0x4e00 bytes (19.5 KiB) at `0x306d000`. It is reloaded
  fresh each time it is opened, so nothing survives in memory between runs; use a file for that.

A crash or a hang in an app does not touch the firmware: hold OPTION/PWR to turn the player off.
