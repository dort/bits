#!/usr/bin/env bash
# Concatenate an input file, an engine, and optional extra layers, then
# run with mork.
# Usage:
#   ./run.sh                              # example.mm2 on diff_engine.mm2
#   ./run.sh test.mm2                     # unsimplified test suite
#   ./run.sh example.mm2 simplify.mm2     # post-process simplification
#   ./run.sh test_simplify.mm2 simplify.mm2
#   ENGINE=diff_engine_fused.mm2 ./run.sh example.mm2       # fused engine
#   ENGINE=diff_engine_fused.mm2 ./run.sh test_simplify.mm2
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mork="$script_dir/../../../MORK/target/release/mork"
engine="$script_dir/${ENGINE:-diff_engine.mm2}"
input="${1:-$script_dir/example.mm2}"
shift || true
layers=()
for layer in "$@"; do
  [[ -f "$layer" ]] && layers+=("$layer") || layers+=("$script_dir/$layer")
done
eval_file="$(mktemp --suffix=.mm2)"
trap 'rm -f "$eval_file"' EXIT
cat "$input" "$engine" "${layers[@]:+${layers[@]}}" > "$eval_file"
"$mork" run "$eval_file"
