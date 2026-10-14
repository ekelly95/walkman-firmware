/* reader: reads BOOK0.TXT .. BOOK9.TXT from the player's top folder. A big app: the whole book (up
 * to 164 KiB) goes into the heap. UTF-8, with Latin-1 as the fallback for bytes that are not; the
 * player's 12 px font draws Latin, Greek, Cyrillic and CJK. Lines wrap at spaces by the font's own
 * widths.
 *
 * List: up/down pick a book, center opens it, OPTION goes back to the launcher.
 * Reading: down or >> next page, up or << previous page, BACK to the list. */
#include "nwapp.h"
#include "ui.h"

#define SLOTS 10
#define TEXT_X 2
#define TEXT_W 124                /* pixels available per line */
#define TOP 16                    /* first text line; the header is above it */
#define LINE_H 13
#define LINES 11                  /* 16 + 11 * 13 = 159 */
#define MAX_PAGES 4096
#define KEY_EV(type, key) (((u32)(type) << 28) | (key))

static u32 sizes[SLOTS];          /* 0: no book in that slot */
static int sel, reading, dirty;
static u8 *book = (u8 *)NWAPP_HEAP;
static u32 book_len, truncated;
static u32 pages[MAX_PAGES];      /* byte offset where each page starts, as far as we have been */
static int page, known;           /* current page; pages[0..known-1] are valid */
static u8 width_cache[0x20f7];    /* width + 1 per code point below U+20F7; 0 = not looked up */
static u32 last_draw;

static void name83(char out[12], int n)        /* "BOOKn   TXT" */
{
    const char *s = "BOOK0   TXT";
    for (int i = 0; i < 12; i++) out[i] = s[i];
    out[4] = (char)('0' + n);
}

static void scan(void)
{
    for (int n = 0; n < SLOTS; n++) {
        char nm[12];
        name83(nm, n);
        int f = file_open("\\", nm, "R");
        sizes[n] = 0;
        if (f >= 0) {
            sizes[n] = file_size(f);
            file_close(f);
        }
    }
    if (!sizes[sel])
        for (sel = 0; sel < SLOTS && !sizes[sel]; sel++)
            ;
    if (sel == SLOTS)
        sel = 0;
}

static int open_book(int n)
{
    char nm[12];
    name83(nm, n);
    int f = file_open("\\", nm, "R");
    if (f < 0)
        return 0;
    u32 size = file_size(f);
    truncated = size > NWAPP_HEAP_SIZE;
    book_len = truncated ? NWAPP_HEAP_SIZE : size;
    u32 got = 0;
    while (got < book_len) {
        u32 want = book_len - got < 4096 ? book_len - got : 4096;
        u32 r = file_read(book + got, want, f);
        if (!r)
            break;
        got += r;
    }
    file_close(f);
    book_len = got;
    pages[0] = book_len >= 3 && book[0] == 0xef && book[1] == 0xbb && book[2] == 0xbf ? 3 : 0;  /* BOM */
    page = 0;
    known = 1;
    return 1;
}

/* Next code point at *pos: UTF-8, or the byte itself (Latin-1) where UTF-8 does not fit. */
static u32 decode(u32 *pos)
{
    u32 p = *pos, c = book[p];
    int n = c >= 0xf0 ? 3 : c >= 0xe0 ? 2 : c >= 0xc0 ? 1 : 0;
    if (n && p + n < book_len) {
        u32 cp = c & (0x3f >> n);
        int ok = 1;
        for (int i = 1; i <= n; i++) {
            u8 b = book[p + i];
            ok &= (b & 0xc0) == 0x80;
            cp = cp << 6 | (b & 0x3f);
        }
        if (ok && cp >= 0x80) {
            *pos = p + n + 1;
            return cp <= 0xffff ? cp : '?';   /* emoji and the like: the font stops at U+FFFF */
        }
    }
    *pos = p + 1;
    return c;
}

static int char_width(u32 cp)
{
    if (cp < 0x20)
        return 0;
    if (cp <= 0x20f6) {
        if (!width_cache[cp]) {
            u16 g = font12_glyph((int)cp - 0x20);
            width_cache[cp] = (u8)((g == 0xffff ? 12 : font12_width(g)) + 1);
        }
        return width_cache[cp] - 1;
    }
    return cp >= 0xff61 && cp <= 0xff9f ? 6 : 12;
}

/* Lays out one line from pos into out (UTF-16, zero-terminated); returns where the next line
 * starts. Wraps at the last space that fits, or mid-word if a word is wider than the line. */
static u32 line_at(u32 pos, u16 *out, int max)
{
    int n = 0, w = 0, n_space = -1;
    u32 p = pos, after_space = 0;
    while (p < book_len && n < max - 1) {
        u32 q = p, cp = decode(&q);
        if (cp == '\n') {
            p = q;
            break;
        }
        if (cp == '\r') {
            p = q;
            continue;
        }
        if (cp == '\t')
            cp = ' ';
        else if (cp < 0x20 || (cp >= 0x7f && cp < 0xa0)) {   /* other control characters */
            p = q;
            continue;
        }
        int cw = char_width(cp);
        if (w + cw > TEXT_W && n) {
            if (cp == ' ') {            /* the space that would overflow ends the line */
                p = q;
                break;
            }
            if (n_space > 0) {          /* back up to the last space */
                n = n_space;
                p = after_space;
            }
            break;
        }
        if (cp == ' ') {
            n_space = n;
            after_space = q;
        }
        out[n++] = (u16)cp;
        w += cw;
        p = q;
    }
    out[n] = 0;
    return p;
}

static void text16(int y, const u16 *s, u16 color)
{
    u16 rect[4] = {TEXT_X, (u16)y, 127, (u16)(y + 12)};
    text_color->fg = color;
    text_color->flags = 1;
    draw_text(rect, rect, s, 0);
}

static void draw_page(void)
{
    char head[32], num[11];
    int i = 0;
    ui_fill(0, 0, 127, 159, UI_BLACK);
    for (const char *s = "BOOK"; *s; s++) head[i++] = *s;
    head[i++] = (char)('0' + sel);
    head[i++] = ' ';
    head[i++] = ' ';
    u32 pct = book_len ? pages[page] * 100 / book_len : 100;   /* at most 164 KiB * 100: fits */
    ui_dec(num, pct);
    for (const char *s = num; *s; s++) head[i++] = *s;
    head[i++] = '%';
    if (truncated)
        for (const char *s = " (cut)"; *s; s++) head[i++] = *s;
    head[i] = 0;
    ui_text(2, 1, head, UI_GRAY);
    u32 pos = pages[page];
    u16 buf[64];
    for (int l = 0; l < LINES && pos < book_len; l++) {
        pos = line_at(pos, buf, 64);
        text16(TOP + LINE_H * l, buf, UI_WHITE);
    }
    if (page + 1 == known && known < MAX_PAGES && pos < book_len)
        pages[known++] = pos;          /* we now know where the next page starts */
}

static void draw_list(void)
{
    char line[24], num[11];
    int found = 0;
    ui_background();
    ui_text(4, 18, "Books", UI_GREEN);
    for (int n = 0, row = 0; n < SLOTS; n++) {
        if (!sizes[n])
            continue;
        found = 1;
        int i = 0;
        line[i++] = n == sel ? '>' : ' ';
        line[i++] = ' ';
        for (const char *s = "BOOK"; *s; s++) line[i++] = *s;
        line[i++] = (char)('0' + n);
        line[i++] = ' ';
        line[i++] = ' ';
        ui_dec(num, (sizes[n] + 1023) / 1024);
        for (const char *s = num; *s; s++) line[i++] = *s;
        for (const char *s = " KB"; *s; s++) line[i++] = *s;
        line[i] = 0;
        ui_text(4, 34 + 13 * row++, line, n == sel ? UI_GREEN : UI_WHITE);
    }
    if (!found) {
        ui_text(4, 34, "No books found.", UI_WHITE);
        ui_text(4, 47, "Copy BOOK0.TXT ...", UI_WHITE);
        ui_text(4, 60, "BOOK9.TXT to the", UI_WHITE);
        ui_text(4, 73, "player's top folder.", UI_WHITE);
    } else
        ui_text(4, 134, "center: read", UI_GRAY);
    ui_text(4, 148, "OPTION: back", UI_GRAY);
}

static void start(void)
{
    reading = 0;
    sel = 0;
    scan();
    dirty = 1;
}

static void move(int d)
{
    for (int i = 0; i < SLOTS; i++) {
        sel = (sel + d + SLOTS) % SLOTS;
        if (sizes[sel])
            break;
    }
    dirty = 1;
}

static int key(u32 ev)
{
    u32 k = EV_KEY(ev), t = EV_TYPE(ev);
    if (ev == KEY_EV(EV_RELEASE, KEY_OPTION))
        return 1;
    if (reading) {
        if (ev == KEY_EV(EV_RELEASE, KEY_BACK)) {
            reading = 0;
            dirty = 1;
        } else if (t == EV_PRESS || t == EV_REPEAT) {
            if ((k == KEY_DOWN || k == KEY_RIGHT) && page + 1 < known) {
                page++;
                dirty = 1;
            } else if ((k == KEY_UP || k == KEY_LEFT) && page > 0) {
                page--;
                dirty = 1;
            }
        }
        return 0;
    }
    if (t == EV_PRESS || t == EV_REPEAT) {
        if (k == KEY_UP || k == KEY_LEFT)
            move(-1);
        else if (k == KEY_DOWN || k == KEY_RIGHT)
            move(1);
        else if (k == KEY_PLAY && t == EV_PRESS && sizes[sel] && open_book(sel)) {
            reading = 1;
            dirty = 1;
        }
    }
    return 0;
}

static void draw(void)
{
    u32 now = ui_ticks();
    if (now - last_draw > 50)          /* no draw for 0.5 s: the screen was off, so repaint */
        dirty = 1;
    last_draw = now;
    if (!dirty)
        return;
    dirty = 0;
    if (reading)
        draw_page();
    else
        draw_list();
}

static void stop(void)
{
}

NWAPP_BIG("Reader", start, key, draw, stop);
