# Rust / Oreslang CLI feature parity

This is an audited implementation status, not a claim of completed parity.

| Capability | ores-stack CLI (Rust) | oreslang-stack CLI | Evidence / gap |
|---|---|---|---|
| Persistent HTTP grandaddy | Opt-in generation-tree supervisor | Same supervisor | HTTP+PID CI proof |
| Middleware daddy replacement | Scoped middleware digest, health-gated swap | Same | PID remains stable for grandaddy and children |
| Route child replacement | route.rs folder | route.ores folder; explicit REST get.ores etc | Child-only PID change, unchanged siblings |
| Failed source rollback | Compiler failure preserves old route | Same | Real rustc / GraalVM source tests |
| Worker crash restart | Bounded per-worker restart | Same | SIGKILL daddy and child tests |
| Source-code compile on worker admission | rustc worker fixture | Java/Graal Oreslang source worker fixture | Test-only host; not in-VM actor hot swap |
| Production hot reload | Existing Rust watcher and process generation | Process generation opt-in | Production Rust/Oreslang HTTP actor runtime integration unimplemented |
| Native compiled application build | Cargo executable, Rust target builds | Source-bundle only; REST demo has native-image runtime separately | No general Oreslang CLI native build |
| Typed GraphQL / Protobuf / TypeSpec | Existing Rust generators | Transport-neutral String RPC/Lambda wrappers | Typed parity unimplemented |
| Deployment | Receipt-gated adapter in Rust CLI | Explicit deploy refusal | Oreslang deployment unimplemented |
| Runtime authorization | Depends on target and configured runtime | Java/Graal permissions | Neither generation-tree fixture is hostile-tenant sandbox |

## Actual REST demo integration

The REST demo (https://github.com/ores-truffle-oreslang/oreslang-demo-restful-server)
has files such as src/routes/rest/health/get.ores and its own central
route registry generated at startup. This generation-tree contract now accepts
an explicit source_file: "get.ores" within a configured route directory.
This **does not** turn its Oreslang Handler actor module into a standalone
HTTP server or hot swap it inside its original server process. A real
middleware-worker and route actor ABI, with route generation fencing,
is still needed.

The routing library (https://github.com/ores-truffle-oreslang/oreslang-http-routing)
uses trie dispatch with richer path matching, not the static exact URL
dispatch of this development supervisor.

## Required next implementation work

1. Define and implement an authenticated actor-worker HTTP protocol for both
   runtimes (request, response, cancellation, health, drain, generation).
   Integrate the actual Spin/HTTP demo Handler actor and real Rust framework
   route.rs, not merely the local test worker's stdout-derived response.
2. Build true per-generation fencing with guaranteed monotonic incarnation,
   draining, graceful handoff and supervisor restart intensity semantics.
   Currently in-flight requests may receive 502 during 600 ms grace; no
   zero-downtime guarantee is established.
3. Add an Oreslang-native typed contract IR (OpenAPI/GraphQL/Protobuf and RPC
   request/response types) and compare deterministic code generation to
   Rust's operation-index contract. Do not advertise current String wrappers
   as typed transports.
4. Generalize the REST demo's GraalVM native-image pipeline into an Oreslang
   stack build with pinned toolchain, receipts, binary digest, reproducibility
   tests, and platform-specific JNI carrier library. A native-image of an
   interpreter embedding guest sources is not AOT lowering of Oreslang
   application handlers.
5. Add a fail-closed Oreslang deploy adapter using the proven Rust release/
   deployment receipts, environment admission, health-gated promotion,
   rollback, and target identity verification. Keep deploy rejected until it
   performs a real integration against an isolated target.

## CI limitations

The Rust CLI standalone adapter and generation-tree tests pass on the
available GitHub Actions runners. The *entire* Rust workspace cargo check
is blocked by the private pinned ORESoftware/ores-compose git dependency in
the current runner (no credential provided). Do not confuse this with a
passing workspace build or introduce secrets to bypass it.

The Oreslang-org Actions runs may fail before any steps are scheduled;
the private ores-stack/ores-stack-cli mirror tests actual identical Oreslang
runtime and CLI source without cross-organization credentials. Only specific
snapshots with passing runs establish test evidence.

## Safety

This process-generation supervisor is POSIX developer tooling listening on
loopback; local custom commands are trusted. It does not defend against
hostile tenant code, filesystem races or local adversaries; the source
tree may be mutated concurrently. Do not expose it publicly or use it as
a deployment authority.
