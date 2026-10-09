#!/usr/bin/env bash
# Fast source-only regression gate. This does not establish runtime behavior:
# GraalVM compiler and actor carrier tests live in oreslang-source.java PR #522.
set -euo pipefail
repo="$(cd -- "$(dirname -- "$0")/.." && pwd -P)"
source="$repo/src/main.ores"
test -s "$source"

# A legacy bare name is forbidden in the native CLI's canonical source. The
# opening-parenthesis boundary avoids matching *_blocking and *_async calls.
if grep -En '(fs|File)\.(read_text|write_text|write_text_atomic|append_text|list_dir|is_dir|is_symlink|exists|remove|mkdir_all)\(' "$source" ||
   grep -En 'stdio\.(print|println)\(' "$source" ||
   grep -En 'stdio\.stdout\.(write|println|log|logList)\(' "$source" ||
   grep -En 'stdio\.stdin\.read_line\(' "$source" ||
   grep -En '(network|net)\.connect\(' "$source" ||
   grep -En 'http\.(get_text|post_text)\(' "$source"; then
  echo "legacy bare native I/O call in migrated Oreslang CLI" >&2
  exit 1
fi

grep -Fq 'fs.write_text_atomic_blocking(' "$source"
grep -Fq 'fs.list_dir_blocking(' "$source"
grep -Fq 'fs.is_symlink_blocking(' "$source"
grep -Fq 'stdio.println_blocking(' "$source"

echo "Native CLI source-only I/O suffix admission: pass (runtime proof separate)"
