# Oreslang Stack CLI

The framework and deployment CLI for **Oreslang-authored** applications. This repository is deliberately distinct from the Rust-based `ores-stack/ores-stack-cli`; `oreslang-stack` is not an alias or a Rust code-generation mode.

> **Bootstrap status:** The repository was initialized with its contract before any CLI executable exists. No command listed below is implemented or certified yet.

## Product boundary

- **Oreslang** is the source language, actor/supervisor model, and compiler/runtime family (currently separate Java/Graal and LLVM paths).
- **Oreslang Stack** is the application framework and its CLI: routes, API and RPC contracts, schema/code generation, build, local development, and deployable artifacts.
- **Implementation language:** The stack's application/framework logic and, where the current compiler permits, the CLI itself must be authored in Oreslang (`.ores`), not Rust. A narrowly scoped host/bootstrap launcher is acceptable only when necessary to start the language runtime; it must not substitute Rust route/code-generation logic.
- **Oreslang FaaS** is a *potential deployment host*, separate from the framework. Do not claim a hosted backend exists until the deployment adaptor and runtime evidence are available.
- **ORES Stack** is the separate Rust framework and CLI. Shared *protocols* are possible; source/language/runtime identity is not shared.

## Proposed command contract (not implemented)

| Command | Intended contract |
| --- | --- |
| `oreslang-stack init` | Create an Oreslang project without Rust application source |
| `oreslang-stack check` | Parse, type-check and validate contracts without deployment |
| `oreslang-stack routes` | Deterministic HTTP/GraphQL/RPC route inventory |
| `oreslang-stack generate` | Deterministic contract-driven GraphQL/RPC/Lambda interface generation |
| `oreslang-stack build --backend graal|llvm` | Produce a backend-specific artifact with provenance |
| `oreslang-stack dev` | Local application development and actor lifecycle |
| `oreslang-stack plan --target <runtime>` | Validate portability and deployment compatibility without side effects |
| `oreslang-stack deploy --target <runtime>` | Explicit deployment; blocked until a certified adapter exists |

Generated GraphQL, RPC and Lambda code must be verified against the actual domain TypeSpec/JSON Schema/Protobuf contracts. A green generator snapshot is not enough. An LLVM-native success must **not** imply JVM/Graal works (or the reverse).

## Comparison fixture integration

`ORESoftware/ores-comparisons` is the consumer of the `ores-dummy-org-oreslang-stack` fixture family, which is intended to be committed as individually pinned Git submodules across each comparison stack. The comparison must preserve exact repository names, branch and immutable commit IDs. Missing private repo access remains a pending state, never a dummy checkout or a pass.

See the parent comparison's `docs/ORESLANG-STACK.md` for the stack/host/compatibility model.

## Acceptance gate for the first executable version

1. Real `.ores` parser/type-checker integration with separately tested Graal and LLVM compilers.
2. Byte-stable route and interface generation, including GraphQL, RPC and Lambda capability gates.
3. Explicit deployment target capabilities, deterministic plan output and no implicit deployment.
4. Actor/process isolation, supervisor restart, hot-load compatibility semantics and truthful errors for unsupported operations.
5. Real fixture build, launch and smoke tests with pinned revisions and recorded evidence.

## Implemented source-level CLI (first slice, under review)

The executable host-side adapter is written in Rust, like the existing \`ores-stack-cli\`, but **application source and framework extension points remain native Oreslang**. The Rust binary does not pretend to parse the full Oreslang language or replace the Oreslang HTTP router/RPC implementations. File discovery uses explicit Oreslang source conventions; semantic validity requires the **real Oreslang compiler**, invoked by \`check\`.

\`\`\`bash
cargo test --all-targets
cargo run -- init --root /tmp/example-api --role api
cargo run -- generate all --root /tmp/example-api
cargo run -- generate all --root /tmp/example-api --check
cargo run -- routes --root /tmp/example-api
cargo run -- check --root /tmp/example-api --compiler oreslang
cargo run -- plan --root /tmp/example-api --target wasm-xprs
\`\`\`

API repositories declare \`[repository] role = "api" | "admin-api"\` in \`oreslang-stack.toml\` and author \`src/routes/**/route.ores\` with a sibling \`handlers.ores\`. Each public wrapper carries a declared HTTP method/path/handler binding:

\`\`\`ores
// @ores-route GET /users/{id} get_user
import module handlers from "./handlers";

pub fnc get_user(String request) -> String {
  return handlers.get_user(request);
}
\`\`\`

The CLI emits sibling **generated** \`rpc.ores\` and \`lambda.ores\` adapters. Their current ABI is an intentionally minimal String request/response envelope; full typed GraphQL/RPC/Protobuf generation and deployment transports require additional compiler-backed contract work. A generated RPC wrapper forwards to the authored route which forwards to the authored handler. Generated Lambda source forwards through RPC; the FaaS adapter is **not yet implemented**.

Web repositories declare \`role = "web" | "admin-web"\`, author \`src/pages/**/page.ores\` and get a sibling generated \`lambda.ores\`. Pages do not create RPC operations. The \`// @ores-page /users/{id} render\` declaration is checked against its filesystem path. Admin and public roles cannot be inferred from directory names.

The CLI refuses symlinked source paths, missing handlers, conflicting dynamic route shapes, incorrect role/path declarations, stale generated outputs in \`--check\` mode, and overwriting unmarked source. It does not count a plan or a source-level generator snapshot as compiler or runtime proof.

### Deployment target restrictions

Only six stacks are *eligible for future deployment adapters*:

| Target | Current admission |
| --- | --- |
| \`oreslang-stack\` | planned; Oreslang-native runtime adapter |
| \`scintilla-run\` | planned; polyglot runtime adapter |
| \`wasm-xprs\` | future Oreslang → WASM backend |
| \`iso-lattes\` | future Oreslang → JS/WASM backend |
| \`lunatic-lorry\` | future Oreslang → WASM backend |
| `litegraph` | planned LLVM-compatible LiteGraph host/GPU adapter; ABI and device execution unproven |

\`beamscale\` is permanently unsupported because Oreslang will not target BEAM/Erlang; \`pony-expres\` is unsupported because Oreslang does not compile to Pony. The Rust \`ores-stack\`, \`graal-show\` and \`litegraph\` are also not admitted deployment targets. \`plan\` gives a **\`deployable: false\`** receipt even for the six eligible lanes. \`deploy\` always fails until there is a real adapter and runtime proof.

See also the [Oreslang-native routing contract](https://github.com/ores-truffle-oreslang/oreslang-http-routing), [Oreslang RPC contract](https://github.com/ores-truffle-oreslang/oreslang-rpc) and [Oreslang SSR library](https://github.com/ores-truffle-oreslang/oreslang-ssr).
