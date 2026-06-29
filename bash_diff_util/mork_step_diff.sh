#!/usr/bin/env bash
#
# mork_step_diff.sh
#
# Repeatedly runs:
#     mork run Going_Wide_02.mm2 --steps N
# starting at N = 0 and incrementing N by 1 each iteration.
#
#   * N = 0  : the program output (volatile metadata stripped) is written as the
#              baseline to Going_Wide_02_output.txt.
#   * N >= 1 : only the diff of this step's output against the previous step is
#              appended, under a header naming the --steps value.
#
# Stopping rule: stop once the last $TAIL_LINES (default 10) lines of the
# stripped output are identical to the previous step's last $TAIL_LINES lines.
# A MAX_STEPS backstop bounds the loop because, empirically, Going_Wide_02 does
# not reach a fixed point within at least 90 steps and its trailing lines
# oscillate, so the convergence test may never fire on its own.
#
# "Stripped output" removes the lines that change on essentially every run
# regardless of the computation's state, so they are never recorded as spurious
# diffs:
#     executing <N> steps took <X> ms (unifications ..., writes ..., transitions ...)
#     dumping <M> expressions
#
set -euo pipefail

# --- Resolve paths relative to this script's own directory -----------------
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

# mork and the .mm2 program live together under MM2_Structuring_Code.
# NOTE: the originally-specified command passed a bare "Going_Wide_02.mm2", but
# mork resolves the program path relative to the current directory; from this
# script's directory that bare name does not exist, so the .mm2 file is given
# the same relative prefix as the mork binary.
mork_rel="../../../MM2_Structuring_Code/structuring_code/mm2_programs/mork"
mm2_rel="../../../MM2_Structuring_Code/structuring_code/mm2_programs/Going_Wide_02.mm2"
output_log="$script_dir/Going_Wide_02_output.txt"

# Safety backstop on the step counter. Override with:  MAX_STEPS=5000 ./mork_step_diff.sh
max_steps="${MAX_STEPS:-1000}"

# Number of trailing lines whose stability between consecutive steps defines
# convergence. Override with:  TAIL_LINES=20 ./mork_step_diff.sh
tail_lines="${TAIL_LINES:-10}"

# --- Helpers ---------------------------------------------------------------

# Remove the volatile metadata lines so only meaningful program state is compared.
strip_volatile() {
  grep -vE '^executing [0-9]+ steps took|^dumping [0-9]+ expressions' || true
}

# Run mork at a given step count and print its stripped output on stdout.
# Aborts the whole script if mork itself fails, so diffs are never taken
# against an error message.
run_step() {
  local n="$1" raw
  if ! raw="$("$mork_rel" run "$mm2_rel" --steps "$n" 2>&1)"; then
    printf '%s\n' "$raw" >&2
    echo "ERROR: 'mork run $mm2_rel --steps $n' exited non-zero; aborting." >&2
    exit 1
  fi
  printf '%s\n' "$raw" | strip_volatile
}

# --- Baseline (steps = 0) --------------------------------------------------
prev_file="$(mktemp)"
curr_file="$(mktemp)"
trap 'rm -f "$prev_file" "$curr_file"' EXIT

step=0
run_step "$step" > "$prev_file"
cp "$prev_file" "$output_log"
echo "steps=$step: wrote baseline ($(wc -l < "$prev_file") lines) to $output_log"

# --- Increment until the last $tail_lines lines stop changing, or hit cap ---
while (( step < max_steps )); do
  next=$(( step + 1 ))
  run_step "$next" > "$curr_file"

  prev_tail="$(tail -n "$tail_lines" "$prev_file")"
  curr_tail="$(tail -n "$tail_lines" "$curr_file")"

  if [[ "$curr_tail" == "$prev_tail" ]]; then
    {
      echo ""
      echo "===== converged at --steps $next ====="
      echo "Last $tail_lines lines identical to --steps $step; stopping."
    } >> "$output_log"
    echo "steps=$next: last $tail_lines lines identical to step $step -> converged, stopping."
    exit 0
  fi

  {
    echo ""
    echo "===== diff for --steps $next (vs --steps $step) ====="
    diff -u --label "steps $step" --label "steps $next" "$prev_file" "$curr_file" || true
  } >> "$output_log"
  echo "steps=$next: appended diff vs step $step."

  cp "$curr_file" "$prev_file"
  step="$next"
done

{
  echo ""
  echo "===== reached MAX_STEPS=$max_steps without convergence ====="
  echo "Last $tail_lines lines never matched the previous step within $max_steps steps."
} >> "$output_log"
echo "Reached MAX_STEPS=$max_steps without last-$tail_lines-line convergence; stopping." >&2
exit 0
