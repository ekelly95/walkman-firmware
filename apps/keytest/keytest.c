/* keytest: lists the last 8 key events as hex, newest first. OPTION goes back to the launcher. */
#include "nwapp.h"
#include "ui.h"

#define HISTORY 8

static u32 history[HISTORY], count;
static int dirty;

static void start(void)
{
    dirty = 1;
}

static int key(u32 ev)
{
    if (ev == (((u32)EV_RELEASE << 28) | KEY_OPTION))
        return 1;
    for (int i = HISTORY - 1; i > 0; i--)
        history[i] = history[i - 1];
    history[0] = ev;
    count++;
    dirty = 1;
    return 0;
}

static void draw(void)
{
    char h[11];
    if (!dirty)
        return;
    dirty = 0;
    ui_background();
    ui_text(4, 18, "Key test (a .BIN app)", UI_GREEN);
    for (int i = 0; i < HISTORY; i++) {
        ui_hex32(h, history[i]);
        ui_text(4, 34 + 12 * i, h, i ? UI_WHITE : UI_GREEN);
    }
    ui_dec(h, count);
    ui_text(4, 134, h, UI_GREEN);
    ui_text(4, 148, "OPTION: back", UI_GRAY);
}

static void stop(void)
{
}

NWAPP("Key test", start, key, draw, stop);
