# Oreslang Lambda execution admission contract (v1)

Status: **proposal / fail closed**. Source-generated `lambda.ores` wrappers are not deployable functions.

## First executable milestone

Compile an actual generated `lambda.ores` and its complete imported source closure with a pinned Java/Graal Oreslang compiler. Start a local, loopback-only child process under the existing provider-neutral `ores-lambda` ingress, invoke an explicit exported function with a bounded UTF-8 request, and verify its exact response. The child must execute Oreslang bytecode/guest code; a Rust/Java mock is not sufficient.

## Mandatory proof sequence

1. Resolve and record immutable Oreslang source, compiler source, toolchain, contract, and adapter revisions, plus SHA-256 of the executable and application artifact.
2. Reject unsupported role, missing `lambda.ores`, ambiguous function export, missing imports, unsupported backend, stale generation, and missing real compiler. No simulated success receipt.
3. Compile the full import closure and run a positive invocation against the real guest. Test invalid input, missing export, malformed framing, oversized request/response, timeout, cancellation, child crash, and concurrent invocations.
4. Run the child with explicit environment allowlist, bounded concurrency and queue, process-group cleanup, no shell interpolation, and loopback binding only. Reject user-controlled executable paths unless explicitly authorized.
5. Propagate request ID, deadline, cancellation, and error status across ingress → adapter → Oreslang runtime. Do not treat actor concurrency as parallel execution inside a single actor.
6. Emit a machine-readable receipt that distinguishes source-validated, compiled, invoked, ingress-tested, benchmarked, and deploy-certified. Each stage must bind exact revisions and evidence; failures and skips cannot promote a stage.
7. Compare HTTP status, response bytes, and error semantics against independent TypeSpec and JSON Schema authorities. Add a cold-start/warm-run benchmark only after functional conformance passes.

## Deliberate non-goals

No AWS/GCP deployment, LLVM parity claim, native AOT claim, GraphQL or protobuf support, tenant isolation certification, or production FaaS promotion from source generation alone. `deploy` must continue to fail closed.

## Acceptance

A real installed Java/Graal Oreslang runtime must execute the generated handler end-to-end through the local ingress. CI must preserve compiler and app tree identities and upload a reproducible positive/negative test receipt. Until then the stack remains registered, not materialized.
