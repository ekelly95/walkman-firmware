/* An app section: code runs in the shared overlay slot at 0x306c4a4 (where home, the music
 * menu and the other apps load), data at 0x3023010 starting with the app descriptor. */
ENTRY(descriptor)

SECTIONS
{
    .text 0x0306c4a4 : {
        *(.text .text.*)
        *(.rodata .rodata.*)
        . = ALIGN(4);
    }
    .data 0x03023010 : {
        KEEP(*(.descriptor))
        *(.data .data.*)
        *(.bss .bss.* COMMON)
        . = ALIGN(4);
    }
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.attributes) *(.comment) }
}
