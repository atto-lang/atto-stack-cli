# Oreslang Stack backends and execution hosts

Oreslang Stack separates **backend selection** from **execution host selection**.

A backend answers: *what artifact does Oreslang compile to?*

A host answers: *where and under which isolation boundary does that artifact
execute?*

## Governed prospective matrix

| Backend | Artifact | Host | Isolation |
| --- | --- | --- | --- |
| Graal | Graal runtime / Native Image | `graal-show` | Graal polyglot/native isolate |
| LLVM native | native executable/library | `scintilla-run` | worker process |
| LLVM native | native executable/library | `litegraph` | specialized native/GPU host |
| LLVM WASM | `wasm32-wasi` | `wasm-xprs` | WASM instance |
| LLVM WASM | `wasm32-wasi` | `lunatic-lorry` | WASM actor/process |
| direct WASM | `wasm32-wasi` | `wasm-xprs` / `lunatic-lorry` | WASM |
| .NET NativeAOT | standalone native executable | `scintilla-run` | worker process; hostile code additionally requires OS sandbox |
| JavaScript | ESM | `iso-lattes` | JS isolate |

The comparison authority for this matrix lives in
`ORESoftware/ores-comparisons/shared/oreslang-backend-host-matrix.json`.

## .NET isolation

The .NET backend does support strong isolation, but not by treating
`AssemblyLoadContext` as a sandbox.

The intended production path is:

```text
Oreslang
   -> .NET CIL
   -> NativeAOT executable
   -> scintilla-run worker process
   -> optional/required OS sandbox for untrusted workloads
```

A collectible `AssemblyLoadContext` is useful for development-time assembly
versioning and unloadability. It is not a security boundary and is not part of
the strict NativeAOT release profile.

For hostile portable code, use a separately compiled WASM artifact:

```text
Oreslang -> LLVM/WASM or direct WASM -> wasm-xprs / lunatic-lorry
```

A .NET process embedding a WASM engine does not turn arbitrary CIL into
sandboxed WASM.

## Current CLI admission

The released/executable CLI path is still Java/Graal only. `--backend llvm`
already fails closed, and the CLI must continue to reject .NET/WASM/JS
execution until each backend produces a real artifact and the selected host
adapter has an exact-head runtime receipt.

Future command shape:

```text
oreslang-stack build --backend graal --host graal-show
oreslang-stack build --backend llvm --target x86_64-linux --host scintilla-run
oreslang-stack build --backend llvm --target wasm32-wasi --host wasm-xprs
oreslang-stack build --backend llvm --target wasm32-wasi --host lunatic-lorry
oreslang-stack build --backend dotnet --host scintilla-run
oreslang-stack build --backend js --host iso-lattes
```

These examples define the interface direction; they are not currently admitted
commands or deployment claims.
