/* The .BIN app format the launcher loads: a flat image linked at NWAPP_LOAD (app.ld), starting
 * with this header. Declare it once per app with NWAPP(...). */
#ifndef NWAPP_H
#define NWAPP_H

#include "fw.h"

#define NWAPP_MAGIC 0x5041574eu   /* "NWAP" */
#define NWAPP_ABI   1
#define NWAPP_LOAD  0x0306d000u    /* in the app overlay region, after the launcher */
#define NWAPP_MAX   0x4e00u        /* up to 0x3071e00, below section 14 at 0x3071e64 */

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
#define NWAPP(title, start, key, draw, stop) \
    __attribute__((section(".nwapp"), used)) const struct nwapp nwapp_header = \
        {NWAPP_MAGIC, NWAPP_ABI, NWAPP_LOAD, (u32)__nwapp_end, title, start, key, draw, stop}

#endif
