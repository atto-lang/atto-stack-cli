#!/usr/bin/env bash
# Real cross-toolchain contract: requires actual oreslang + oresfmt binaries.
# This is intentionally separate from bootstrap-contract.sh, whose compiler and
# formatter are mocks and therefore cannot establish language/toolchain parity.
set -euo pipefail

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
oreslang_bin="${ORESLANG_BIN:-oreslang}"
oresfmt_bin="${ORESFMT_BIN:-oresfmt}"
stack_bin="${ORESLANG_STACK_BIN:-$repo/bin/oreslang-stack}"
flags2env_bin="${FLAGS2ENV_BIN:-flags2env}"

require_executable() {
  local value="$1" label="$2"
  if [[ "$value" == */* ]]; then
    [[ -x "$value" ]] || { echo "real-toolchain: $label is not executable: $value" >&2; exit 127; }
  else
    command -v "$value" >/dev/null 2>&1 ||
      { echo "real-toolchain: $label is required: $value" >&2; exit 127; }
  fi
}

require_executable "$oreslang_bin" "ORESLANG_BIN"
require_executable "$oresfmt_bin" "ORESFMT_BIN"
require_executable "$stack_bin" "ORESLANG_STACK_BIN"
require_executable "$flags2env_bin" "FLAGS2ENV_BIN"
export FLAGS2ENV_BIN="$flags2env_bin"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# Compact-but-valid layout is a compiler concern, not a formatting error.
compact="$tmp/compact.ores"
cat > "$compact" <<'ORES'
pub routine main(): void {
if true then return; else return; fi
}
ORES
cp "$compact" "$tmp/compact.before"
"$oreslang_bin" check "$compact"
cmp -s "$tmp/compact.before" "$compact" ||
  { echo "real-toolchain: oreslang check mutated source" >&2; exit 1; }

if "$oresfmt_bin" --check "$compact"; then
  echo "real-toolchain: compact fixture unexpectedly reported canonical" >&2
  exit 1
fi

"$oresfmt_bin" --stdout "$compact" > "$tmp/formatted.ores"
"$oreslang_bin" check "$tmp/formatted.ores"
"$oresfmt_bin" --check "$tmp/formatted.ores"
"$oresfmt_bin" --stdout "$tmp/formatted.ores" > "$tmp/formatted-again.ores"
cmp -s "$tmp/formatted.ores" "$tmp/formatted-again.ores" ||
  { echo "real-toolchain: formatter is not byte-idempotent" >&2; exit 1; }

# Formatting may reject malformed input, but if it emits output it must not turn
# compiler-invalid source into compiler-valid source.
malformed="$tmp/malformed.ores"
printf '%s\n' 'pub routine main(): void { let = ; }' > "$malformed"
if "$oreslang_bin" check "$malformed"; then
  echo "real-toolchain: malformed fixture was accepted before formatting" >&2
  exit 1
fi
if "$oresfmt_bin" --stdout "$malformed" > "$tmp/malformed-formatted.ores" 2>"$tmp/malformed-format.err"; then
  if "$oreslang_bin" check "$tmp/malformed-formatted.ores"; then
    echo "real-toolchain: formatter repaired compiler-invalid syntax" >&2
    exit 1
  fi
fi

make_project() {
  local destination="$1"
  cp -R "$repo/examples/hello-api" "$destination"
}

# A compiler rejection must happen before the formatter and before packaging.
make_project "$tmp/bad-project"
printf '%s\n' 'pub routine broken(): void { let = ; }' > "$tmp/bad-project/src/zz-broken.ores"
cp -R "$tmp/bad-project/src" "$tmp/bad-project-src-before"
fmt_log="$tmp/formatter-invocations"
oreslang_log="$tmp/oreslang-invocations"
: > "$fmt_log"
: > "$oreslang_log"
cat > "$tmp/logging-oresfmt" <<'WRAP'
#!/usr/bin/env bash
set -euo pipefail
printf 'invoked\n' >> "$ORESFMT_INVOCATION_LOG"
exec "$REAL_ORESFMT_BIN" "$@"
WRAP
cat > "$tmp/logging-oreslang" <<'WRAP'
#!/usr/bin/env bash
set -euo pipefail
printf 'CALL' >> "$ORESLANG_INVOCATION_LOG"
for arg in "$@"; do
  printf '\t%s' "$arg" >> "$ORESLANG_INVOCATION_LOG"
done
printf '\n' >> "$ORESLANG_INVOCATION_LOG"
exec "$REAL_ORESLANG_BIN" "$@"
WRAP
chmod +x "$tmp/logging-oresfmt" "$tmp/logging-oreslang"
if ORESFMT_BIN="$tmp/logging-oresfmt" \
   REAL_ORESFMT_BIN="$oresfmt_bin" \
   ORESFMT_INVOCATION_LOG="$fmt_log" \
   ORESLANG_BIN="$tmp/logging-oreslang" \
   REAL_ORESLANG_BIN="$oreslang_bin" \
   ORESLANG_INVOCATION_LOG="$oreslang_log" \
   "$stack_bin" build --format-check --root "$tmp/bad-project"; then
  echo "real-toolchain: build accepted compiler-invalid source" >&2
  exit 1
fi
grep -F   { echo "real-toolchain: compiler rejection still produced a bundle" >&2; exit 1; }
diff -ru "$tmp/bad-project-src-before" "$tmp/bad-project/src" >/dev/null ||
  { echo "real-toolchain: rejected build mutated authored source" >&2; exit 1; }

# A style-only failure must pass compiler admission, fail the format gate, leave
# authored source unchanged, and produce no bundle.
make_project "$tmp/style-project"
printf '%s   \n' 'pub routine helper(): void { return; }' > "$tmp/style-project/src/zz-style.ores"
"$oreslang_bin" check "$tmp/style-project/src/zz-style.ores"
cp -R "$tmp/style-project/src" "$tmp/style-project-src-before"
if ORESLANG_BIN="$oreslang_bin" ORESFMT_BIN="$oresfmt_bin" \
   "$stack_bin" build --format-check --root "$tmp/style-project"; then
  echo "real-toolchain: build accepted noncanonical source" >&2
  exit 1
fi
test ! -e "$tmp/style-project/dist/oreslang-stack-source.tar.gz" ||
  { echo "real-toolchain: format rejection still produced a bundle" >&2; exit 1; }
diff -ru "$tmp/style-project-src-before" "$tmp/style-project/src" >/dev/null ||
  { echo "real-toolchain: format-gated build rewrote authored source" >&2; exit 1; }

# Canonicalize the complete source tree explicitly, then require the same real
# compiler + formatter gate to succeed and package the checked sources.
"$oresfmt_bin" --write --ok-to-mod-outside-git "$tmp/style-project/src"
"$oresfmt_bin" --check "$tmp/style-project/src"
while IFS= read -r -d '' source; do
  "$oreslang_bin" check "$source"
done < <(find "$tmp/style-project/src" -type f -name '*.ores' -print0)

ORESLANG_BIN="$oreslang_bin" ORESFMT_BIN="$oresfmt_bin" \
  "$stack_bin" build --format-check --root "$tmp/style-project" >/dev/null
artifact="$tmp/style-project/dist/oreslang-stack-source.tar.gz"
test -s "$artifact" ||
  { echo "real-toolchain: successful checked build produced no bundle" >&2; exit 1; }
tar -tzf "$artifact" | grep -F './src/' >/dev/null

echo "real oreslang check -> oresfmt -> check -> idempotence -> build contract passed"
CALL\tcheck\t' "$oreslang_log" | grep -F '/zz-broken.ores' >/dev/null ||
  { echo "real-toolchain: malformed project source never reached oreslang check" >&2; exit 1; }
test ! -s "$fmt_log" ||
  { echo "real-toolchain: formatter ran after compiler rejection" >&2; exit 1; }
test ! -e "$tmp/bad-project/dist/oreslang-stack-source.tar.gz" ||
  { echo "real-toolchain: compiler rejection still produced a bundle" >&2; exit 1; }
diff -ru "$tmp/bad-project-src-before" "$tmp/bad-project/src" >/dev/null ||
  { echo "real-toolchain: rejected build mutated authored source" >&2; exit 1; }

# A style-only failure must pass compiler admission, fail the format gate, leave
# authored source unchanged, and produce no bundle.
make_project "$tmp/style-project"
printf '%s   \n' 'pub routine helper(): void { return; }' > "$tmp/style-project/src/zz-style.ores"
"$oreslang_bin" check "$tmp/style-project/src/zz-style.ores"
cp -R "$tmp/style-project/src" "$tmp/style-project-src-before"
if ORESLANG_BIN="$oreslang_bin" ORESFMT_BIN="$oresfmt_bin" \
   "$stack_bin" build --format-check --root "$tmp/style-project"; then
  echo "real-toolchain: build accepted noncanonical source" >&2
  exit 1
fi
test ! -e "$tmp/style-project/dist/oreslang-stack-source.tar.gz" ||
  { echo "real-toolchain: format rejection still produced a bundle" >&2; exit 1; }
diff -ru "$tmp/style-project-src-before" "$tmp/style-project/src" >/dev/null ||
  { echo "real-toolchain: format-gated build rewrote authored source" >&2; exit 1; }

# Canonicalize the complete source tree explicitly, then require the same real
# compiler + formatter gate to succeed and package the checked sources.
"$oresfmt_bin" --write --ok-to-mod-outside-git "$tmp/style-project/src"
"$oresfmt_bin" --check "$tmp/style-project/src"
while IFS= read -r -d '' source; do
  "$oreslang_bin" check "$source"
done < <(find "$tmp/style-project/src" -type f -name '*.ores' -print0)

ORESLANG_BIN="$oreslang_bin" ORESFMT_BIN="$oresfmt_bin" \
  "$stack_bin" build --format-check --root "$tmp/style-project" >/dev/null
artifact="$tmp/style-project/dist/oreslang-stack-source.tar.gz"
test -s "$artifact" ||
  { echo "real-toolchain: successful checked build produced no bundle" >&2; exit 1; }
tar -tzf "$artifact" | grep -F './src/' >/dev/null

echo "real oreslang check -> oresfmt -> check -> idempotence -> build contract passed"
