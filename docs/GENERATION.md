# Native Oreslang route, RPC and Lambda generator

[`src/main.ores`](../src/main.ores) implements recursive source discovery,
method/page annotations, deterministic inventory JSON, generated RPC/Lambda
wrapper code and drift checks **in Oreslang**, not Rust.

## Source authority

API roles `api` and `admin-api` use `src/routes/**/route.ores` with sibling
`handlers.ores`. A valid declaration:

```ores
// @ores-route GET /users/{id} show
import module handlers from "./handlers";
pub fnc show(String request) -> String {
  return handlers.show(request);
}
```

The handler must be a public String request -> String response function.
Each distinct method in the same route must have a distinct exported symbol.

Web roles `web` and `admin-web` use `src/pages/**/page.ores`:

```ores
// @ores-page /users/{id} render
pub fnc render(String request) -> String {
  return "<main>Oreslang</main>";
}
```

## Outputs

- API: generated sibling `rpc.ores` (route forwarding) and
  `lambda.ores` (RPC forwarding).
- Web: generated sibling `lambda.ores` (page forwarding).
- All roles: `generated/route-manifest.json` (stable JSON inventory).

`oreslang-stack generate --kind all` writes, while
`oreslang-stack generate --kind all --check` refuses missing/stale outputs
without writing. A Lambda-only operation requires a current RPC adapter.
Unowned authored files are not overwritten; symlinks are refused; orphan
generated adapters are rejected in check mode and removed by full regeneration.

Route traversal uses cooperative stdlib `fs.list_dir_blocking` (sorted) and checks leaf declarations
against the derived static/dynamic path. Route shapes `/users/[id]` and
`/users/[name]` conflict irrespective of parameter name. Nesting is capped
at 32 path segments.

## Boundaries

- The source generators use a transport-neutral String envelope, matching
  the original Rust proof of concept. This is **not** a typed GraphQL,
  protobuf schema, or working Lambda runtime adapter.
- Source pattern checks do not replace the native Oreslang compiler or
  application contract validation.
- Filesystem preflight and writes are not atomic as one multi-file transaction
  and are not race-free against malicious concurrent mutations.
- LLVM backend cannot execute this CLI yet. Java/Graal runtime [PR #522](https://github.com/ores-truffle-oreslang/oreslang-source.java/pull/522) supplies the async-backed `_blocking` I/O calls required by the migrated generator. Strict typechecking and actual CLI initialization/read-only/drift/refusal tests passed on the exact downstream source in [GraalVM CI run #38005034460](https://github.com/athlet-o/athleto-e2e/actions/runs/38005034460). The versioned compiler release remains a prerequisite for deploying the CLI.
