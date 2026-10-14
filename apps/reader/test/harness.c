/* Host test for reader.c's layout: real font widths, stand-ins for everything else. */
#include <stdio.h>
#include <stdlib.h>
#define FW_H
typedef unsigned char u8; typedef unsigned short u16; typedef unsigned int u32;
#include "fontdata.h"
static u16 font12_glyph(int i) { return GLYPH[i]; }
static u8 font12_width(int g) { return WIDTH[g]; }
static int file_open(const char *d, const char *n, const char *m) { (void)d; (void)n; (void)m; return -1; }
static unsigned file_read(void *b, unsigned l, int h) { (void)b; (void)l; (void)h; return 0; }
static unsigned file_size(int h) { (void)h; return 0; }
static void file_close(int h) { (void)h; }
struct text_color { u16 fg, bg, flags; };
static struct text_color tc;
#define text_color (&tc)
static void draw_text(const u16 *a, const u16 *b, const u16 *s, int al) { (void)a; (void)b; (void)s; (void)al; }
#define KEY_OPTION 0x01
#define KEY_PLAY 0x02
#define KEY_DOWN 0x08
#define KEY_LEFT 0x10
#define KEY_RIGHT 0x20
#define KEY_UP 0x40
#define KEY_BACK 0x80
#define EV_KEY(ev) ((ev) & 0x0fffffff)
#define EV_TYPE(ev) ((ev) >> 28)
enum { EV_PRESS = 1, EV_LONG = 2, EV_REPEAT = 3, EV_RELEASE = 4, EV_LONG_RELEASE = 5 };
#define NWAPP_H
#define NWAPP_HEAP ((void *)0)
#define NWAPP_HEAP_SIZE 0x29000u
#define NWAPP_BIG(...) extern int nwapp_unused
#include "reader.c"
void ui_background(void) {}
void ui_text(int x, int y, const char *s, u16 c) { (void)x; (void)y; (void)s; (void)c; }
void ui_hex32(char o[11], u32 v) { (void)o; (void)v; }
void ui_dec(char o[11], u32 v) { sprintf(o, "%u", v); }
void ui_fill(int a, int b, int c, int d, u16 e) { (void)a; (void)b; (void)c; (void)d; (void)e; }
u32 ui_ticks(void) { return 0; }
u32 ui_random(void) { return 4; }

static void put_utf8(u32 c)
{
    if (c < 0x80) putchar((int)c);
    else if (c < 0x800) { putchar(0xc0 | c >> 6); putchar(0x80 | (c & 63)); }
    else { putchar(0xe0 | c >> 12); putchar(0x80 | (c >> 6 & 63)); putchar(0x80 | (c & 63)); }
}

int main(int argc, char **argv)
{
    static u8 buf[200000];
    FILE *f = fopen(argv[1], "rb");
    book = buf;
    book_len = (u32)fread(buf, 1, sizeof buf, f);
    fclose(f);
    u32 pos = book_len >= 3 && buf[0] == 0xef ? 3 : 0;
    int lines = 0, bad = 0, maxw = 0;
    u32 chars_in = 0, chars_out = 0;
    for (u32 p = pos; p < book_len;) {   /* count non-space characters in the source */
        u32 c = decode(&p);
        if (c > ' ' && !(c >= 0x7f && c < 0xa0)) chars_in++;   /* the reader skips C1 controls */
    }
    while (pos < book_len) {
        u16 line[64];
        u32 next = line_at(pos, line, 64);
        if (next == pos) { printf("STUCK at %u\n", pos); return 1; }
        int w = 0;
        for (int i = 0; line[i]; i++) { w += char_width(line[i]); if (line[i] > ' ') chars_out++; }
        if (w > maxw) maxw = w;
        if (w > TEXT_W) bad++;
        if (argc > 2) {
            printf("%3d %3d |", lines, w);
            for (int i = 0; line[i]; i++) put_utf8(line[i]);
            printf("|\n");
        }
        if (lines % LINES == LINES - 1 && argc > 2) printf("---- page %d ----\n", lines / LINES + 1);
        lines++;
        pos = next;
    }
    printf("%d lines, %d pages, widest %d px (limit %d), %d too wide, non-space chars %u in / %u out\n",
           lines, (lines + LINES - 1) / LINES, maxw, TEXT_W, bad, chars_in, chars_out);
    return bad || chars_in != chars_out;
}
