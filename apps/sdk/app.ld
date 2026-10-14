/* A .BIN app: one flat image at NWAPP_LOAD (nwapp.h), header first. bss is not in the file: the
 * launcher zeroes from the end of the file up to the header's `end` (__nwapp_end). */
ENTRY(nwapp_header)

SECTIONS
{
    .bin 0x0306d000 : {
        KEEP(*(.nwapp))
        *(.text .text.*)
        *(.rodata .rodata.*)
        *(.data .data.*)
        . = ALIGN(4);
    }
    .bss (NOLOAD) : {
        *(.bss .bss.* COMMON)
        . = ALIGN(4);
        __nwapp_end = .;
    }
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.attributes) *(.comment) }
}
