// Map an RKnano stage-3 image (stage3.bin from `nwe39x blobs`) into the current program.
// Run as a -preScript on a program created with the ARM:LE:32:Cortex language; argument: the path
// to stage3.bin. Any blocks already in the program (the placeholder import) are removed.
//
// Stage 3 is a list of sections {code_va, code_pa, code_sz, data_va, data_pa, data_sz, bss_pa,
// bss_sz}; *_va locate bytes in the file (offset = va - base), *_pa are run addresses. Many
// sections share run addresses (an overlay scheme), so the first block to claim an address range
// becomes a normal block and every later block that overlaps it becomes an overlay block named
// after its section, e.g. "s009_code".
//@category RKnano

import java.io.ByteArrayInputStream;
import java.io.File;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;

public class LoadRknanoStage extends GhidraScript {

    private record Range(long start, long end) {
        boolean overlaps(long s, long e) {
            return s < end && start < e;
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            throw new IllegalArgumentException("usage: LoadRknanoStage.java <stage3.bin>");
        }
        byte[] stage = Files.readAllBytes(new File(args[0]).toPath());
        ByteBuffer bb = ByteBuffer.wrap(stage).order(ByteOrder.LITTLE_ENDIAN);
        long base = Integer.toUnsignedLong(bb.getInt(0));
        int count = bb.getInt(4);

        Memory mem = currentProgram.getMemory();
        for (MemoryBlock b : mem.getBlocks()) {
            mem.removeBlock(b, monitor);
        }

        List<Range> claimed = new ArrayList<>();
        int normal = 0, overlays = 0;
        for (int i = 0; i < count; i++) {
            int o = 8 + 32 * i;
            long[] f = new long[8];
            for (int k = 0; k < 8; k++) {
                f[k] = Integer.toUnsignedLong(bb.getInt(o + 4 * k));
            }
            long codeVa = f[0], codePa = f[1], codeSz = f[2];
            long dataVa = f[3], dataPa = f[4], dataSz = f[5];
            long bssPa = f[6], bssSz = f[7];

            String[] kinds = {"code", "data", "bss"};
            long[][] parts = {{codePa, codeSz, codeVa}, {dataPa, dataSz, dataVa}, {bssPa, bssSz, -1}};
            for (int p = 0; p < 3; p++) {
                long pa = parts[p][0], sz = parts[p][1], va = parts[p][2];
                if (sz == 0) {
                    continue;
                }
                boolean overlay = claimed.stream().anyMatch(r -> r.overlaps(pa, pa + sz));
                String name = String.format("s%03d_%s", i, kinds[p]);
                Address start = toAddr(pa);
                MemoryBlock block;
                if (va >= 0) {
                    int off = (int) (va - base);
                    block = mem.createInitializedBlock(name, start,
                        new ByteArrayInputStream(stage, off, (int) sz), sz, monitor, overlay);
                } else {
                    block = mem.createUninitializedBlock(name, start, sz, overlay);
                }
                block.setRead(true);
                block.setWrite(p != 0);
                block.setExecute(p == 0);
                block.setComment(String.format("stage3 section %d %s, run %#x, file %s", i, kinds[p], pa,
                    va >= 0 ? String.format("%#x", va - base) : "-"));
                if (overlay) {
                    overlays++;
                } else {
                    claimed.add(new Range(pa, pa + sz));
                    normal++;
                }
                if (p == 0) {
                    Address entry = block.getStart();
                    addEntryPoint(entry);
                    disassemble(entry);
                }
            }
        }
        println(String.format("LoadRknanoStage: base %#x, %d sections -> %d normal blocks, %d overlays",
            base, count, normal, overlays));
    }
}
