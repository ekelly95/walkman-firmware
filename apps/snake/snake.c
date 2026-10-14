/* snake: the pad steers; its center pauses, and starts a new game after a crash.
 * OPTION goes back to the launcher. The snake speeds up as it grows. The screen stays on while a
 * game runs (screen_hold), and times out as usual when paused or after a crash. */
#include "nwapp.h"
#include "ui.h"

#define CELL 8
#define COLS 16                  /* 128 px */
#define ROWS 17                  /* 136 px */
#define TOP 20                   /* field from y=20 to 155; the score line is above it */
#define CELLS (COLS * ROWS)

#define C_SNAKE UI_GREEN
#define C_HEAD 0x07e0
#define C_FOOD UI_RED
#define C_WALL 0x39e7

enum { PLAYING, PAUSED, OVER };

static u16 body[CELLS];          /* ring buffer of cells (y * COLS + x), head at body[head] */
static u8 occupied[CELLS];
static int head, length, grow, dir, next_dir, food, state, score, best, redraw_all, redraw_score;
static u32 last_step;
static int held;                 /* we hold the screen on while PLAYING */

static void set_state(int s)
{
    state = s;
    if (s == PLAYING && !held) {
        screen_hold();
        held = 1;
    } else if (s != PLAYING && held) {
        screen_release();
        held = 0;
    }
}

static const int DX[4] = {0, 1, 0, -1}, DY[4] = {-1, 0, 1, 0};   /* up, right, down, left */

static void cell(int c, u16 color)
{
    int x = (c % COLS) * CELL, y = TOP + (c / COLS) * CELL;
    ui_fill(x + 1, y + 1, x + CELL - 2, y + CELL - 2, color);   /* 6x6 with a 1 px gap */
}

static void erase(int c)
{
    int x = (c % COLS) * CELL, y = TOP + (c / COLS) * CELL;
    ui_fill(x, y, x + CELL - 1, y + CELL - 1, UI_BLACK);
}

static void place_food(void)
{
    if (length >= CELLS) {
        food = -1;
        return;
    }
    int c = (int)(ui_random() % CELLS);
    while (occupied[c])
        c = (c + 1) % CELLS;
    food = c;
}

static void new_game(void)
{
    for (int i = 0; i < CELLS; i++)
        occupied[i] = 0;
    length = 3;
    head = 2;
    for (int i = 0; i < 3; i++) {
        body[i] = (u16)((ROWS / 2) * COLS + 4 + i);
        occupied[body[i]] = 1;
    }
    grow = 0;
    dir = next_dir = 1;
    score = 0;
    set_state(PLAYING);
    place_food();
    last_step = ui_ticks();
    redraw_all = 1;
}

static int period(void)          /* ticks (10 ms) per step: 150 ms, down to 60 ms */
{
    int p = 15 - score / 4;
    return p < 6 ? 6 : p;
}

static void step(void)
{
    if ((next_dir ^ dir) != 2)   /* no reversing into yourself */
        dir = next_dir;
    int h = body[head], x = h % COLS + DX[dir], y = h / COLS + DY[dir];
    if (x < 0 || x >= COLS || y < 0 || y >= ROWS) {
        set_state(OVER);
        redraw_score = 1;
        return;
    }
    int n = y * COLS + x;
    int tail = body[(head - length + 1 + CELLS) % CELLS];
    if (occupied[n] && !(n == tail && !grow)) {
        set_state(OVER);
        redraw_score = 1;
        return;
    }
    if (grow)
        grow--, length++;
    else {
        occupied[tail] = 0;
        erase(tail);
    }
    cell(h, C_SNAKE);
    head = (head + 1) % CELLS;
    body[head] = (u16)n;
    occupied[n] = 1;
    cell(n, C_HEAD);
    if (n == food) {
        score++;
        if (score > best)
            best = score;
        grow += 2;
        place_food();
        if (food >= 0)
            cell(food, C_FOOD);
        redraw_score = 1;
    }
}

static void labeled(int x, const char *label, int value, u16 color)
{
    char line[20], num[11];
    int i = 0;
    ui_dec(num, (u32)value);
    for (const char *s = label; *s; s++) line[i++] = *s;
    for (const char *s = num; *s; s++) line[i++] = *s;
    line[i] = 0;
    ui_text(x, 3, line, color);
}

static void draw_score(void)
{
    ui_fill(0, 0, 127, TOP - 2, UI_BLACK);
    labeled(2, "Score ", score, UI_WHITE);
    if (state == PAUSED)
        ui_text(76, 3, "PAUSED", UI_GREEN);
    else if (state == OVER)
        ui_text(76, 3, "CRASH!", UI_RED);
    else
        labeled(76, "Best ", best, UI_GRAY);
}

static void draw_all(void)
{
    ui_fill(0, 0, 127, 159, UI_BLACK);
    ui_fill(0, TOP - 1, 127, TOP - 1, C_WALL);
    for (int i = 0; i < length; i++)
        cell(body[(head - i + CELLS) % CELLS], i ? C_SNAKE : C_HEAD);
    if (food >= 0)
        cell(food, C_FOOD);
    draw_score();
}

static void start(void)
{
    best = 0;
    new_game();
}

static int key(u32 ev)
{
    u32 k = EV_KEY(ev), t = EV_TYPE(ev);
    if (k == KEY_OPTION && t == EV_RELEASE)
        return 1;
    if (t != EV_PRESS)
        return 0;
    ui_random();                 /* key timing stirs the food positions */
    if (k == KEY_PLAY) {
        if (state == OVER)
            new_game();
        else {
            set_state(state == PAUSED ? PLAYING : PAUSED);
            last_step = ui_ticks();
            redraw_score = 1;
        }
    } else if (state == PLAYING) {
        if (k == KEY_UP) next_dir = 0;
        else if (k == KEY_RIGHT) next_dir = 1;
        else if (k == KEY_DOWN) next_dir = 2;
        else if (k == KEY_LEFT) next_dir = 3;
    }
    return 0;
}

static u32 last_draw;

static void draw(void)
{
    u32 now = ui_ticks();
    if (now - last_draw > 50)    /* no draw for 0.5 s: the screen was off, so repaint it */
        redraw_all = 1;
    last_draw = now;
    if (redraw_all) {
        redraw_all = redraw_score = 0;
        draw_all();
    }
    if (state == PLAYING && now - last_step >= (u32)period()) {
        last_step = now;
        step();
    }
    if (redraw_score) {
        redraw_score = 0;
        draw_score();
    }
}

static void stop(void)
{
    set_state(OVER);             /* releases the screen */
}

NWAPP("Snake", start, key, draw, stop);
