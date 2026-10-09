# Native Oreslang CLI — implementation and remaining work

## Boundary

`src/main.ores` owns command selection, backend rejection, and project
admission. The `flags-2-env` TOML schema owns argv validation, defaults and
subcommand-specific options. `bin/oreslang-stack` is a deliberately minimal
host bridge: it loads flags2env exports, runs the guest CLI, checks an exact
guest action receipt, execs the Oreslang application for `dev`, or invokes
the real compiler check and archives the source for `build`.

The shell runner is **not** a general-purpose application framework or route
generator. Oreslang has no admitted capability-safe child-process execution
API that would eliminate this bridge today. That missing primitive must be
designed as a capability-scoped host API, not replaced by importing
`java.lang.ProcessBuilder` or granting unsafe interop.

## Current state and non-goals

- `dev`: launch-once proof. No watch or actor hot replacement.
- `build`: typecheck plus source archive. Not Graal native-image, JVM
  distribution, LLVM object file or WASM bundle.
- `deploy`: hard refusal until compiler/backend + runtime admission and
  reproducible deployment receipts are available.
- The 800-line Rust route/RPC/Lambda generator formerly in this draft was
  removed: it **has not been ported** and must not be claimed implemented.
- Role and route/page conventions in `docs/GENERATION.md` are a **design
  contract**, not a tested generator or active implementation.

## Before merge

1. Run `src/main.ores` with the real Java/Graal compiler against the native
   sample projects and assert its exact receipts; check negative inputs.
2. Give the guest Oreslang standard library the safe directory traversal,
   symlink metadata and atomic file-write primitives necessary to port the
   route/page inventory + generation contract completely.
3. Port generator/contract validation into Oreslang source and compare against
   golden fixtures including authored-file overwrite refusal and orphan files.
4. Implement genuine `dev` watch + actor lifecycle semantics through Oreslang,
   and real `build` output with backend-specific provenance.
5. Implement and certify independent host adapters before enabling `deploy`.
   No LLVM/Graal parity claims without separate compiler checks.

## Threat model

A malicious project must never be executed by `build`, and `deploy` must
not open a network connection, upload or run user source while unsupported.
The caller still controls the local project and chosen toolchain. The
bootstrap trusts the repository's audited flags config and an explicitly
installed Oreslang binary; it rejects unknown flags. External host-process
execution is not claimed to be sandboxed.
