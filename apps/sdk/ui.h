/* Small drawing helpers over the firmware's picture and text routines. */
#ifndef UI_H
#define UI_H

#include "fw.h"

#define UI_GREEN 0x47a6
#define UI_WHITE 0xffff
#define UI_GRAY  0x7bcf

void ui_background(void);                                /* the 128x160 home backdrop */
void ui_text(int x, int y, const char *s, u16 color);    /* ASCII, 12 px font, up to 31 chars */
void ui_hex32(char out[11], u32 v);                      /* "0x" + 8 hex digits */
void ui_dec(char out[11], u32 v);                        /* decimal, no leading zeros */

#endif
