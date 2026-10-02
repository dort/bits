#!/usr/bin/env bash
# Concatenate an input file with the FAST sieve engine (sieve2.mm2) and
# run with mork.
# Usage:
#   ./run2.sh              # runs example.mm2
#   ./run2.sh test.mm2     # same test suite as the slow engine
#   ./run2.sh myquery.mm2
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mork="$script_dir/../../../MORK/target/release/mork"
input="${1:-$script_dir/example.mm2}"
eval_file="$(mktemp --suffix=.mm2)"
trap 'rm -f "$eval_file"' EXIT
cat "$input" "$script_dir/sieve2.mm2" > "$eval_file"
"$mork" run "$eval_file"
