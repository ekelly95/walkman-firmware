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
| snake | Snake: the pad steers, center pauses; holds the screen on while playing |
| bigtest | a big app: checks a 96 KiB table in its own image and the 164 KiB heap |

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

- `key(ev)` gets every key event: `EV_KEY(ev)` is the button (`KEY_UP`, `KEY_DOWN`, `KEY_LEFT`, `KEY_RIGHT`, `KEY_PLAY` for the pad's center, ...),
  `EV_TYPE(ev)` is press, long press, repeat or release. Return nonzero to go back to the list.
- `draw()` is called on every pass of the firmware's app loop, so it is also the place for anything
  that moves. Redraw only what changed: drawing the full background each pass is slow.
- The SDK (`sdk/`) has the firmware calls (`fw.h`: pictures, text, files, keys, switching apps),
  the header (`nwapp.h`) and helpers (`ui.h`). There is no C library; `memset` and `memcpy` are in
  `rt.c`.
- The screen times out as in Sony's menus (the launcher restarts the timeout on each key press),
  and while it is off `draw()` is not called at all. An app that moves on its own, like a game,
  calls `screen_hold()` while it runs and `screen_release()` when it stops (also in `stop()`).
- `ui_ticks()` counts 10 ms ticks from the firmware's SysTick; `ui_random()` gives random numbers.
- A small app (`NWAPP(...)`) gets 0x4e00 bytes (19.5 KiB) at `0x306d000` for code, data and bss,
  and music keeps playing. A **big app** (`NWAPP_BIG(...)`) gets 0x22000 bytes (136 KiB) there plus
  `NWAPP_HEAP`, 0x29000 bytes (164 KiB); the launcher stops music first, because big apps use the
  audio code's memory. Either way the app is loaded fresh each time it opens, so nothing survives
  in memory between runs; use a file for that.

A crash or a hang in an app does not touch the firmware: hold OPTION/PWR to turn the player off.
