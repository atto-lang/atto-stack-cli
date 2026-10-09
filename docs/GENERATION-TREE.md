# Generation tree (grandaddy → daddy → child)

Both CLIs share **the same** opt-in POSIX/loopback generation supervisor:
bin/generation-tree.py, implementing ores.dev.generations/v1.

It is **not** conventional "reload browser" or "restart the HTTP server".
Grandaddy is the long-running frontend HTTP listener. Daddy is a
separate middleware HTTP process. Each route folder owns a separate HTTP
worker. Every request flows grandaddy → daddy → child.

## Run

Oreslang:

    ORESLANG_BIN=/path/to/oreslang oreslang-stack dev --generation-tree --root examples/generation-tree-oreslang
    curl -i http://127.0.0.1:18551/alpha

Rust:

    ores-stack dev --generation-tree --root examples/generation-tree-rust
    curl -i http://127.0.0.1:18552/alpha

Python 3, a POSIX host, the configured worker commands and the language
toolchain are required. The supplied examples use the explicitly labeled
test-only source-worker fixture, which compiles/executes small stand-alone
Rust/Oreslang source units at startup. Replace the test fixture with a real
HTTP actor/route worker for deployment-oriented integration.

## Contract

Create dev-tree.json in the project root:

    {
      "schema": "ores.dev.generations/v1",
      "port": 18551,
      "middleware": "src/middleware",
      "routes": [
        {
          "path": "/alpha",
          "dir": "src/routes/alpha",
          "argv": ["python3", "tools/my-http-route-worker.py", "--port", "{port}", "--root", "{root}", "--source-dir", "{source_dir}"]
        }
      ],
      "daddy_argv": ["python3", "tools/my-http-middleware.py", "--port", "{port}"]
    }

The worker commands are executable argv arrays, **not shell strings**.
Host arguments recognize {port}, {root} and {source_dir} placeholders.
Every spawned worker receives ORES_DEV_PORT, ORES_DEV_HEALTH_TOKEN and
ORES_DEV_ROOT. It must listen on 127.0.0.1:ORES_DEV_PORT; return exact
HTTP 200 /__ores_health with body OK when given X-Ores-Dev-Token; and
accept the token on proxied requests. The middleware must forward to
X-Ores-Dev-Target-Port over loopback. Its port/target header is internal;
do not expose these private worker endpoints publicly.

The fixture_echo:true setting is **testing only**. It returns source-file
text without executing any Rust or Oreslang code; it must not be
treated as real code hot loading. Production worker mode refuses startup
without explicit daddy_argv and per-route argv.

## Proof obligations

Our CI tests send real HTTP requests, track X-Ores-Grandaddy-PID,
X-Ores-Daddy-PID, and X-Ores-Child-PID and enforce:

1. Grandaddy PID and TCP listener remain stable throughout the test.
2. Editing one source file in a route folder replaces just its child,
   not daddy or sibling children.
3. Editing a file in middleware replaces daddy only; existing route
   children retain their PIDs.
4. Invalid Rust/Oreslang source refuses replacement and keeps the
   previous healthy child serving; fixing source admits a new child.
5. The child source unit is actually compiled/executed, not echoed;
   response body and middleware header change after valid source edits.
6. Unknown routes return 404 and symlinked sources are rejected.

Polling is content-hashed, with 150 ms poll and 300 ms stabilization.
Each worker must become healthy before its replacement is admitted;
old generations are retired after a short grace period. A 502 may still
occur for an in-flight request: **no zero-downtime SLA is claimed**.
Route snapshots cover direct route-folder files; middleware snapshots
cover its subtree.

## Tested crash recovery and source admission

The supervisor detects a crashed child or daddy and rebuilds only that
worker, leaving grandaddy and sibling route children undisturbed. Reload
intensity is limited to three attempts per 11 seconds per worker;
a new source digest resets the failed-compilation admission budget.
A candidate must return authenticated loopback health within 30 seconds
before it can replace its predecessor. Invalid source code leaves the
last healthy route generation serving. Tests use SIGKILL and compare
actual PIDs and HTTP bodies before/after the swap.

## Audit boundaries and parity gaps

This is a developer-local, explicitly opted-in process supervisor.
It binds the grandaddy to 127.0.0.1 only and requires POSIX process groups.
It is not a secure multi-tenant sandbox, remote hot-code loader, or
network-facing reverse proxy. Workers are trusted local user commands.
Mutable-tree TOCTOU races, request-drain handoffs, token exposure to
local processes, worker health churn, and dynamic configuration migration
remain future hardening work.

Oreslang HTTP examples:
- https://github.com/ores-truffle-oreslang/oreslang-demo-restful-server
- https://github.com/ores-truffle-oreslang/oreslang-http-routing
- https://github.com/ores-truffle-oreslang/oreslang-demos

The existing REST demo uses method sources such as
src/routes/rest/health/get.ores and a startup-generated central
registry. By default, route.ores or route.rs must exist in each worker directory.
 Oreslang may select source_file: "get.ores" (or post/put/patch/delete/
 head/options.ores) to mirror the REST demo's route-file layout, but an
 explicit HTTP worker adapter is still required. The actor source file is
 not itself an HTTP listener.
It does **not** hot-swap actors inside that existing server or rewire
its generated route registry. That needs a separate runtime ABI and
integration test.

For built artifact parity, the Rust stack has Cargo binaries and more
mature TypeSpec/GraphQL/RPC and deployment receipt machinery. The
Oreslang CLI currently creates compiler-checked source distributions
rather than a general standalone guest-code binary. The REST demo has
its *own* working GraalVM native-image build (AOT runtime with embedded
Oreslang sources); that has not yet been generalized into oreslang-stack
build. A managed deployment adapter, typed transport parity, and
in-VM OTP actor hot swapping remain **unfinished**, and unsupported
operations must continue to fail closed.


## Additional security audit — October 2026

The opt-in development server now has regression tests for:

- **HTTP admission and proxy isolation:** rejects transfer-encoded or
  ambiguous-content-length requests and non-origin-form targets. Removes
  request and response hop-by-hop headers, including fields named by
  `Connection`. Never exposes upstream `X-Ores-Dev-*` internal headers.
- **Bounded local HTTP workload:** at most 64 simultaneously admitted
  connections per host, 5-second accepted-socket timeout, 256 KiB incoming
  request body and 1 MiB upstream response body limits.
- **Subprocess least privilege:** workers inherit a fixed toolchain-environment
  allowlist, not arbitrary credentials in the grandaddy environment. This
  is *not* a sandbox; workers retain the launching user's filesystem access.
- **Safe source snapshots:** bounded regular-file reads from no-follow file
  descriptors, symlink/invalid source rejection, per-file 4 MiB size cap,
  and 4,000-file inventory cap. Parent directory races cannot be excluded
  completely without directory-FD-pinned tree snapshots.
- **Generation fencing:** after a replacement is healthy, compare its
  watched-source digest again immediately before admission. A source edit
  during compilation discards that candidate without replacing the healthy
  generation.
- **Lifecycle cleanup:** POSIX process groups are terminated even if their
  group leader has already exited. Workers finishing admission after shutdown
  are immediately stopped instead of being promoted.

Security tests live in `tests/test_proxy_security.py`,
`tests/test_process_tree_security.py`, and
`tests/test_source_snapshot_security.py`; real HTTP and source-execution
tests remain in the generation-tree test suites.

**Important remaining limitations:** a local trusted development tool,
not an authenticated public reverse proxy; no adversarial tenant isolation;
worker health endpoints rely on a process-local bearer value; no guaranteed
graceful request drain or rollback transaction across middleware and routes.
Full Rust workspace Cargo builds currently depend on private Git repositories
and need a credential-free dependency mirror to validate in CI. Native
GraalVM compilation of every Oreslang guest handler and production deployment
are still not implemented by this CLI feature.
