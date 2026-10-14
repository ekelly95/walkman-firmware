/* The .BIN app format the launcher loads: a flat image linked at NWAPP_LOAD (app.ld), starting
 * with this header. Declare it once per app with NWAPP(...). */
#ifndef NWAPP_H
#define NWAPP_H

#include "fw.h"

#define NWAPP_MAGIC 0x5041574eu   /* "NWAP" */
#define NWAPP_ABI   1              /* small app: music keeps playing */
#define NWAPP_ABI_BIG 2            /* big app: the launcher stops music and background tasks first */
#define NWAPP_LOAD  0x0306d000u    /* in the app overlay region, after the launcher */
#define NWAPP_MAX   0x4e00u        /* small: up to 0x3071e00, below section 14 (audio) at 0x3071e64 */
#define NWAPP_BIG_MAX 0x22000u     /* big: up to 0x308f000, below section 2's live data at 0x3090000 */

/* Big apps also get this much RAM in the overlay data region, which the audio code and USB mode
 * use otherwise. Contents do not survive leaving the app. */
#define NWAPP_HEAP      ((void *)0x03024000)
#define NWAPP_HEAP_SIZE 0x29000u   /* to 0x304d000 */

struct nwapp {
    u32 magic, abi;
    u32 load, end;                 /* link address and end of bss: the memory the app needs */
    char name[16];
    void (*start)(void);
    int (*key)(u32 ev);            /* a key event (see key_event); nonzero: back to the launcher */
    void (*draw)(void);            /* every pass of the app loop: redraw only what changed */
    void (*stop)(void);
};

extern char __nwapp_end[];
#define NWAPP_DECLARE(abi, title, start, key, draw, stop) \
    __attribute__((section(".nwapp"), used)) const struct nwapp nwapp_header = \
        {NWAPP_MAGIC, abi, NWAPP_LOAD, (u32)__nwapp_end, title, start, key, draw, stop}
#define NWAPP(title, start, key, draw, stop) NWAPP_DECLARE(NWAPP_ABI, title, start, key, draw, stop)
#define NWAPP_BIG(title, start, key, draw, stop) NWAPP_DECLARE(NWAPP_ABI_BIG, title, start, key, draw, stop)

#endif
