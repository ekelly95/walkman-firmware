// Name what is known about the NW-E390 1.01 firmware, then decompile the firmware-file install
// routine to <outdir>/install_routine.c as a check that the memory map is right.
// Run as a -postScript after LoadRknanoStage.java; argument: an output directory.
//
// Names ending in "_maybe" are inferred from how they are called, not yet confirmed.
//@category RKnano

import java.io.File;
import java.io.PrintWriter;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.SourceType;

public class AnnotateRknano extends GhidraScript {

    // {block ("" = the normal block holding the address), address, name, comment}
    private static final String[][] FUNCTIONS = {
        {"", "0x3068888", "debug_printf", "printf-style debug log; strings start with \\n"},
        {"", "0x3057fda", "file_open_maybe", "(dir, name, mode) -> handle or -1; called with \"RKNANOFWIMG\""},
        {"", "0x305824a", "file_read_maybe", "(buf, len, handle) -> bytes read"},
        {"", "0x30581c8", "file_close_maybe", "(handle)"},
        {"", "0x305867e", "file_size_maybe", "(handle) -> size"},
        {"", "0x30586e0", "file_seek_maybe", "(offset, whence, handle)"},
        {"", "0x305a896", "file_delete_maybe", "called after a successful install (\"Delete fwfile!\")"},
        {"", "0x3058086", "file_rename_maybe",
            "(\"DEFAULT XML\", dir, L\"default-capability.xml\", ...): recreates the capability file after an install"},
        {"", "0x306200a", "lcd_blit",
         "(x, y, w, h, bpp, pixels): bpp 16 = RGB565 rows, bpp 1 = glyph bitmap in fg/bg colours"},
        {"", "0x3062774", "lcd_set_window_maybe", "(x0, y0, x1, y1) before pixel writes"},
        {"", "0x30626cc", "lcd_write_pixel_maybe", "(rgb565)"},
        {"", "0x3062878", "lcd_clear_rect", "(x0, y0, x1, y1): fills black; (0,14,127,159) is the area under the status bar"},
        {"", "0x3062110", "blit_picture_rows",
         "(x, y, w, h, data offset): reads pixel rows from ImageLogicAddress + offset in 512-byte chunks and blits them"},
        {"", "0x3062212", "draw_picture", "(index, dx, dy): picture at its stored x,y plus dx,dy"},
        {"", "0x3062400", "draw_picture_at", "(index, x, y): reads the 16-byte entry at ImageLogicAddress + 0x20 + 16*index"},
        {"", "0x3062438", "res_read_maybe", "(logical address, buf, len) via 0x3066c34"},
        {"", "0x306c9cc", "image_select",
         "(n): ImageLogicAddress (RAM 0x4b5c) = imageres[n] offset read from the firmware header; logs ImageLogicAddress"},
        {"", "0x3061c82", "string_get_maybe", "(string id, buf, max chars)"},
        {"", "0x3061f4a", "text_draw_maybe", "(x, y, w, h, ?, string id)"},
        {"s018_code", "0x306cc70", "music_menu_draw",
         "6 rows of 26 px from y=30: separator 133 at y+25, highlight 109 at y, icon at x=6 y+3, text at x=28; "
         + "rows come from the table at s018 data 0x3023010: {u16 picture, u16 string id}"},
        {"", "0x30628d4", "lcd_flush_maybe", "called after each lcd_fill_rect_maybe"},
        {"", "0x3060f30", "watchdog_kick_maybe", "called once per 8 KiB chunk while flashing"},
        {"s009_code", "0x306cc96", "fw_install_from_file",
            "Installs \\RKNANOFW.IMG: checks magic RKnanoFW, file size = roundup(size + 16 KiB, 1 MiB) + 4, "
            + "backup header at `size` equal to the header; writes NAND in 0x2000 chunks; deletes the file. "
            + "No version or signature check."},
        {"s009_code", "0x306cb4e", "fw_write_image_maybe", "writes the image to NAND with a progress bar"},
        {"s009_code", "0x306cafe", "fw_nand_write_maybe", "takes the 'NAND' lock (0x444e414e) around a write"},
        {"s009_code", "0x306ca52", "fw_draw_progress_maybe", "draws the progress bar while flashing"},
        {"s009_code", "0x306cf94", "s009_memcmp_maybe", "section-local memcmp"},
        {"s009_code", "0x306cf9e", "s009_memset_maybe", "section-local memset"},
    };

    private Address resolve(String blockName, String addr) {
        long offset = Long.decode(addr);
        if (blockName.isEmpty()) {
            return toAddr(offset);
        }
        MemoryBlock block = currentProgram.getMemory().getBlock(blockName);
        if (block == null) {
            throw new IllegalStateException("no block " + blockName);
        }
        return block.getStart().getAddressSpace().getAddress(offset);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        File outdir = new File(args.length > 0 ? args[0] : ".");
        outdir.mkdirs();

        for (String[] f : FUNCTIONS) {
            Address a = resolve(f[0], f[1]);
            disassemble(a);
            Function fn = getFunctionAt(a);
            if (fn == null) {
                fn = createFunction(a, f[2]);
            }
            if (fn == null) {
                println("could not create a function at " + a);
                continue;
            }
            fn.setName(f[2], SourceType.USER_DEFINED);
            fn.setComment(f[3]);
        }

        int functions = currentProgram.getFunctionManager().getFunctionCount();
        println("AnnotateRknano: " + functions + " functions in the program");

        Function install = getFunctionAt(resolve("s009_code", "0x306cc96"));
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        DecompileResults res = decomp.decompileFunction(install, 120, monitor);
        try (PrintWriter w = new PrintWriter(new File(outdir, "install_routine.c"), "UTF-8")) {
            w.println(res.decompileCompleted() ? res.getDecompiledFunction().getC() : "/* " + res.getErrorMessage() + " */");
        }
        try (PrintWriter w = new PrintWriter(new File(outdir, "summary.txt"), "UTF-8")) {
            w.println("functions: " + functions);
            w.println("blocks: " + currentProgram.getMemory().getBlocks().length);
        }
        decomp.dispose();
    }
}
