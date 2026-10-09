# Oreslang Stack CLI

**The CLI implementation is Oreslang source.** The command dispatcher,
recursive file-route discovery, role validation, route JSON inventory, and
RPC/Lambda source generation live in [`src/main.ores`](src/main.ores).
There is no Rust executable and no Cargo dependency.

`bin/oreslang-stack` is a narrow POSIX host/bootstrap bridge for
[`flags-2-env`](https://github.com/flags-2-env/flags-2-env),
launching the installed Oreslang Java/Graal compiler/runtime,
and packaging the checked application sources. It does not discover routes
or generate source adapters.

## Commands

```bash
oreslang-stack init --root /path/to/new-api-repo --role api
oreslang-stack init --root /path/to/new-web-repo --role web
oreslang-stack init --root /path/to/new-infra-repo --role infra
oreslang-stack init --root /path/to/new-lambdas-repo --role lambdas
oreslang-stack dev --root examples/hello-api
oreslang-stack routes --root examples/hello-api
oreslang-stack generate --kind all --root examples/hello-api
oreslang-stack generate --kind all --check --root examples/hello-api
oreslang-stack check --root examples/hello-api
oreslang-stack build --root examples/hello-api
oreslang-stack deploy --root examples/hello-api --target oreslang-stack
```

| Command | Behavior |
|---|---|
| `init` | Oreslang-native fresh API/web sources and candidate-only infra/Lambda scaffolds; refuses existing `src/`, `generated/`, or project manifests |\n| `dev` | Oreslang discovers and generates adapters, then launches the app with the Java/Graal runtime; launch-once, not a live-reload watcher |
| `routes` | Native Oreslang recursive discovery produces deterministic JSON route inventory |
| `generate` | Native Oreslang writes `rpc.ores`, `lambda.ores` and a route manifest; `--check` verifies byte equality without writes |
| `check` | Native generation drift check followed by real Oreslang compiler `--check` on each `.ores` source |
| `build` | Generation, compiler checks, a source distribution containing a runnable `bin/oreslang-stack-run` (requires installed Oreslang); **not a compiled native/JVM/WASM executable** |
| `deploy` | Explicit **hard failure** until a backend-specific certified deploy adapter exists |

## Multi-repository bootstrap

Use the exact same CLI for fresh repositories of roles `api`, `admin-api`, `web` and `admin-web`. For example, once the required GitHub repositories are cloned and the Java/Graal Oreslang runtime and `flags2env` are installed:

```bash
# In an existing empty project checkout (a README/.git is fine):
oreslang-stack init --root . --role api
oreslang-stack routes --root .
oreslang-stack generate --kind all --check --root .
oreslang-stack check --root .
oreslang-stack build --root .
```

`init` is intentionally non-destructive: a preexisting `oreslang-stack.toml`, `src/` or `generated/` is a hard refusal, **not** an invitation to migrate existing code. It creates a minimal route/page, entrypoint, role manifest and generated adapters via native Oreslang and compiler-checks the result. It does not provision GitHub repositories, authenticate to an organization, build a native binary, certify deploy, or imply that the generated route is a running HTTP server.

All filesystem writes are scoped to the selected repository. Project initialization is not a single atomic transaction across multiple files; if the actual compiler/generator fails after creating output, inspect it before retrying rather than overwriting any authored work.

## Infra and Lambda repositories

`infra` and `lambdas` have a separate fail-closed candidate profile. `init` creates source-only examples and explicit `deployable = false` manifests. `check` typechecks their sources but **does not** run cloud deployments or create AWS Lambda bootstraps; `routes`, `generate`, `dev`, `build`, and `deploy` are denied for these two roles. See [the infra/Lambda admission guide](docs/INFRA_LAMBDAS.md) for actual provider and runtime requirements.

## Source layout

The project declares the role in `oreslang-stack.toml` as
`api`, `admin-api`, `web` or `admin-web`. API repositories author
`src/routes/**/route.ores` with sibling `handlers.ores` and
`// @ores-route GET /users/{id} show` annotations. Web repositories author
`src/pages/**/page.ores` with `// @ores-page /users/{id} render`.
Generated API routes have `rpc.ores` and `lambda.ores`, while web pages
receive only `lambda.ores`.

The original Rust proof-of-concept forwarded String requests/responses. This
native Oreslang port maintains that **source adapter envelope** for parity;
typed GraphQL, protobuf and host transport bindings are separate dependencies,
not represented as implemented.

Generated code is owned by a marker and never overwrites authored code.
The native generator checks duplicate route method/exports, identical dynamic
route shapes (`[id]` vs `[name]`), orphan adapters, symlinks, role mismatches,
missing handler functions and stale output. Generation performs a read-only
validation phase before materializing files; the filesystem APIs are **not
race-free openat handles**, so hostile mutable project trees are not supported.

## Dependencies

- A Java/Graal Oreslang executable available as `oreslang` (or
  `ORESLANG_BIN=/path/to/executable`).
- `flags2env` from canonical `flags-2-env/flags-2-env`.
- Directory metadata and string helpers originating in [Java/Graal PR #496](https://github.com/ores-truffle-oreslang/oreslang-source.java/pull/496), plus the canonical cooperative native `_blocking` I/O runtime in [Java/Graal PR #522](https://github.com/ores-truffle-oreslang/oreslang-source.java/pull/522). The suffix means **source-level synchronous results with automatic continuation suspension**, never OS scheduler carrier blocking. Until those dependencies are released and pinned, a stock compiler may not run this CLI.

Use `FLAGS2ENV_BIN` to locate a custom flags parser executable.
The schema is [`.cli-flags.toml`](.cli-flags.toml), not a home-grown argv parser.

```sh
bash tests/bootstrap-contract.sh
# Only after installing a real Oreslang runtime with PR #522:
bash tests/native-generator-contract.sh
```

Tests using a mock Oreslang command only prove host bootstrap behavior,
**not native language compilation**. Full native generator tests require the
real interpreter and its filesystem permission APIs. See
[`docs/GENERATION.md`](docs/GENERATION.md) and
[`docs/NATIVE-CLI.md`](docs/NATIVE-CLI.md).

## Not yet certified

A working `deploy` requires a genuine compiled artifact, target/runtime ABI,
isolation/admission policies and a live deployment receipt. Oreslang LLVM is
still experimental and is not usable as the CLI runtime. Real Java/Graal CLI init, check, routes and denial integration passed with an exact migrated source snapshot in [run #38005034460](https://github.com/athlet-o/athleto-e2e/actions/runs/38005034460). This PR remains draft until the compiler runtime dependency is released/pinned and the CLI's own distribution workflows are verified.
