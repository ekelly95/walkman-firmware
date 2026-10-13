// Decompile every function that references a string containing one of the given fragments.
// Arguments: <output file> <fragment> [<fragment> ...]. Works on any analyzed program; used on
// Sony's WmFwUpdater.dll to find the SCSI commands and on the firmware to follow debug strings.
//@category RKnano

import java.io.File;
import java.io.PrintWriter;
import java.util.LinkedHashMap;
import java.util.Map;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

public class DecompileByString extends GhidraScript {

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            throw new IllegalArgumentException("usage: DecompileByString.java <out file> <fragment>...");
        }
        Map<Function, String> found = new LinkedHashMap<>();
        for (int i = 1; i < args.length; i++) {
            if (args[i].startsWith("@")) {  // "@0x10020444": decompile the function at an address
                ghidra.program.model.address.Address a = toAddr(Long.decode(args[i].substring(1)));
                Function fn = getFunctionContaining(a);
                if (fn == null) {
                    disassemble(a);
                    fn = createFunction(a, null);
                }
                if (fn != null) {
                    found.put(fn, args[i]);
                }
            }
        }
        DataIterator it = currentProgram.getListing().getDefinedData(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Data d = it.next();
            if (!d.hasStringValue()) {
                continue;
            }
            String s = String.valueOf(d.getValue());
            for (int i = 1; i < args.length; i++) {
                if (!s.contains(args[i])) {
                    continue;
                }
                for (Reference ref : getReferencesTo(d.getAddress())) {
                    Function fn = getFunctionContaining(ref.getFromAddress());
                    if (fn != null) {
                        found.merge(fn, s, (a, b) -> a.contains(b) ? a : a + " | " + b);
                    } else {
                        println("DecompileByString: \"" + s + "\" referenced from " + ref.getFromAddress()
                            + " outside any function");
                    }
                }
            }
        }
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        try (PrintWriter w = new PrintWriter(new File(args[0]), "UTF-8")) {
            for (Map.Entry<Function, String> e : found.entrySet()) {
                Function fn = e.getKey();
                w.println("// ==== " + fn.getName() + " @ " + fn.getEntryPoint() + "  strings: " + e.getValue());
                DecompileResults res = decomp.decompileFunction(fn, 120, monitor);
                w.println(res.decompileCompleted() ? res.getDecompiledFunction().getC() : "/* " + res.getErrorMessage() + " */");
            }
        }
        decomp.dispose();
        println("DecompileByString: " + found.size() + " functions -> " + args[0]);
    }
}
