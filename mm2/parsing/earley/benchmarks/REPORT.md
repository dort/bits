# Parser scale measurements

Claude's results and progress for the
[parser benchmark assignment](../../docs/dev_plans/claude_parser_benchmark_handoff.md),
revised for the
[benchmark review](../../docs/dev_plans/review_parser_benchmarks_26b1231.md).
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

That is the quick run: 26 cases plus the engine-agreement row, under one
minute in total, modest output. Every case runs in a fresh worker process, and
every row is validated against the case's known outcomes — expected
recognition, the named limit, enumeration completion, exact distinct-tree
counts, published row counts — with engine comparison requiring every expected
participant to report, complete, and agree. A contradiction is a
machine-readable `validation-failed` row and a nonzero exit, so the exit
status certifies both that the measurements ran and that the measured parser
behaved as specified; a correctly reported configured limit validates cleanly.
Larger workloads are explicit, for example `--units 256 1024` or
`--chain-tokens 31`; `--only <text>` selects cases by ID substring, `--list`
prints the selected IDs, and `--supervisor-timeout` caps any one case.
Interrupting the supervisor stops the live worker's process group — MORK
children included — before its scratch directory is removed, and the command
exits 130. The supervisor streams one JSON row per case to `rows.jsonl` next
to a `meta.json` holding machine, interpreter, binary, and registry identity.
Case IDs are pure functions of the registry parameters.

## Provenance of the numbers below

Measured 2026-11-11 on Linux 7.0.0-42-generic x86_64 (`singbuntu24`), CPython
3.14.10, MORK release binary SHA-256
`6ef8dc1bee052ac1f88944ce83c21174bb3d6622bad77875634b5d0cefe75a0e`, grammar
fingerprint `8711aca…9281851d` (the pinned worked-example grammar) for the
`expr` cases, lexer specification fingerprint `abcfb5fe…a8ddcbc3`
(`expression_demo.json`). Rows: `output/benchmarks/quick-2026-11-11b/` and
`output/benchmarks/units256-2026-11-11b/` on that machine; both runs exited 0
with every row validated.

## 1. Unit count: linear time, flat memory

Fixed `x + 12` units (3 tokens, the pinned 13-item chart), fixed grammar and
limits, recognition engine. `parse` covers every unit's engine reruns and the
Python processing after them, with result serialization timed separately;
every case also publishes its `results.jsonl`/`summary.json` through the
production writer.

| Units | parse (s) | per unit (ms) | serialize (s) | published bytes | worker peak RSS (KiB) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 0.124 | 31.0 | 0.0004 | 2,126 | 23,564 |
| 16 | 0.495 | 30.9 | 0.0013 | 6,168 | 23,696 |
| 64 | 2.003 | 31.3 | 0.0059 | 22,363 | 23,424 |
| 256 | 8.060 | 31.5 | 0.0233 | 87,469 | 23,932 |

Parse time is linear in the unit count and the Python worker's peak resident
set stays between 23.4 and 23.9 MiB from 4 to 256 units with serialization
included — no trend with unit count. Serialization time and published bytes
grow linearly (about 0.09 ms and 340 bytes per unit) because the result files
hold one row per unit; the rows are streamed, never held. Engine staging is
constant per run: the largest simultaneous input+dump+streams footprint is
5.6 KB at every unit count, because exactly one unit's facts are staged at a
time. This is the observed trend on these inputs, not a proved bound; larger
opt-in runs can extend the evidence.

## 2. Tokens per unit: parser work tracks tokens and sweeps, not characters

One unit per bundle. `runs` is the number of MORK processes whose sweep
schedule completed (the doubling budget ladder); attempts equal runs in every
completed case here. `staging` is the largest simultaneous engine
input+dump+streams footprint.

| Case | tokens | chars | items | runs | budget | parse (s) | staging (KB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| expr (left recursion) | 7 | 13 | 25 | 2 | 32 | 0.032 | 7.1 |
| expr | 15 | 29 | 49 | 3 | 64 | 0.125 | 11.8 |
| expr | 31 | 68 | 97 | 4 | 128 | 0.230 | 21.2 |
| long (same grammar, 24-char operands) | 7 | 105 | 25 | 2 | 32 | 0.032 | 7.6 |
| long | 15 | 213 | 49 | 3 | 64 | 0.118 | 12.6 |
| long | 31 | 429 | 97 | 4 | 128 | 0.237 | 22.9 |
| right recursion | 7 | 13 | 51 | 2 | 32 | 0.057 | 7.8 |
| right recursion | 15 | 35 | 167 | 3 | 64 | 0.208 | 16.0 |
| right recursion | 31 | 83 | 591 | 4 | 128 | 1.088 | 40.0 |
| chain-31 + list | 1 | 1 | 66 | 4 | 128 | 0.269 | 14.2 |
| chain-31 + list | 7 | 13 | 291 | 5 | 256 | 2.395 | 29.7 |
| chain-31 + list | 15 | 35 | 647 | 5 | 256 | 5.056 | 45.3 |
| ambiguous concat | 3 | 5 | 20 | 2 | 32 | 0.032 | 5.5 |
| ambiguous concat | 8 | 15 | 90 | 2 | 32 | 0.107 | 9.5 |

The long-token cases run at the same speed as the token-dense cases with 6.3×
the characters: character count affects only the bundle, lexing, and staging
sides (all small here), while parser cost follows token count and the sweep
budget the grammar shape demands. Right recursion at 31 tokens costs 4.6× the
left-recursive expression on the same budget because its item set is 6×
larger (591 against 97): every suffix completion spans a distinct range. The
unit-production chain is the most expensive shape per token — depth 31 alone
forces budgets past 128 sweeps, and each sweep is a whole-space join over the
growing item set.

## 3. Engines: identical verdicts, bounded forest overhead

Ambiguous concatenation over 8 tokens, one unit, all limits equal. Every
engine's output goes through the production writer, so the forest rows carry
the packed graph and the enumeration rows carry the trees.

| Engine | parse (s) | parts | dump bytes | serialize (s) | published bytes | trees |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| recognition | 0.106 | — | 6,567 | 0.0001 | 1,140 | — |
| forest | 0.109 | 128 | 14,328 | 0.0003 | 7,250 | — |
| forest + enumeration (max 512 trees, depth 40) | 0.131 | 128 | 14,328 | 0.0234 | 525,047 | 429 |

Recognition verdicts agree across the engines (the run's validated
`engines-agreement` row; a missing, failed, or incomplete participant would
fail the run instead of shrinking the comparison). The forest engine's extra
`node`/`part` facts cost about 4% runtime and 2.2× the dump size. Enumeration
produced 429 trees for 8 leaves, all structurally distinct (429 distinct
canonical serializations) and exactly the Catalan count the registry derives
for the case; the three-token case's two trees are additionally checked
structurally against a hand-written oracle in the harness tests, read back
from the published `results.jsonl`. Serializing those 429 trees is where the
cost moves: 23 ms and 525 KB published against 16 ms of enumeration and a
14 KB dump — result output, not inference, dominates heavily enumerated
units' disk use.

## 4. Limits: exhaustion is reported, never miscounted

`attempts` counts every MORK process started; `runs` only those whose sweep
schedule completed.

| Case | configuration | recognition | named limit | attempts | runs |
| --- | --- | --- | --- | ---: | ---: |
| limits-sweeps | chain grammar, `max_sweeps=4` | incomplete | sweeps | 1 | 1 |
| limits-walltime | 31-token expression, `timeout_seconds=0.05` | incomplete | wall-time | 3 | 2 |
| limits-tokens | 31-token unit, `max_tokens=8` | incomplete | tokens | 0 | 0 |
| limits-trees | concat-8, forest, `max_trees=2` | accepted; enumeration incomplete (2 trees) | tree count | 2 | 2 |
| limits-depth | concat-8, forest, `max_depth=2` | accepted; enumeration incomplete (0 trees) | depth | 2 | 2 |

No limit case is counted as a rejection (`rejected` is 0 throughout) and no
cut enumeration claims completeness; the supervisor validates each of these
expected partial outcomes, including the exact reason label and tree counts.
The wall-time case shows the attempt/run distinction: its third engine
process was started and killed by the deadline, so it is one attempt and no
completed run, and a timed-out process's partially written dump is still
collected into the staging byte metrics at cleanup. The token-limit case
never starts a MORK process: the reader's index check rejects the unit first.

## Memory: what was measured and how

- **Python worker**: `RUSAGE_SELF` peak resident set. For the recognition
  unit-count series it stays between 23.4 and 23.9 MiB across 4–256 units,
  dominated by interpreter plus imports. The enumeration case is the
  exception and is reported separately: 31.9 MiB peak, because building and
  serializing 429 trees through the production writer is included in the
  measured worker, as it should be.
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
is roughly 4–15% of a small-unit run and noise for the heavy ones. Result
publication is cheaper still: the no-replace rename costs ~0.3–0.6 ms per
case regardless of size. At these scales the measured bottleneck is the sweep
schedule, not process creation or publication.

## Observed bottlenecks and evidence-based proposals

1. **The confirmation rerun dominates completed cases.** Closure requires two
   consecutive budgets with equal projections, and the ladder doubles, so the
   final confirming run alone costs as much as all prior runs together (for
   example chain-15 ran budgets 16…256 where 128 already held the fixed
   point). A starting-budget heuristic seeded from token count plus grammar
   unit-chain depth is a hypothesis these measurements suggest — in every
   measured case the reached budget was the first power of two covering
   roughly tokens plus chain depth — but it is untested across grammar
   families and is not claimed as a universal formula. It would change only
   the starting rung, not the convergence contract.
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
  timed separately from parsing. Added two staging-size counters to
  `grammarc.Runner`. Fixed the `sys.path` order in `tests/support.py` so this
  project's root precedes the lexer (both trees now have top-level
  `benchmarks` and `tests` packages). Earley suite 60 → 71.
- **2026-11-11, second iteration** — All four corrections from
  `review_parser_benchmarks_26b1231.md`. (1) Every exceptional exit after
  worker creation — interrupt included — stops the worker's process group and
  reaps it before scratch removal; the CLI reports a clean interrupted exit
  (130); a live-interruption regression kills a real worker with a live
  grandchild. (2) Execution, validation, and resource-limited outcomes are
  separated: rows are validated against known outcomes (verdicts, unit and
  published-row counts, completeness flags, reason labels, exact
  distinct-tree counts derived from the Catalan number), engine disagreement,
  missing or incomplete participants fail the run, and the duplicate-free
  claim now rests on distinct-structure counting plus an exact two-tree
  oracle read from published results. (3) `Runner` counts engine attempts
  separately from completed budgets and collects final staging sizes — dump,
  stdout, stderr, and the simultaneous total — on success, failure, and
  timeout paths; a timed-out stand-in writer reports its one attempt and its
  4,096-byte partial dump. (4) The production result path is measured: the
  CLI's inline writing moved to the shared `grammarc.results.ResultWriter`
  (CLI migrated, no second implementation), every benchmark case serializes
  and publishes real `results.jsonl`/`forests.jsonl`/`summary.json` with
  serialization and publication timed separately from inference, published
  bytes measured from the actual files, and per-case cleanup timed for
  normal, failed, and timed-out workers. Report claims corrected: the flat
  ~23.4–23.9 MiB worker RSS applies to the recognition unit-count series,
  the enumeration case peaks at 31.9 MiB with serialization included, and
  the starting-budget idea is stated as an untested hypothesis. Earley suite
  71 → 85; lexer suite passing (107).
