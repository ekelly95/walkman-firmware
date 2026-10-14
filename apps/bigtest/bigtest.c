/* bigtest: checks the big-app memory. Its own file carries a 96 KiB table of known words (so the
 * launcher must load ~100 KiB), and it fills the 164 KiB heap with a pseudo-random pattern and
 * reads it back. Shows each result and how long it took. OPTION goes back to the launcher. */
#include "nwapp.h"
#include "ui.h"

#define TABLE_WORDS (96 * 1024 / 4)
#define PATTERN 0xa5c3e17bu

static const u32 table[TABLE_WORDS] = {[0 ... TABLE_WORDS - 1] = PATTERN};

static int step, dirty;
static u32 table_bad, heap_bad, t_table, t_heap;

static u32 next(u32 x)              /* xorshift: the heap pattern, reproducible from a seed */
{
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return x;
}

static void check_table(void)
{
    u32 t0 = ui_ticks();
    table_bad = 0;
    for (u32 i = 0; i < TABLE_WORDS; i++) {
        if (((volatile const u32 *)table)[i] != PATTERN)
            table_bad++;
    }
    t_table = ui_ticks() - t0;
}

static void check_heap(void)
{
    volatile u32 *heap = (volatile u32 *)NWAPP_HEAP;
    u32 words = NWAPP_HEAP_SIZE / 4, x = 0x12345678, t0 = ui_ticks();
    for (u32 i = 0; i < words; i++) {
        heap[i] = x = next(x);
    }
    x = 0x12345678;
    heap_bad = 0;
    for (u32 i = 0; i < words; i++) {
        if (heap[i] != (x = next(x)))
            heap_bad++;
    }
    t_heap = ui_ticks() - t0;
}

static void line(int y, const char *label, u32 value, const char *unit, u16 color)
{
    char s[32], n[11];
    int i = 0;
    ui_dec(n, value);
    for (const char *p = label; *p; p++) s[i++] = *p;
    for (const char *p = n; *p; p++) s[i++] = *p;
    for (const char *p = unit; *p; p++) s[i++] = *p;
    s[i] = 0;
    ui_text(4, y, s, color);
}

static void start(void)
{
    step = 0;
    dirty = 1;
}

static int key(u32 ev)
{
    return ev == (((u32)EV_RELEASE << 28) | KEY_OPTION);
}

static void draw(void)
{
    if (step == 1) { check_table(); step = 2; dirty = 1; }
    else if (step == 3) { check_heap(); step = 4; dirty = 1; }
    if (!dirty)
        return;
    dirty = 0;
    ui_background();
    ui_text(4, 18, "Big app memory test", UI_GREEN);
    line(36, "image: ", (u32)(__nwapp_end - (char *)NWAPP_LOAD) / 1024, " KiB", UI_WHITE);
    if (step >= 2) {
        line(52, "table bad words: ", table_bad, "", table_bad ? UI_RED : UI_GREEN);
        line(64, "  checked in ", t_table * 10, " ms", UI_GRAY);
    } else
        ui_text(4, 52, "checking table...", UI_WHITE);
    if (step >= 4) {
        line(84, "heap: ", NWAPP_HEAP_SIZE / 1024, " KiB", UI_WHITE);
        line(96, "heap bad words: ", heap_bad, "", heap_bad ? UI_RED : UI_GREEN);
        line(108, "  write+read in ", t_heap * 10, " ms", UI_GRAY);
    } else if (step >= 2)
        ui_text(4, 84, "checking heap...", UI_WHITE);
    ui_text(4, 148, "OPTION: back", UI_GRAY);
    if (step == 0 || step == 2)
        step++;                     /* show "checking..." first, run the check on the next pass */
}

static void stop(void)
{
}

NWAPP_BIG("Big test", start, key, draw, stop);
