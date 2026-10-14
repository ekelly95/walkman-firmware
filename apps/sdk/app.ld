/* A .BIN app: one flat image at NWAPP_LOAD (nwapp.h), header first, bss included as zeros. */
ENTRY(nwapp_header)

SECTIONS
{
    .bin 0x0306d000 : {
        KEEP(*(.nwapp))
        *(.text .text.*)
        *(.rodata .rodata.*)
        *(.data .data.*)
        *(.bss .bss.* COMMON)
        . = ALIGN(4);
        __nwapp_end = .;
    }
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.attributes) *(.comment) }
}
