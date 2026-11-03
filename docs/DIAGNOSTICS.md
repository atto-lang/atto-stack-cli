# Compiler diagnostics contract (proposed)

This is the **target contract** for all native Oreslang compilers, not a claim
that Graal, LLVM, WASM, .NET or the Stack CLI implement every item today.

## Default build/check behavior

- Show up to **five independent errors for the whole invocation**, not merely
  the first, ordered deterministically by source unit and source position.
- Every error has a phase (`lex`, `parse`, `import`, `type`, `ownership`,
  `lowering`, `link`, or `artifact`), stable error code, project-relative
  path/source unit, available module and namespace, one-based line/column and,
  where safe, a bounded source excerpt with caret and actionable message.
- If an issue originates in an imported source, use the *imported* unit as its
  primary location. Link-time context can add a bounded "imported from" note.
- Print diagnostics and final summary to **stderr**; successful build receipts
  and intended artifact paths go to stdout. Build/check failure exits nonzero.
- Prefer paths relative to the project workspace; do not leak absolute temporary
  CI paths, credentials, raw host exceptions or the contents of unrelated files.
- Issue collection is bounded in CPU, memory, number of error records and
  emitted bytes. Warnings have separate accounting from errors.
- Parser recovery should resume only at proven-safe declaration boundaries,
  and type/ownership analysis must never proceed using invented malformed
  AST nodes. Suppress cascades from an already-rejected symbol.
- Any failure prevents publishing a **new** build artifact. An existing
  artifact must not be misrepresented as the product of the failed build.

Example target rendering:

```text
error[E-PARSE-001] src/handlers/users.ores:12:9 (module: users; phase: parse)
  12 | const id = ;
     |            ^ expected expression

error[E-TYPE-003] src/payments/charge.ores:44:17 (module: payments; phase: type)
  44 | return "paid";
     |        ^ expected bool, found String

build failed: 2 errors (maximum shown: 5); no artifact emitted
```

## Current implemented slice

The Stack CLI bridge checks all `.ores` files in a deterministic source
inventory and now presents up to **five failing files**, with project-relative
unit labels and bounded compiler diagnostic output from both stderr and stdout.
Each emitted stream is truncated to 4096 bytes, terminal control characters
are replaced, the configured project root is removed from displayed diagnostics,
and the compiler's maximum file output size is capped at 64 MiB per file.
Compiler stdout cannot forge a successful build receipt. This means **one
independent failure per compiler invocation/file** today, not five separate
errors inside a malformed file. The Java/Graal companion work improves typed
source-unit/module attribution, and LLVM now prints bounded context. Actual
native frontend diagnostic recovery across phases remains separate work.

## Required backend qualification

Test zero/one/five/six independent issues across both multiple files and a
single file; nested imports, same-name modules, invalid UTF-8, multiline and
symlinked filenames, malicious escape characters, and missing import targets;
stable ordering, no duplicate cascades, bounded resource usage, consistent
nonzero exits, and no artifact publication on failure. Test real Graal and LLVM
compilation; an interpreter mock validates only host orchestration.
