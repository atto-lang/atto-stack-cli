# Oreslang Stack CLI

The framework and deployment CLI for **Oreslang-authored** applications. This repository is deliberately distinct from the Rust-based `ores-stack/ores-stack-cli`; `oreslang-stack` is not an alias or a Rust code-generation mode.

> **Bootstrap status:** The repository was initialized with its contract before any CLI executable exists. No command listed below is implemented or certified yet.

## Product boundary

- **Oreslang** is the source language, actor/supervisor model, and compiler/runtime family (currently separate Java/Graal and LLVM paths).
- **Oreslang Stack** is the application framework and its CLI: routes, API and RPC contracts, schema/code generation, build, local development, and deployable artifacts.
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
