/* launcher: app slot 7 (Ebook, compiled out by Sony), opened from the home menu's Photos icon.
 * Lists \APP0.BIN .. \APP9.BIN from the player's drive and runs the one picked: the .BIN is
 * read to NWAPP_LOAD and the launcher forwards keys and draw calls to it (nwapp.h).
 *
 * List: up/left move up, down/right move down, the pad center opens, OPTION goes home.
 * In an app: hold BACK to come back to the list, whatever the app does with keys.
 * Every key event restarts the screen timeout; apps that animate without input (games) hold the
 * screen on with screen_hold/screen_release. */
#include "nwapp.h"
#include "ui.h"

#define SLOTS 10
#define ROW0 34
#define ROW_H 13
#define CHUNK 2048
#define KEY_EV(type, key) (((u32)(type) << 28) | (key))

static char names[SLOTS][16];   /* "" = no app in that slot */
static int count, sel, dirty;
static const struct nwapp *running;
static char status[24];

static void name83(char out[12], int n)   /* "APPn    BIN" */
{
    const char *s = "APP0    BIN";
    for (int i = 0; i < 12; i++) out[i] = s[i];
    out[3] = (char)('0' + n);
}

static void copy_name(char *d, const char *s)
{
    int i = 0;
    while (i < 15 && s[i]) { d[i] = s[i]; i++; }
    d[i] = 0;
}

static void scan(void)
{
    count = 0;
    for (int n = 0; n < SLOTS; n++) {
        char nm[12];
        struct nwapp h;
        names[n][0] = 0;
        name83(nm, n);
        int f = file_open("\\", nm, "R");
        if (f < 0)
            continue;
        if (file_read(&h, sizeof h, f) == sizeof h && h.magic == NWAPP_MAGIC) {
            copy_name(names[n], h.name);
            if (!names[n][0])
                copy_name(names[n], "(no name)");
            count++;
        }
        file_close(f);
    }
    if (sel >= SLOTS || !names[sel][0])
        for (sel = 0; sel < SLOTS && !names[sel][0]; sel++)
            ;
}

static void fail(const char *why)
{
    copy_name(status, why);
    dirty = 1;
}

static void run(int n)
{
    char nm[12];
    u8 *mem = (u8 *)NWAPP_LOAD;
    const struct nwapp *h = (const struct nwapp *)NWAPP_LOAD;
    name83(nm, n);
    int f = file_open("\\", nm, "R");
    if (f < 0)
        { fail("cannot open file"); return; }
    unsigned size = file_size(f), got = 0;
    if (size < sizeof *h || size > NWAPP_MAX) {
        file_close(f);
        fail("file too big");
        return;
    }
    while (got < size) {
        unsigned want = size - got < CHUNK ? size - got : CHUNK;
        unsigned r = file_read(mem + got, want, f);
        if (!r)
            break;
        got += r;
    }
    file_close(f);
    if (got != size)
        { fail("read error"); return; }
    if (h->magic != NWAPP_MAGIC || h->abi != NWAPP_ABI || h->load != NWAPP_LOAD
        || h->end < NWAPP_LOAD + size || h->end > NWAPP_LOAD + NWAPP_MAX)
        { fail("not a v1 app"); return; }
    for (u8 *p = mem + size; p < (u8 *)h->end; p++)   /* bss beyond the file, if any */
        *p = 0;
    status[0] = 0;
    running = h;
    running->start();
}

static void back_to_list(void)
{
    if (running)
        running->stop();
    running = 0;
    scan();
    dirty = 1;
}

static void start(u8 *msg)
{
    (void)msg;
    running = 0;
    status[0] = 0;
    scan();
    dirty = 1;
}

static int event(void)
{
    return 0;
}

static void move(int d)
{
    for (int i = 0; i < SLOTS; i++) {
        sel = (sel + d + SLOTS) % SLOTS;
        if (names[sel][0])
            break;
    }
    dirty = 1;
}

static int keys(void)
{
    u32 ev = key_event();
    if (!ev)
        return 0;
    screen_activity();   /* a key press restarts the screen timeout, as in Sony's menus */
    if (running) {
        if (ev == KEY_EV(EV_LONG, KEY_BACK) || running->key(ev))
            back_to_list();
        return 0;
    }
    if (ev == KEY_EV(EV_RELEASE, KEY_OPTION)) {
        static const u8 home_msg[28];   /* home: highlight entry id 0, the Photos slot */
        app_switch(0, home_msg);
        return 1;
    }
    if (EV_TYPE(ev) == EV_PRESS || EV_TYPE(ev) == EV_REPEAT) {
        u32 k = EV_KEY(ev);
        if (k == KEY_UP || k == KEY_LEFT)
            move(-1);
        else if (k == KEY_DOWN || k == KEY_RIGHT)
            move(1);
        else if (k == KEY_PLAY && EV_TYPE(ev) == EV_PRESS && count)
            run(sel);
    }
    return 0;
}

static void draw(void)
{
    if (running) {
        running->draw();
        return;
    }
    if (!dirty)
        return;
    dirty = 0;
    ui_background();
    ui_text(4, 18, "Apps", UI_GREEN);
    if (!count) {
        ui_text(4, ROW0, "No apps found.", UI_WHITE);
        ui_text(4, ROW0 + ROW_H, "Copy APP0.BIN ...", UI_WHITE);
        ui_text(4, ROW0 + 2 * ROW_H, "APP9.BIN to the", UI_WHITE);
        ui_text(4, ROW0 + 3 * ROW_H, "player's top folder.", UI_WHITE);
    }
    for (int n = 0, row = 0; n < SLOTS; n++) {
        if (!names[n][0])
            continue;
        char line[24] = {n == sel ? '>' : ' ', ' ', 'A', 'P', 'P', (char)('0' + n), ' '};
        copy_name(line + 7, names[n]);
        ui_text(4, ROW0 + ROW_H * row++, line, n == sel ? UI_GREEN : UI_WHITE);
    }
    if (status[0])
        ui_text(4, 134, status, UI_GREEN);
    else if (count)
        ui_text(4, 134, "center: run", UI_GRAY);
    ui_text(4, 148, "OPTION: home", UI_GRAY);
}

static void stop(void)
{
    if (running)
        running->stop();
    running = 0;
}

__attribute__((section(".descriptor"), used))
const struct app descriptor = {0, 0, event, keys, draw, start, stop};
