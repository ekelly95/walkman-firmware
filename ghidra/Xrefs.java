// Cross-reference helper for the overlay firmware. Arguments: <output file> then any of
//   @0xADDR                decompile the function containing ADDR (s001_code::0xADDR for an overlay)
//   callers@0xADDR         list every function (in any overlay) that references ADDR, and decompile each
//   range@0xSTART-0xEND    one line per function in that range: address, name, parameter count
//@category RKnano

import java.io.File;
import java.io.PrintWriter;
import java.util.LinkedHashMap;
import java.util.Map;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class Xrefs extends GhidraScript {

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            throw new IllegalArgumentException("usage: Xrefs.java <out file> (@addr | callers@addr | range@a-b)...");
        }
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        Map<Function, String> todo = new LinkedHashMap<>();
        StringBuilder listing = new StringBuilder();
        for (int i = 1; i < args.length; i++) {
            String a = args[i];
            if (a.startsWith("@")) {
                Function f = functionAt(parseAddr(a.substring(1)));
                if (f != null) todo.put(f, a);
            } else if (a.startsWith("callers@")) {
                Address target = parseAddr(a.substring(8));
                listing.append("// callers of ").append(target).append(":\n");
                ReferenceIterator it = currentProgram.getReferenceManager().getReferencesTo(target);
                Address thumb = target.add(1);
                while (it.hasNext()) {
                    Reference r = it.next();
                    Function f = getFunctionContaining(r.getFromAddress());
                    listing.append("//   ").append(r.getFromAddress()).append(" ").append(r.getReferenceType())
                           .append(f == null ? " (no function)" : " in " + f.getName() + " @ " + f.getEntryPoint()).append("\n");
                    if (f != null) todo.put(f, "caller of " + target);
                }
                it = currentProgram.getReferenceManager().getReferencesTo(thumb);
                while (it.hasNext()) {
                    Reference r = it.next();
                    Function f = getFunctionContaining(r.getFromAddress());
                    listing.append("//   ").append(r.getFromAddress()).append(" ").append(r.getReferenceType()).append(" (thumb ptr)")
                           .append(f == null ? " (no function)" : " in " + f.getName() + " @ " + f.getEntryPoint()).append("\n");
                    if (f != null) todo.put(f, "pointer to " + target);
                }
            } else if (a.startsWith("range@")) {
                String[] se = a.substring(6).split("-");
                Address s = parseAddr(se[0]), e = parseAddr(se[1]);
                listing.append("// functions in ").append(s).append("-").append(e).append(":\n");
                for (Function f : currentProgram.getFunctionManager().getFunctions(s, true)) {
                    if (f.getEntryPoint().compareTo(e) > 0) break;
                    listing.append("//   ").append(f.getEntryPoint()).append(" ").append(f.getName())
                           .append(" params=").append(f.getParameterCount()).append(" size=")
                           .append(f.getBody().getNumAddresses()).append("\n");
                }
            }
        }
        try (PrintWriter out = new PrintWriter(new File(args[0]))) {
            out.print(listing);
            for (Map.Entry<Function, String> e : todo.entrySet()) {
                Function f = e.getKey();
                out.printf("%n// ==== %s @ %s  (%s)%n", f.getName(), f.getEntryPoint(), e.getValue());
                DecompileResults res = dec.decompileFunction(f, 60, monitor);
                out.println(res.getDecompiledFunction() != null ? res.getDecompiledFunction().getC() : "// decompile failed: " + res.getErrorMessage());
            }
        }
        println("Xrefs: " + todo.size() + " functions -> " + args[0]);
    }

    // "0x306ca1c" in the default space, or "s001_code::0x306ca1c" in an overlay.
    private Address parseAddr(String text) {
        int sep = text.indexOf("::");
        if (sep < 0) return toAddr(Long.decode(text));
        Address a = currentProgram.getAddressFactory().getAddress(text.replace("::0x", "::"));
        if (a == null) throw new IllegalArgumentException("no such address: " + text);
        return a;
    }

    private Function functionAt(Address a) {
        Function f = getFunctionContaining(a);
        if (f == null) {
            disassemble(a);
            f = createFunction(a, null);
        }
        return f;
    }
}
