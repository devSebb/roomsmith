#!/usr/bin/env bash
# The checks .github/workflows/validate.yml runs, on this machine.
#   scripts/ci-local.sh            everything
#   HERMES_BIN=/path/to/hermes scripts/ci-local.sh    use another Hermes build
# Hermes's own checks run on a clean copy of the tree with a throwaway
# HERMES_HOME, so no Hermes install or data on this machine is touched.
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/bin/python}"
HERMES="${HERMES_BIN:-hermes}"
fail=0
step() { # name, command...
  local name="$1"; shift
  local log; log="$(mktemp)"
  if "$@" >"$log" 2>&1; then echo "PASS  $name  $(tail -1 "$log" | cut -c1-90)"; else echo "FAIL  $name"; tail -25 "$log"; fail=1; fi
  rm -f "$log"
}
bundles_match() { [ -z "$(git status --porcelain desktop/plugin.js dashboard/dist/index.js)" ] || [ "${ALLOW_DIRTY_BUNDLES:-0}" = 1 ]; }

step "engine, tools, backend tests" "$PY" -m pytest -q
step "editor typecheck"             npm --prefix web run --silent check
step "editor tests"                 npm --prefix web test --silent
before="$(shasum desktop/plugin.js dashboard/dist/index.js)"
step "editor build + Desktop lint"  npm --prefix web run --silent build
[ "$before" = "$(shasum desktop/plugin.js dashboard/dist/index.js)" ] \
  && echo "PASS  committed bundles match a fresh build" \
  || { echo "NOTE  bundles changed by the build: commit them with the source"; bundles_match || true; }

if command -v "$HERMES" >/dev/null 2>&1; then
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  mkdir -p "$tmp/roomsmith" "$tmp/home"
  git ls-files -c -o --exclude-standard | while read -r f; do
    [ -f "$f" ] && mkdir -p "$tmp/roomsmith/$(dirname "$f")" && cp "$f" "$tmp/roomsmith/$f"
  done
  echo "      clean copy: $(find "$tmp/roomsmith" -type f | wc -l | tr -d ' ') files, $(du -sk "$tmp/roomsmith" | cut -f1) KB, largest $(find "$tmp/roomsmith" -type f -exec du -k {} + | sort -n | tail -1 | cut -f1) KB (limits 400 / 10240 / 1024)"
  echo "      $("$HERMES" --version 2>/dev/null | head -1)"
  export HERMES_HOME="$tmp/home" ROOMSMITH_DATA_DIR="$tmp/home/data"
  step "hermes plugins doctor --ci"  "$HERMES" plugins doctor "$tmp/roomsmith" --ci
  step "hermes plugins validate"     "$HERMES" plugins validate "$tmp/roomsmith"
else
  echo "SKIP  hermes not found (set HERMES_BIN)"; fail=1
fi
[ "$fail" = 0 ] && echo "ALL PASS" || echo "FAILED"
exit "$fail"
