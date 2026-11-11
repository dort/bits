# Review of Claude's parser benchmark implementation

Reviewed 2026-11-11 against `26b1231` by Codex, after integrating the splitter
commit `425a41e`. The workload registry, fresh-process measurements, bounded
per-case aggregation, and ordinary timeout cleanup are useful additions.
The normal runs reproduce the reported trends. Four corrections remain before
the [benchmark assignment](claude_parser_benchmark_handoff.md) is complete.

## Verification

- **71 Earley tests and 107 lexer tests passed**, including the splitter's
  source-to-both-parser-engines integration test.
- The full quick benchmark completed: **26 cases plus the agreement row**,
  with expected recognition results and no remaining scratch directories.
  Rows are in ignored `earley/output/benchmarks/codex-review-20261111/`.
- Fixed three-token units took approximately 0.125, 0.493, and 2.011 seconds
  for 4, 16, and 64 units. The measured worker peak was 23,608 KiB at all three
  sizes. This reproduces the small-input linear-time/flat-memory observation;
  it does not establish a general performance bound.
- Targeted reproductions are retained locally in ignored
  `lexer/output/claude-benchmark-review/{probe.py,report.json}`. They use actual
  runner results, controlled malformed semantic outcomes, an isolated child
  process, and a stand-in engine. The review probe explicitly terminated its
  surviving child after observing the interruption defect.
- No parser or benchmark implementation files were changed during this review.

## Required corrections

### 1. P1 — terminate the worker group when the supervisor is interrupted

Locations: [parser.py](../../earley/benchmarks/parser.py), `run_worker()` lines
216–228 and `measure_case()` lines 256–260.

`run_worker()` kills the worker's process group on `TimeoutExpired` only.
`KeyboardInterrupt` propagates without stopping or reaping that group. Because
the worker starts a new session, a terminal interrupt delivered to the supervisor
does not reach it automatically. `measure_case()` then removes scratch files
while the worker and any MORK child can still be using them.

**Reproduction:** start a worker that writes its PID and sleeps, through the
actual `run_worker()` helper in a separate supervisor. Send SIGINT to the
supervisor and let its caller clean the temporary directory. The supervisor
exits 130, the directory is gone, and the worker is still alive. The timeout
cleanup tests do not exercise this interruption path.

**Required correction:** ensure exceptional exits after process creation stop
the worker group and reap the worker before removing scratch. Preserve the
original interruption or failure. Make cleanup reliable if the worker exits
between detection and signalling. Apply the same ownership rule to descendants;
terminating only the immediate worker is insufficient when MORK is running.

**Acceptance checks:** interrupt a supervisor with a live worker and live
grandchild, verify neither remains running, and verify scratch is removed only
after termination. Retain the existing ordinary timeout and successful-run
cleanup regressions. Report a clean interrupted CLI exit.

### 2. P2 — make semantic mismatches fail validation

Locations: [parser.py](../../earley/benchmarks/parser.py), `engines_agreement()`
lines 286–294 and `supervise()` lines 321–355.

The harness treats successful worker execution as successful validation even
when the result contradicts a known expectation. An unexpected recognition
result only adds a console note. Engine disagreement also receives
`status="ok"`, and does not affect the final exit status. A performance run can
therefore exit successfully after measuring an incorrect implementation.

**Reproductions:** feed the supervisor a normally shaped result for a case whose
expected recognition is `accepted`, but whose actual result is `rejected`.
The row is marked `ok` and the command returns 0. Feed its engine comparison one
accepted result and one rejected result: the agreement row contains both
`status="ok"` and `verdicts_agree=false`, and the command still returns 0.
These probes replace worker results to isolate the validation logic; the real
engines agreed in the quick run.

**Required correction:** separate measurement execution, semantic validation,
and resource-limited outcomes. Known semantic mismatches and engine disagreement
must produce a machine-readable failure and a nonzero result. Validate expected
unit counts and relevant completeness flags. Do not let a missing/failed engine
silently shrink the comparison into a successful one-engine check. Deliberate
limit cases should validate their expected partial outcome without imposing
brittle exact-time assertions.

The report also infers duplicate-free enumeration from the count of 429 trees.
A count alone cannot exclude one missing tree offset by one duplicate. Check
distinct tree structures and a small exact oracle before making that claim.
The existing small forest tests remain valuable; the benchmark cases need their
own meaningful validation of the results being measured.

**Acceptance checks:** wrong expected verdict, disagreeing engines, missing
comparison participants, incorrect completeness, and duplicate tree outputs
produce explicit validation failures. A correctly reported configured limit
remains distinct from a parser correctness failure.

### 3. P2 — count attempted engine processes and timed-out staging output

Locations: [parser.py](../../earley/benchmarks/parser.py), line 124;
[runner.py](../../earley/grammarc/runner.py), `_execute()` lines 308–319.

`engine_runs` sums `len(unit.budgets)`. Those budgets describe runs that reached
the runner's completion checks; they do not count every MORK process started.
The `peak_dump_bytes` update is also after the timeout handler's early return,
so a partially written dump from a timed-out process is omitted. These fields
undercount exactly the failure cases the harness is intended to characterize.

**Reproduction:** use a stand-in engine that writes a 4,096-byte dump and then
sleeps under a 200 ms unit timeout. Independently count the actual `_execute()`
invocation and record the write before sleeping. One process ran and wrote
4,096 bytes; the benchmark reports `engine_runs=0` and
`peak_engine_dump=0`. Its wall-time classification is otherwise correct.

**Required correction:** instrument process attempts separately from completed
budgets. Collect final observed staging sizes in cleanup before deletion, for
success, failure, and timeout paths. Include captured stdout/stderr when
reporting staging disk use, and distinguish individual-file maxima from the
simultaneous total footprint. Preserve the existing meaning of `UnitResult.budgets`.

**Acceptance checks:** the timed-out writer reports one attempt and its actual
partial dump size; a token-limit rejection still reports zero attempts; ordinary
successful budgets remain correctly counted. Record nonzero diagnostic-file
sizes when they contribute to staging use.

### 4. P2 — measure result serialization and publication as well as inference

Location: [parser.py](../../earley/benchmarks/parser.py), `run_case()` lines
113–169; [REPORT.md](../../earley/benchmarks/REPORT.md), engine comparisons and
disk/memory conclusions.

The worker reads `Runner` results, counts their trees, and discards the returned
graphs and trees. It never writes the actual parser result files. Its byte
metrics describe the input token bundle and MORK staging files, and its parse
timing stops before the CLI's graph/tree serialization and publication work.
Consequently the current forest measurements cover building the returned Python
objects, not producing the promised packed-forest and tree output on disk.

**Reproduction:** run the concat-8 forest case with enumeration. It counts 429
trees, but the only files remaining in its scratch directory are the four input
bundle files. There is no `results.jsonl`, `forests.jsonl`, or parser summary,
and no result-output byte metric. This matches the implementation, but leaves
the assignment's output, staging-disk, and publication measurements unfinished.

**Required correction:** exercise the production result-writing path, time it
separately from inference, and measure the published files and staging footprint.
Share the production serializer/publication mechanism with the benchmark rather
than creating a second implementation. Stream results per unit and include
serialization in the measured worker's resident-memory peak. Measure cleanup
time and failure cleanup as requested in the handoff. Keep the existing library
inference measurements as explicitly scoped numbers.

**Acceptance checks:** forest and enumeration cases publish reconstructable
result bundles with the expected per-unit identities and counts; output bytes
are measured from those actual files; serialization/publication time is
identified; failure and interruption clean staging; increasing unit count does
not accumulate serialized rows or graphs in the benchmark driver.

## Report corrections and disposition

The report's assertion that worker peak RSS is approximately 23.7 MiB in every
case is broader than its own raw data: the original
`engines-concat-n0008-trees` row records **26,684 KiB**, and this review measured
26,744 KiB for that case. Keep the valid flat-memory observation for the fixed
recognition-unit-count series, and report the enumeration case separately.

The observed sweep costs are useful evidence for future experiments. Keep
proposed starting-budget heuristics as hypotheses until tested across the
grammar families; the current measurements do not establish a universal formula.
No new grammar features or batching are needed to address this review.

The combined splitter/parser functionality passes its current checks. Parser
benchmark acceptance remains open for the corrections above. Codex's source-side
scale measurements can proceed independently while Claude makes them.
