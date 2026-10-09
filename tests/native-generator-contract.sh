#!/usr/bin/env bash
# Requires Java/Graal Oreslang with stdlib PR #496, NOT a mocked runner.
set -euo pipefail
repo="$(cd -- "$(dirname -- "$0")/.." && pwd -P)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cp -R "$repo/examples/hello-api" "$tmp/api"
cp -R "$repo/examples/hello-web" "$tmp/web"
cli="$repo/bin/oreslang-stack"
cp -R "$repo/examples/hello-api" "$tmp/manifest-collision"
mkdir -p "$tmp/manifest-collision/generated"
printf '{"schema":"foreign"}\n' > "$tmp/manifest-collision/generated/route-manifest.json"
if "$cli" generate --kind all --root "$tmp/manifest-collision"; then
  echo "foreign route manifest must fail before writing any adapters" >&2
  exit 1
fi
test ! -e "$tmp/manifest-collision/src/routes/rpc.ores"
test ! -e "$tmp/manifest-collision/src/routes/lambda.ores"
"$cli" generate --kind all --root "$tmp/api"
"$cli" generate --kind all --check --root "$tmp/api"
"$cli" check --root "$tmp/api"
"$cli" routes --root "$tmp/api" | grep -F '"kind":"route"'
grep -F 'route.greet(request)' "$tmp/api/src/routes/rpc.ores"
grep -F 'rpc.rpc_greet(request)' "$tmp/api/src/routes/lambda.ores"
grep -F 'oreslang.stack.inventory/v1' "$tmp/api/generated/route-manifest.json"
"$cli" build --root "$tmp/api"
test -s "$tmp/api/dist/oreslang-stack-source.tar.gz"
tar -tzf "$tmp/api/dist/oreslang-stack-source.tar.gz" | grep -F "bin/oreslang-stack-run"
tar -tzf "$tmp/api/dist/oreslang-stack-source.tar.gz" | grep -F "generated/route-manifest.json"
printf '\n// deliberately stale\n' >> "$tmp/api/src/routes/rpc.ores"
if "$cli" generate --kind all --check --root "$tmp/api"; then
  echo "stale generated file must fail verification" >&2
  exit 1
fi
"$cli" generate --kind all --root "$tmp/api"
printf 'hand authored\n' > "$tmp/api/src/routes/rpc.ores"
if "$cli" generate --kind all --root "$tmp/api"; then
  echo "hand-authored file must not be overwritten" >&2
  exit 1
fi
"$cli" generate --kind all --root "$tmp/web"
"$cli" generate --kind all --check --root "$tmp/web"
test -f "$tmp/web/src/pages/lambda.ores"
test ! -e "$tmp/web/src/pages/rpc.ores"
if "$cli" generate --kind rpc --root "$tmp/web"; then
  echo "web repositories do not generate RPC" >&2
  exit 1
fi
mkdir -p "$tmp/api/src/routes/users/[id]" "$tmp/api/src/routes/users/[name]"
for param in id name; do
  dir="$tmp/api/src/routes/users/[$param]"
  printf 'pub fnc show(String request) -> String { return request; }\n' > "$dir/handlers.ores"
  printf '// @ores-route GET /users/{%s} show\nimport module handlers from "./handlers";\npub fnc show(String request) -> String { return handlers.show(request); }\n' "$param" > "$dir/route.ores"
done
if "$cli" generate --kind all --root "$tmp/api"; then
  echo "ambiguous dynamic path shapes must fail" >&2
  exit 1
fi
if "$cli" deploy --root "$tmp/web" --target oreslang-stack; then
  echo "uncertified deploy must fail" >&2
  exit 1
fi
if "$cli" build --root "$tmp/web" --backend llvm; then
  echo "unsupported LLVM must fail" >&2
  exit 1
fi
echo "native Oreslang generator integration checks passed"
