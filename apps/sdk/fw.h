/* Sony NW-E390 firmware 1.01 entry points, for the launcher (an app slot) and the .BIN apps it
 * loads. Addresses are section 0 (always resident) run addresses, called with the Thumb bit set.
 * Evidence for each is in NOTES.md. */
#ifndef FW_H
#define FW_H

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;

/* App descriptor: the first 28 bytes of an app section's data (run address 0x3023010).
 * The dispatcher at 0x3066a08 calls start once, then loops: event and keys (a nonzero return
 * switches app), draw when a redraw is due, and stop before the next app loads. */
struct app {
    u32 link0, link1;            /* zeroed by the dispatcher */
    int (*event)(void);          /* +0x08 */
    int (*keys)(void);           /* +0x0c */
    void (*draw)(void);          /* +0x10 */
    void (*start)(u8 *msg);      /* +0x14: msg = the 28 bytes the caller passed to app_switch */
    void (*stop)(void);          /* +0x18 */
};

#define FW(addr, type) ((type)((addr) | 1))

/* Switch to app `idx` (0 MainMenu ... 16 PhotoMenu); `msg` is copied (28 bytes). For MainMenu,
 * msg[0] is the home entry id to highlight. Return nonzero from keys() afterwards. */
#define app_switch      FW(0x3066b6c, void (*)(int idx, const void *msg))
/* Current key event, 0 if none: key code | type << 28 (EV_* below). Each press gives a press,
 * then repeats if held past 50 ticks, then a release. 0x800 while HOLD is on. */
#define key_event       FW(0x306067c, u32 (*)(void))
/* Key codes, read with the key-test app on the player (2026-10-13). The pad's four arrows and
 * center, plus the volume buttons; VOL+ is inferred from key_global's handling of 0x10000004. */
#define KEY_OPTION  0x01
#define KEY_PLAY    0x02    /* pad center */
#define KEY_VOLUP   0x04
#define KEY_DOWN    0x08    /* pad down */
#define KEY_LEFT    0x10    /* pad left, |<< */
#define KEY_RIGHT   0x20    /* pad right, >>| */
#define KEY_UP      0x40    /* pad up */
#define KEY_BACK    0x80
#define KEY_VOLDOWN 0x100
#define KEY_HOLD   0x800
#define EV_KEY(ev)  ((ev) & 0x0fffffff)
#define EV_TYPE(ev) ((ev) >> 28)
enum { EV_PRESS = 1, EV_LONG = 2, EV_REPEAT = 3, EV_RELEASE = 4, EV_LONG_RELEASE = 5 };
/* The firmware's global key handling, as the home menu calls it with each event: + and - change
 * the volume, HOLD shows its icon. Returns nonzero when it used the event. Apps that want + and -
 * for themselves just don't call it. */
#define key_global      FW(0x3067cdc, int (*)(u32 ev))

/* Screen timeout (state at RAM 0x55a4: +0 screen off, +1 hold count, +4 last activity). While the
 * screen is off the dispatcher stops calling draw(). screen_activity restarts the timeout, as a
 * key press in a menu should; screen_hold keeps the screen on until a matching screen_release. */
#define screen_activity FW(0x3062d8e, void (*)(void))
#define screen_hold     FW(0x3062db6, void (*)(void))
#define screen_release  FW(0x3062d9c, void (*)(void))
/* Picture `idx` from imageres0 at (x, y). 105 is the 128x160 home backdrop. */
#define draw_picture_at FW(0x3062400, void (*)(int idx, int x, int y))
/* Text in the 12 px font, color from text_color. rect = {x0, y0, x1, y1}; align 0 left,
 * 1 right, 2 center. str is UTF-16, zero-terminated. */
#define draw_text       FW(0x3061774, void (*)(const u16 *rect, const u16 *rect2, const u16 *str, int align))

/* Files on the player's drive. dir is a path such as "\\"; name is the 8.3 short name without
 * the dot, space padded to 11 characters ("APP1    BIN"); mode "R" or "W". Up to 8 open files. */
#define file_open       FW(0x3057fda, int (*)(const char *dir, const char *name83, const char *mode))
#define file_read       FW(0x305824a, unsigned (*)(void *buf, unsigned len, int handle))  /* bytes read */
#define file_size       FW(0x305867e, unsigned (*)(int handle))
#define file_close      FW(0x30581c8, void (*)(int handle))

/* Direct LCD drawing: set an inclusive window, then write its pixels row by row (RGB565). */
#define lcd_window      FW(0x3062774, void (*)(int x0, int y0, int x1, int y1))
#define lcd_pixel       FW(0x30626cc, void (*)(u16 color))

/* The firmware's 10 ms tick counter (SysTick interrupt), the "now" of the screen timeout and the
 * key handler. SysTick's CVR counts down within the current tick: a cheap source of entropy. */
#define TICKS           (*(volatile u32 *)0x4b68)
#define SYST_CVR        (*(volatile u32 *)0xE000E018)

/* 12 px font lookups, as draw_text uses them (each reads the font from flash: cache results).
 * font12_glyph(cp - 0x20) for U+0020..U+20F6 gives the glyph number (0xffff: none);
 * font12_width(glyph) its advance in pixels. Other code points draw 12 px wide (U+FF61..U+FF9F 6). */
#define font12_glyph    FW(0x3053f40, u16 (*)(int index))
#define font12_width    FW(0x3053f20, u8 (*)(int glyph))

/* Background tasks (music playback, the status bar, ...) are a linked list headed at RAM 0x77ac
 * that the dispatcher runs every pass. A task has the app descriptor's shape: links, then five
 * functions. task_remove unlinks one and calls its stop; tasks_stop_all stops them all, as the
 * core does before USB mode. The core's own tasks live in section 0 (data 0x30044xx). */
struct task {
    struct task *prev, *next;
    void (*fn[5])(void);
};
#define TASK_LIST       ((void *)0x77ac)    /* points at the first task */
#define task_remove     FW(0x30569a8, int (*)(void *list, struct task *t))
#define tasks_stop_all  FW(0x3056a0c, int (*)(void *list))

struct text_color { u16 fg, bg, flags; };   /* flags bit 0: transparent background, bit 1: swap */
#define text_color      ((volatile struct text_color *)0x551c)

#endif
