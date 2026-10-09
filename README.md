# Oreslang Stack CLI

**Oreslang-authored command dispatcher** for the Oreslang application framework.
This draft replaces the Rust implementation originally proposed in
[PR #2](https://github.com/ores-truffle-oreslang/oreslang-stack-cli/pull/2).
The source of the CLI's command admission rules is [`src/main.ores`](src/main.ores),
not Rust. The narrow [Bash launcher](bin/oreslang-stack) exists solely to invoke
[`flags-2-env`](https://github.com/flags-2-env/flags-2-env), start the
Oreslang runtime, execute an admitted host process, and create a source archive.

## CLI commands

```sh
oreslang-stack dev --root examples/hello-api
oreslang-stack build --root examples/hello-api
oreslang-stack deploy --root examples/hello-api --target oreslang-stack
```

| Command | Current behavior | Not yet implemented |
|---|---|---|
| `dev` | Verifies project manifest + entrypoint in Oreslang, then runs the entry once using Java/Graal Oreslang | File watching, hot reload, supervisors, dev HTTP server |
| `build` | Oreslang admits the project; real compiler `--check` must pass before `dist/oreslang-stack-source.tar.gz` is emitted | Compiled native/JVM/WASM artifact, provenance and packaging attestations |
| `deploy` | **Fails closed** with a nonzero exit status | Every host adapter, remote upload and admission receipt |

**A source bundle is not a compiled/deployable build.** The Oreslang LLVM
compiler does not currently support the runtime features used here.
`--backend llvm` is explicitly refused; do not treat a JVM/Graal success as
LLVM parity. `deploy` must never return success without a certified adapter.

## Dependencies and usage

Install the `flags2env` command from
[flags-2-env/flags-2-env](https://github.com/flags-2-env/flags-2-env)
and the **Java/Graal** Oreslang CLI executable (`oreslang` on your PATH).
Set `FLAGS2ENV_BIN` and/or `ORESLANG_BIN` to override their paths.

```sh
./bin/oreslang-stack --help
./bin/oreslang-stack dev --root examples/hello-api
./bin/oreslang-stack build --root examples/hello-api
```

`flags2env shell-env` evaluates the pinned, audited
[`.cli-flags.toml`](.cli-flags.toml) contract. Only recognized commands and
flags are admitted; `--root`, `--entry`, and `--backend` are shared flags.
The Oreslang guest sees only scoped environment keys and read access to the
selected project; it does not require general Java reflection or process spawn.

A project has `oreslang-stack.toml` and an Oreslang `src/main.ores` entrypoint
(by default). Existing route/page conventions and their RPC/Lambda
generation design are documented in [docs/GENERATION.md](docs/GENERATION.md),
but the former Rust generator has been **removed**, not falsely represented
as a working native-Oreslang implementation. Native route inventory, contract
validation, generation, and the real build/deploy backends remain outstanding
engineering work.

## Security and verification

- No Rust toolchain or Cargo dependency is used for this CLI.
- No fallback to Rust/JS/Python route generation.
- No `--allow-all` at the CLI admission boundary.
- Invalid or missing admission receipts fail closed.
- Project manifest and entrypoint symlinks are rejected; source archive
  production refuses symlinks within `src`.
- `deploy` is deliberately nonfunctional, never a pretend success.
- CI can exercise flag parsing and the **host bridge** with a mocked Oreslang
  interpreter. Such tests do **not** prove that the Oreslang source type-checks
  or runs in a real compiler. A separate real-Oreslang integration gate is
  required before considering this production-ready.

See [docs/NATIVE-CLI.md](docs/NATIVE-CLI.md) for boundary and acceptance criteria.
