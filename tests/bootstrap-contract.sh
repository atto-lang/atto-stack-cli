#!/usr/bin/env bash
set -euo pipefail
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/project/src"
printf '[repository]\nrole = "api"\n' > "$tmp/project/oreslang-stack.toml"
printf 'pub routine main(): void { return; }\n' > "$tmp/project/src/main.ores"
cat > "$tmp/fake-oreslang" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--check" ]]; then
  [[ -f "${2:-}" ]] || exit 1
  exit 0
fi
if [[ "${1:-}" == --allow-env=* ]]; then
  case "${ORESLANG_STACK_COMMAND:-}" in
    dev|build) printf 'ORESLANG_STACK_ACTION_v1:%s\n' "$ORESLANG_STACK_COMMAND" ;;
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
tar -tzf "$tmp/project/dist/oreslang-stack-source.tar.gz" | grep -F 'src/main.ores'
if "$repo/bin/oreslang-stack" deploy --root "$tmp/project" --target oreslang-stack; then
  echo "deploy must not succeed" >&2
  exit 1
fi
if "$repo/bin/oreslang-stack" dev --root "$tmp/project" --bad-flag; then
  echo "unknown flags must fail" >&2
  exit 1
fi
if "$repo/bin/oreslang-stack" build --backend llvm --root "$tmp/project"; then
  echo "llvm must not be accepted as build-capable" >&2
  exit 1
fi
echo 'host bootstrap contract checks passed (mock interpreter; not native language compilation)'
