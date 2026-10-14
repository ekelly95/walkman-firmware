/* Small drawing helpers over the firmware's picture and text routines. */
#ifndef UI_H
#define UI_H

#include "fw.h"

#define UI_GREEN 0x47a6
#define UI_WHITE 0xffff
#define UI_GRAY  0x7bcf

#define UI_BLACK 0x0000
#define UI_RED   0xf800

void ui_background(void);                                /* the 128x160 home backdrop */
void ui_text(int x, int y, const char *s, u16 color);    /* ASCII, 12 px font, up to 31 chars */
void ui_hex32(char out[11], u32 v);                      /* "0x" + 8 hex digits */
void ui_dec(char out[11], u32 v);                        /* decimal, no leading zeros */

void ui_fill(int x0, int y0, int x1, int y1, u16 color);  /* inclusive rectangle */
/* 10 ms ticks since the app started, counted by polling SysTick. Call it at least every 10 ms to
 * keep it exact (draw() runs far more often); a slower caller loses whole ticks, never gains. */
u32 ui_ticks(void);
u32 ui_random(void);                                     /* xorshift, seeded from SysTick */

#endif
