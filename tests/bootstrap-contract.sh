#!/usr/bin/env bash
# Host only: this mock NEVER establishes Oreslang compiler correctness.
set -euo pipefail
repo="$(cd -- "$(dirname -- "$0")/.." && pwd -P)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/project/src"
printf '[repository]\nrole = "api"\n' > "$tmp/project/oreslang-stack.toml"
printf 'pub routine main(): void { return; }\n' > "$tmp/project/src/main.ores"
cat > "$tmp/fake-oreslang" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "--check" ]]; then
  [[ -f "$2" ]] || exit 1
  exit 0
fi
if [[ "$1" == --allow-env=* ]]; then
  if [[ "$ORESLANG_STACK_BACKEND" != graal ]]; then
    echo 'ERROR: LLVM not supported'
    exit 0
  fi
  case "$ORESLANG_STACK_COMMAND" in
    dev|build|check)
      mkdir -p "$ORESLANG_STACK_ROOT/generated"
      printf '{"schema": "oreslang.stack.inventory/v1"}\n' > "$ORESLANG_STACK_ROOT/generated/route-manifest.json"
      printf 'ORESLANG_STACK_ACTION_v1:%s\n' "$ORESLANG_STACK_COMMAND" ;;
    routes) printf 'ORESLANG_STACK_JSON_v1:{"schema":"oreslang.stack.inventory/v1"}\n' ;;
    generate) printf 'ORESLANG_STACK_ACTION_v1:generated\n' ;;
    deploy) printf 'ERROR: deployment denied\n' ;;
    *) printf 'ERROR: unrecognized\n' ;;
  esac
  exit 0
fi
printf 'app started\n'
EOS
chmod +x "$tmp/fake-oreslang"
export ORESLANG_BIN="$tmp/fake-oreslang"
test "$("$repo/bin/oreslang-stack" dev --root "$tmp/project")" = "app started"
"$repo/bin/oreslang-stack" build --root "$tmp/project" | grep -F 'NOT a compiled'
test -s "$tmp/project/dist/oreslang-stack-source.tar.gz"
"$repo/bin/oreslang-stack" routes --root "$tmp/project" | grep -F '"schema"'
"$repo/bin/oreslang-stack" generate --kind all --root "$tmp/project" | grep -F 'generated'
"$repo/bin/oreslang-stack" check --root "$tmp/project" | grep -F 'verified'
tar -tzf "$tmp/project/dist/oreslang-stack-source.tar.gz" | grep -F 'src/main.ores'
if "$repo/bin/oreslang-stack" deploy --root "$tmp/project" --target oreslang-stack; then
  echo "deploy must never succeed" >&2
  exit 1
fi
if "$repo/bin/oreslang-stack" dev --root "$tmp/project" --bad-flag; then
  echo "unknown flags must fail" >&2
  exit 1
fi
if "$repo/bin/oreslang-stack" build --backend llvm --root "$tmp/project"; then
  echo "llvm not admitted" >&2
  exit 1
fi
ln -s "$tmp/project" "$tmp/project-link"
if "$repo/bin/oreslang-stack" dev --root "$tmp/project-link"; then
  echo "symlink root must fail" >&2
  exit 1
fi
echo 'host bootstrap contract checks passed (mock interpreter; not native compilation)'
