#!/usr/bin/env bash
# Runs Hermes's own plugin doctor on a clean export of the committed tree
# (what a catalog install sees: no .venv, node_modules or scratch files) and
# reports the file/size counts the catalog's security scan limits.
set -euo pipefail
cd "$(dirname "$0")/.."
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git archive --format=tar HEAD | tar -x -C "$tmp"
files=$(find "$tmp" -type f | wc -l | tr -d ' ')
bytes=$(du -sk "$tmp" | cut -f1)
echo "clean export: $files files, ${bytes} KB (catalog limits: 400 files, 10240 KB, 1024 KB per file)"
big=$(find "$tmp" -type f -size +1000k | sed "s#$tmp/##")
if [ -n "$big" ]; then echo "!! files over 1 MB:"; echo "$big"; fi
ROOMSMITH_DATA_DIR="$tmp/.data" hermes plugins doctor "$tmp" --ci
