/* hello-app: the first code of our own on the NW-E390. It runs in app slot 7 (Ebook, compiled
 * out by Sony), opened from the home menu's Photos icon. It lists the last 8 key events as hex,
 * newest first, so it doubles as a key-code finder. OPTION/PWR (short press) goes back home. */
#include "fw.h"

#define GREEN 0x47a6
#define WHITE 0xffff
#define EXIT_EVENT ((EV_RELEASE << 28) | KEY_OPTION)
#define HISTORY 8

static int dirty;
static u32 history[HISTORY], count;

/* GCC may call these for struct and array initializers, even freestanding. */
void *memset(void *d, int c, unsigned n) { u8 *p = d; while (n--) *p++ = (u8)c; return d; }
void *memcpy(void *d, const void *s, unsigned n) { u8 *p = d; const u8 *q = s; while (n--) *p++ = *q++; return d; }

static void text(int y, const char *s, u16 color)
{
    u16 buf[24];
    u16 rect[4] = {4, (u16)y, 124, (u16)(y + 12)};
    int i = 0;
    while (s[i] && i < 23) { buf[i] = (u8)s[i]; i++; }
    buf[i] = 0;
    text_color->fg = color;
    text_color->flags = 1;
    draw_text(rect, rect, buf, 0);
}

static void hex32(char *out, u32 v)
{
    out[0] = '0'; out[1] = 'x';
    for (int i = 0; i < 8; i++) {
        u32 d = (v >> (28 - 4 * i)) & 0xf;
        out[2 + i] = (char)(d < 10 ? '0' + d : 'a' + d - 10);
    }
    out[10] = 0;
}

static void start(u8 *msg)
{
    (void)msg;
    dirty = 1;
}

static int event(void)
{
    return 0;
}

static int keys(void)
{
    if (keys_blocked())
        return 0;
    u32 ev = key_event();
    if (!ev)
        return 0;
    if (ev == EXIT_EVENT) {
        u8 msg[28] = {0};   /* home: highlight entry id 0 (the Photos slot we live in) */
        app_switch(0, msg);
        return 1;
    }
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
    draw_picture_at(105, 0, 0);
    text(18, "Hello from slot 7!", GREEN);
    text(32, "key events, newest first:", WHITE);
    for (int i = 0; i < HISTORY; i++) {
        hex32(h, history[i]);
        text(46 + 11 * i, h, i ? WHITE : GREEN);
    }
    hex32(h, count);
    text(136, h, GREEN);
    text(148, "OPTION: back home", WHITE);
}

static void stop(void)
{
}

__attribute__((section(".descriptor"), used))
const struct app descriptor = {0, 0, event, keys, draw, start, stop};
