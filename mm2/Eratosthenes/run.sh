#!/usr/bin/env bash
# Concatenate an input file with the sieve engine and run with mork.
# Usage:
#   ./run.sh              # runs example.mm2 (primes up to 100)
#   ./run.sh test.mm2     # expect (CORRECT 50), no MISTAKE
#   ./run.sh myquery.mm2
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mork="$script_dir/../../../MORK/target/release/mork"
input="${1:-$script_dir/example.mm2}"
eval_file="$(mktemp --suffix=.mm2)"
trap 'rm -f "$eval_file"' EXIT
cat "$input" "$script_dir/sieve.mm2" > "$eval_file"
"$mork" run "$eval_file"
