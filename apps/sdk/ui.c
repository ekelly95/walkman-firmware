#include "ui.h"

void ui_background(void)
{
    draw_picture_at(105, 0, 0);
}

void ui_text(int x, int y, const char *s, u16 color)
{
    u16 buf[32];
    u16 rect[4] = {(u16)x, (u16)y, 127, (u16)(y + 12)};
    int i = 0;
    while (s[i] && i < 31) { buf[i] = (u8)s[i]; i++; }
    buf[i] = 0;
    text_color->fg = color;
    text_color->flags = 1;
    draw_text(rect, rect, buf, 0);
}

void ui_hex32(char out[11], u32 v)
{
    out[0] = '0'; out[1] = 'x';
    for (int i = 0; i < 8; i++) {
        u32 d = (v >> (28 - 4 * i)) & 0xf;
        out[2 + i] = (char)(d < 10 ? '0' + d : 'a' + d - 10);
    }
    out[10] = 0;
}

void ui_dec(char out[11], u32 v)
{
    char tmp[11];
    int n = 0, i = 0;
    do { u32 q = v / 10; tmp[n++] = (char)('0' + (v - q * 10)); v = q; } while (v);
    while (n) out[i++] = tmp[--n];
    out[i] = 0;
}
