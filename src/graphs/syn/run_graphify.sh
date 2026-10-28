#!/usr/bin/env bash
set -euo pipefail
SRC="${1:?source tree}"; OUT="${2:?output dir}"
FILES="${3:-src/tokenize.c parse.c src/vdbe.c src/vdbeapi.c src/vdbemem.c src/prepare.c}"
SCAN="$OUT/scan"
rm -rf "$OUT"; mkdir -p "$SCAN"
for f in $FILES; do cp "$SRC/$f" "$SCAN/"; done
printf 'language.h=c\n' > "$SCAN/.graphifyrc"
export GRAPHIFY_BACKEND=none GRAPHIFY_QUERY_LOG_DISABLE=1
graphify extract "$SCAN" --code-only --no-cluster --out "$OUT/out"
{ echo "sqlite_commit=$(git -C "$SRC" rev-parse HEAD)"; echo "files=$FILES"; echo "graphify_version=$(graphify --version 2>&1 | head -1)"; } > "$OUT/graph_meta.txt"
cat "$OUT/graph_meta.txt"
find "$OUT/out" -name graph.json
