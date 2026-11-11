# Parser scale measurements

Claude's results and progress for the
[parser benchmark assignment](../../docs/dev_plans/claude_parser_benchmark_handoff.md).
Raw rows live under the ignored `output/benchmarks/`; this file is the compact
reproducible record. Shared-code defects found during the measurements would be
reported here with reproducers for Codex; none were found.

## Reproducing

From `earley/`, with the real MORK binary (a `MORK` environment variable
overrides the path everywhere):

```bash
PYTHONPATH=../lexer /home/ni/repos/m/bits/mm2/parsing/lexer/.venv/bin/python \
  -m benchmarks.parser
```

That is the quick run: 26 cases, under one minute in total, modest output.
Larger workloads are explicit, for example `--units 256 1024` or
`--chain-tokens 31`; `--only <text>` selects cases by ID substring, `--list`
prints the selected IDs, and `--supervisor-timeout` caps any one case. Every
case runs in a fresh worker process so peak resident memory is comparable; the
supervisor streams one JSON row per case to `rows.jsonl` next to a `meta.json`
holding machine, interpreter, binary, and registry identity. Case IDs are pure
functions of the registry parameters.

## Provenance of the numbers below

Measured 2026-11-11 on Linux 7.0.0-42-generic x86_64 (`singbuntu24`), CPython
3.14.10, MORK release binary SHA-256
`6ef8dc1bee052ac1f88944ce83c21174bb3d6622bad77875634b5d0cefe75a0e`, grammar
fingerprint `8711aca…9281851d` (the pinned worked-example grammar) for the
`expr` cases, lexer specification fingerprint `abcfb5fe…a8ddcbc3`
(`expression_demo.json`). Rows: `output/benchmarks/quick-2026-11-11/` and
`output/benchmarks/units256-2026-11-11/` on that machine.

## 1. Unit count: linear time, flat memory

Fixed `x + 12` units (3 tokens, the pinned 13-item chart), fixed grammar and
limits, recognition engine. `parse` covers every unit's engine reruns and
Python processing; `per unit` divides by the unit count.

| Units | parse (s) | per unit (ms) | worker peak RSS (KiB) | bundle bytes |
| ---: | ---: | ---: | ---: | ---: |
| 4 | 0.123 | 30.8 | 23,680 | 14,174 |
| 16 | 0.489 | 30.5 | 23,680 | 51,452 |
| 64 | 1.976 | 30.9 | 23,796 | 202,002 |
| 256 | 7.913 | 30.9 | 23,608 | 811,614 |

Parse time is linear in the unit count and the Python worker's peak resident
set does not move between 4 and 256 units (the spread is below 1%). Engine
staging per run is also constant: peak engine input 2.0 KB, peak dump 3.3 KB
at every unit count, because exactly one unit's facts are resident per run.
This is the observed trend on these inputs, not a proved bound; the
accumulation points that could break it (archive metadata, result rows) are
streamed by construction, and larger opt-in runs can extend the evidence.

## 2. Tokens per unit: parser work tracks tokens and sweeps, not characters

One unit per bundle. `runs` is the number of fresh MORK processes the
doubling budget ladder used; `budget` is the largest sweep budget that ran.

| Case | tokens | chars | items | runs | budget | parse (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| expr (left recursion) | 7 | 13 | 25 | 2 | 32 | 0.031 |
| expr | 15 | 29 | 49 | 3 | 64 | 0.101 |
| expr | 31 | 68 | 97 | 4 | 128 | 0.239 |
| long (same grammar, 24-char operands) | 7 | 105 | 25 | 2 | 32 | 0.031 |
| long | 15 | 213 | 49 | 3 | 64 | 0.101 |
| long | 31 | 429 | 97 | 4 | 128 | 0.220 |
| right recursion | 7 | 13 | 51 | 2 | 32 | 0.055 |
| right recursion | 15 | 35 | 167 | 3 | 64 | 0.209 |
| right recursion | 31 | 83 | 591 | 4 | 128 | 1.089 |
| chain-31 + list | 1 | 1 | 66 | 4 | 128 | 0.268 |
| chain-31 + list | 7 | 13 | 291 | 5 | 256 | 2.393 |
| chain-31 + list | 15 | 35 | 647 | 5 | 256 | 5.105 |
| ambiguous concat | 3 | 5 | 20 | 2 | 32 | 0.030 |
| ambiguous concat | 8 | 15 | 90 | 2 | 32 | 0.105 |

The long-token cases run at the same speed as the token-dense cases with 6.3×
the characters: character count affects only the bundle and lexing sides (both
sub-millisecond here), while parser cost follows token count and the sweep
budget the grammar shape demands. Right recursion at 31 tokens costs 4.6× the
left-recursive expression on the same budget because its item set is 6×
larger (591 against 97): every suffix completion spans a distinct range. The
unit-production chain is the most expensive shape per token — depth 31 alone
forces budgets past 128 sweeps, and each sweep is a whole-space join over the
growing item set.

## 3. Engines: identical verdicts, bounded forest overhead

Ambiguous concatenation over 8 tokens, one unit, all limits equal.

| Engine | parse (s) | parts | dump bytes | trees |
| --- | ---: | ---: | ---: | ---: |
| recognition | 0.104 | — | 6,567 | — |
| forest | 0.108 | 128 | 14,328 | — |
| forest + enumeration (max 512 trees, depth 40) | 0.124 | 128 | 14,328 | 429 |

Recognition verdicts agree across the engines on every completed case (the
run's `engines-agreement` row). The forest engine's extra `node`/`part` facts
cost about 4% runtime here and 2.2× the dump size; enumerating all 429 trees
(exactly the Catalan number for 8 leaves, confirming the packed graph is
complete and duplicate-free) adds 16 ms in Python, outside MORK.

## 4. Limits: exhaustion is reported, never miscounted

| Case | configuration | recognition | named limit |
| --- | --- | --- | --- |
| limits-sweeps | chain grammar, `max_sweeps=4` | incomplete | sweeps |
| limits-walltime | 31-token expression, `timeout_seconds=0.05` | incomplete | wall-time |
| limits-tokens | 31-token unit, `max_tokens=8` | incomplete | tokens |
| limits-trees | concat-8, forest, `max_trees=2` | accepted; enumeration incomplete | tree count |
| limits-depth | concat-8, forest, `max_depth=2` | accepted; enumeration incomplete (0 trees) | depth |

No limit case is counted as a rejection (`rejected` is 0 throughout) and no
cut enumeration claims completeness. The token-limit case never starts a MORK
process (0 engine runs): the reader's index check rejects the unit first. The
accounting itself is covered by `tests/test_benchmarks.py` on deterministic
tiny cases, so timing noise cannot fail a correctness assertion.

## Memory: what was measured and how

- **Python worker**: `RUSAGE_SELF` peak resident set, ~23.7 MiB in every
  case, flat across unit counts and dominated by interpreter plus imports.
- **MORK child, direct**: `/usr/bin/time -v` on the exact engine inputs the
  harness generates measures 6,064 KiB peak resident for the `x + 12` run and
  5,980 KiB for the heaviest quick case (chain grammar, 15 tokens, 256
  sweeps, 3.1 s), against 5,376 KiB for a one-fact control space. Resident
  memory is small and essentially flat; the binary's ~10 GiB startup
  reservation is virtual address space, not resident memory, and the runner's
  RLIMIT_AS ceiling accounts for it.
- **MORK child, per row**: the rows' `RUSAGE_CHILDREN` figure (~15 MiB) is an
  upper bound only. On this platform a forked child's `ru_maxrss` starts from
  the parent's resident pages before `exec`, which the control case
  demonstrates exactly (its children report precisely the parent's peak). The
  direct measurements above are authoritative; the row field remains useful
  as a cheap regression ceiling.
- **Not measured**: Rust-side allocation internals; `tracemalloc` is not used
  for any whole-process claim.

## Startup against inference

The control case times `mork run` over a one-fact space: 1.3 ms minimum,
2.2 ms mean over 5 runs. That is an estimate of process startup, arena
reservation, and a trivial run — not a direct measurement of full-join
inference. Against it, the measured engine runs here spend 15–30 ms per
process on small units and seconds on sweep-heavy shapes, so process startup
is roughly 4–15% of a small-unit run and noise for the heavy ones. At these
scales the measured bottleneck is the sweep schedule, not process creation.

## Observed bottlenecks and evidence-based proposals

1. **The confirmation rerun dominates completed cases.** Closure requires two
   consecutive budgets with equal projections, and the ladder doubles, so the
   final confirming run alone costs as much as all prior runs together (for
   example chain-15 ran budgets 16…256 where 128 already held the fixed
   point). An initial-budget heuristic seeded from token count plus grammar
   unit-chain depth would skip the provably insufficient small budgets; the
   data here (budget reached ≈ tokens + chain depth, then one doubling)
   supplies the seed formula. This changes only the starting rung, not the
   convergence contract.
2. **Sweep count, not per-process cost, is the scaling limit.** Chain-shaped
   grammars force budgets linear in depth before any token is consumed.
   Chaining round tables past the 998-sweep cap (already proposed) matters
   before any batching does.
3. **Batching units per process is not yet justified.** With ~2 ms startup
   against ≥15 ms of work per unit, merging units into one MORK process would
   save under 15% on the smallest units while giving up the fresh-space
   isolation the pipeline plan requires. The evidence does not support it at
   current scales; millions of sub-millisecond units would reopen the
   question. Per the assignment, no batching, parallel workers, nullable
   grammars, or persistent spaces were added.

## Progress log

- **2026-11-11** — Harness built (`benchmarks/cases.py`, `benchmarks/parser.py`):
  deterministic case registry over the four assigned dimensions, fresh-process
  workers with per-case supervisor timeout and guaranteed scratch cleanup
  (process-group kill on timeout), per-case rows streamed to `rows.jsonl` with
  fixed-size accumulators, lazy unit generation through
  `SourcePiece`/`source_records`/`write_bundle`, whole-archive validation
  timed separately from parsing. Added two staging-size counters
  (`peak_input_bytes`, `peak_dump_bytes`) to `grammarc.Runner` — attributes
  only, no interface or output-contract change. Fixed the `sys.path` order in
  `tests/support.py` so this project's root precedes the lexer (both trees
  now have top-level `benchmarks` and `tests` packages). Eleven new harness
  tests (accounting, failure/timeout classification, cleanup, registry
  determinism); earley suite 60 → 71, lexer suite unchanged and passing.
  Quick run plus a 256-unit opt-in run recorded above.
