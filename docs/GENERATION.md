# Oreslang-native route / RPC / Lambda generation — design contract

The original Rust PR #2 prototype implemented `init`, `routes`,
`generate`, `check`, and `plan` in Rust. Those code paths have been
**removed** because the Oreslang stack CLI must be authored in Oreslang.
These capabilities are not currently implemented in the native CLI.

## Intended inputs

- `oreslang-stack.toml` with explicit repository role:
  `api`, `admin-api`, `web`, or `admin-web`.
- API: `src/routes/**/route.ores` and sibling `handlers.ores`.
- Web: `src/pages/**/page.ores`.
- Explicit route annotation `// @ores-route GET /users/{id} get_user`.
- Explicit page annotation `// @ores-page /users/{id} render`.

## Intended outputs and admission checks

- Byte-stable generated `rpc.ores` and `lambda.ores` from validated types,
  with generator ownership markers and no overwrite of authored code.
- Real Oreslang compiler typecheck and contract-driven GraphQL/Protobuf
  generation, not string-only transport envelopes as a substitute.
- Deterministic route inventory, duplicate/dynamic-route conflict checks,
  symlink refusal and stale/orphan generated-file detection.
- Deployment target restrictions. No eligible target is currently deployable.
  Explicitly deny BEAM/Beamscale and Pony Expres.
- Java/Graal and LLVM must be checked separately as those backends mature.

This is a future implementation contract, not a feature announcement.
