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
/* Key codes, read with the hello-app on the player (2026-10-13). */
#define KEY_OPTION 0x01
#define KEY_PLAY   0x02
#define KEY_PREV   0x10
#define KEY_NEXT   0x20
#define KEY_VOLUP  0x40
#define KEY_VOLDOWN 0x100
#define KEY_BACK   0x80
#define KEY_HOLD   0x800
#define EV_KEY(ev)  ((ev) & 0x0fffffff)
#define EV_TYPE(ev) ((ev) >> 28)
enum { EV_PRESS = 1, EV_LONG = 2, EV_REPEAT = 3, EV_RELEASE = 4, EV_LONG_RELEASE = 5 };
#define keys_blocked    FW(0x3067cdc, int (*)(void))   /* home skips input while nonzero */
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

struct text_color { u16 fg, bg, flags; };   /* flags bit 0: transparent background, bit 1: swap */
#define text_color      ((volatile struct text_color *)0x551c)

#endif
