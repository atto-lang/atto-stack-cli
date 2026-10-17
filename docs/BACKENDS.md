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

## .NET NativeAOT / ORW1

The .NET backend candidate now exposes a statically linked
`oreslang-app --worker` process protocol, **ORW1 v1**:

- framed binary stdio with a 28-byte header;
- strict UTF-8 payloads capped at 1 MiB;
- invocation deadline capped at 30 seconds;
- strictly increasing request IDs per worker generation;
- opaque unknown guest failures retire the worker;
- ambient environment is cleared by the generic launcher;
- untrusted workers are refused by the generic launcher and require an
  OS-sandbox host.

The current .NET guest ABI remains `main() -> i64`; ORW1 invocation payloads
must therefore be empty. It is not yet the provider-neutral `String -> String`
Lambda ABI.

Scintilla's existing reusable child protocol is line-oriented JSON, not ORW1.
Accordingly `dotnet + scintilla-run` remains planned until an explicit ORW1
adapter/port driver executes successfully.

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

The executable pair is currently **`--backend graal --host local`**. Both
selectors are parsed by `flags-2-env`; the Oreslang-native dispatcher owns the
backend/host matrix and fails closed on every other pair.

Known prospective routes are recognized so diagnostics preserve architectural
intent without implying execution:

- `graal + graal-show`: planned, adapter/runtime receipt pending;
- `llvm + scintilla-run` / `litegraph`: planned native targets;
- `llvm + wasm-xprs` / `lunatic-lorry`: planned `wasm32-wasi` targets;
- `wasm + wasm-xprs` / `lunatic-lorry`: future direct-WASM backend;
- `dotnet + scintilla-run`: planned NativeAOT route, ORW1 adapter pending;
- `js + iso-lattes`: future JavaScript backend.

Unknown backends and mismatched backend/host pairs are rejected separately from
known-but-not-executable routes.

Future command shape:

```text
oreslang-stack build --backend graal --host graal-show  # planned; denied today
oreslang-stack build --backend llvm --target x86_64-linux --host scintilla-run
oreslang-stack build --backend llvm --target wasm32-wasi --host wasm-xprs
oreslang-stack build --backend llvm --target wasm32-wasi --host lunatic-lorry
oreslang-stack build --backend dotnet --host scintilla-run  # ORW1 adapter pending
oreslang-stack build --backend js --host iso-lattes
```

These examples define the interface direction; they are not currently admitted
commands or deployment claims.
