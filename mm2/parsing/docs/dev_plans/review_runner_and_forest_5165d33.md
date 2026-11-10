# Review of Claude's runner and forest completion

Reviewed 2026-11-10 against commit `5165d33` by Codex.

The engines, grammar compiler, and small-example traversal work. The current
completion claim is broader than the implemented runner/output contracts.
Keep milestones 4–5 open for the findings below. This review adds no changes to
Claude's production files; its requested fixes remain in `earley/`, independent
of Codex's upcoming splitter work.

## Evidence and scope

- All **36 Earley tests** pass against the real local MORK binary.
- All **83 lexer tests** pass, including version-2 bundle integration.
- The agreed requirements are in the
  [revised forest plan](earley_span_forest_parser.md) and
  [integrated pipeline plan](stream_splitter_and_earley_pipeline.md).
- Additional probes used actual version-2 bundles and actual MORK forest facts.
  A controlled enumeration delay and a small executable that writes an oversized
  dump isolate the missing resource checks; those probes are not performance
  measurements of MORK itself.
- The local reproduction script and report are in ignored
  `lexer/output/claude-completion-review/{probe.py,report.json}`. Their
  essential inputs and observed outcomes are included below so this review
  remains useful without those generated files.

## Required corrections

### 1. P1 — carry the unit deadline through Python processing and enumeration

Locations: [runner.py](../../earley/grammarc/runner.py), `run_unit()` lines
136–158 and 174–204; `_execute()` lines 235–238;
[forest.py](../../earley/grammarc/forest.py), `enumerate()`.

The runner checks time before each MORK subprocess and passes a timeout to that
process. It then parses the dump, computes the projection, constructs the
forest, and enumerates trees without enforcing the remaining deadline. The
enumerator accepts only count and depth limits. The result can report complete
enumeration with no reason after exceeding the configured per-unit wall time.
If a later engine run times out, `result()` can also start enumerating the
previous run's graph after the deadline has already expired.

**Reproduction:** cache the real forest-engine dump for `x + 12`, return its
semantic facts for two budgets to remove subprocess-startup variability, and
wrap the real enumerator with a controlled 60 ms delay. With a 20 ms unit
timeout, the result took about 61 ms and still returned `accepted`,
`closure_complete=true`, `enumeration_complete=true`, and `reason=null`.

**Required fix:** use one absolute deadline across input processing, dump
processing, projection, graph construction, and traversal. Check it inside
potentially long Python loops and while producing alternatives, not solely
after a whole enumeration returns. Preserve sound acceptance and any previously
established closure, but mark the requested unfinished output incomplete and
name the exhausted deadline. Tree count and depth do not bound traversal time.

**Acceptance checks:** expiration during projection, graph construction, and
enumeration; no new enumeration work after a previously exhausted deadline;
accepted recognition preserved while enumeration is incomplete; command exits 3
when requested enumeration times out.

### 2. P1 — publish the packed forest that forest mode promises

Locations: [runner.py](../../earley/grammarc/runner.py), `UnitResult` and
`run_unit.result()`; [__main__.py](../../earley/grammarc/__main__.py), result
serialization; [forest.py](../../earley/grammarc/forest.py), `graph()`.

`Forest.graph()` exists and its isolated tests preserve alternatives. The runner
never calls it or returns the facts needed to call it. `--engine forest` without
tree enumeration exports only counts and completion flags; the subprocess dump
is deleted. Even when trees are requested, the packed alternative graph is lost.

**Reproduction:** parse `x + 12` with the worked-example grammar and
`--engine forest`. Exit status is 0. The result says `forest_complete=true`,
`node_count=4`, `part_count=7`, and `trees=[]`. The only output files are
`results.jsonl` and `summary.json`; neither contains nodes, parts, a graph, or a
reference to retained graph data. The revised plan makes this lossless shared
graph the primary forest output and concrete trees an optional view.

**Required fix:** expose the graph through the runner and serialize it in the
result bundle when forest mode is requested, including when enumeration is not
requested. Use a fixed file count and release each unit after writing it. Keep
the complete child descriptor in each packed alternative, including alternatives
for prefixes that do not reach the root. Distinguish graph completeness from
tree-enumeration completeness.

**Acceptance checks:** a real CLI forest run yields reconstructable nodes/parts;
the identical-child-production fixture preserves both alternatives through the
published output; a cyclic graph is exportable without tree enumeration; multiple
units remain isolated and do not accumulate in memory.

### 3. P1 — enforce process and output ceilings while MORK runs

Locations: [runner.py](../../earley/grammarc/runner.py), constructor line 71
and `_execute()` lines 208–238; CLI `--max-process-bytes` default.

The memory limit defaults to `None`, leaving default recognition and forest
runs without the finite process-memory ceiling required by the plan.
`max_dump_bytes` is inspected only after the process exits. A process can
therefore write far beyond that limit before the runner reports it. Capturing
stdout/stderr with `capture_output=True` also has no corresponding byte bound.

**Reproduction:** with `max_dump_bytes=1024`, a small stand-in executable using
the MORK argument layout wrote a 2,097,152-byte dump and continued for 50 ms.
Only after its successful exit did the runner return a dump-size limit result.
Inspecting a default `Runner` confirms `max_process_bytes is None`. This is
post-run rejection of an oversized dump, not enforcement of its resource bound.

**Required fix:** choose and qualify a finite default process-memory ceiling;
enforce dump/output limits while the child runs, using an OS limit or bounded
supervision; bound captured diagnostics as well. Keep limits separate from
generic runtime failures, as described in finding 5. Do not interpret the
dump-size guard as an in-memory forest bound.

**Acceptance checks:** a writer attempting an oversized dump is stopped at the
configured bound; a noisy process cannot accumulate unlimited captured output;
default process limits are present; actual limit exhaustion returns an explicit
incomplete result and cleans its temporary files. Keep small real-MORK fixtures
passing under the qualified defaults.

### 4. P2 — stage result files and publish them atomically

Location: [__main__.py](../../earley/grammarc/__main__.py), lines 57–97.

The command creates the final directory before bundle preflight, writes results
directly there, and writes the summary later. Failure leaves a directory that
blocks retrying the same command. Longer failures can leave a prefix of result
rows visible at the final path. The pipeline plan explicitly calls for staged
result publication.

**Reproduction:** run `grammarc parse` with a missing bundle directory and a new
output path. It exits 2 but leaves that final output directory containing an
empty `results.jsonl`. A retry at that path then fails because it exists.

**Required fix:** stage the fixed result files in a sibling temporary directory,
close them, and publish with no-replace directory semantics only after source
validation and result writing succeed. Reuse the existing publication mechanism
through a shared helper; do not make a second implementation of the rename
contract. Deliberately reported incomplete parse results may be published as
incomplete; configuration, input, I/O, and interruption failures must clean staging.

**Acceptance checks:** missing/corrupt bundle, runtime error after one successful
unit, interruption, output write failure, and concurrent destination creation.
Each failure preserves an existing destination and leaves no new final directory.

### 5. P2 — do not classify every nonzero exit as memory exhaustion

Location: [runner.py](../../earley/grammarc/runner.py), lines 229–234.

Setting `max_process_bytes` changes every nonzero process exit into an incomplete
limit result, irrespective of its cause. The same invalid command or runtime
bug becomes a configuration/runtime diagnostic without the cap and a resumable
resource outcome with it. Applying a memory ceiling does not establish that a
failure exhausted it.

**Reproduction:** use `/usr/bin/false` as the explicitly selected executable.
Without a memory cap, the runner raises `RuntimeError` for exit 1. With a 2 GiB
cap, the same program returns `recognition=incomplete` and a reason claiming the
process failed under `max_process_bytes`. No memory exhaustion is involved.

**Required fix:** report ordinary engine failures as diagnostics regardless of
whether limits were installed. Identify a limit outcome only when the runner or
OS supplies evidence of that particular exhaustion. Preserve bounded stderr and
the exit status for diagnostics.

**Acceptance checks:** an ordinary nonzero exit remains a runtime failure with
and without a memory cap; verified timeout/dump/memory exhaustion stays an
incomplete resource outcome with the relevant limit identified.

### 6. P2 — finite user depth must not end in Python recursion failure

Location: [forest.py](../../earley/grammarc/forest.py), the mutually recursive
`symbol_trees`, `child_sequences`, and `child_trees` generators.

The accepted depth limit is any positive integer, but traversal consumes Python
call-stack depth. A supported unit cycle can raise `RecursionError` before
reaching that limit or yielding the requested small number of trees. Traversal
order exposes this: recursive child-production names sort before the base case.

**Reproduction:** compile `expr -> expr | INT` with the recursive production
named `aaaa`, the terminal production named `zzzz`, and the recursive production
listed first. Obtain its real forest-engine facts on one `INT`, then call
`Forest.enumerate(1, 10000)`. It raises `RecursionError: maximum recursion depth
exceeded` rather than returning a bounded result with an explicit incomplete
status. This uses a finite, valid graph and finite requested bounds.

**Required fix:** use explicit traversal state so supported depth/count/deadline
limits control termination, including long right-hand-side prefix walks.
Merely raising Python's recursion limit changes the failure threshold without
providing that contract. If a smaller supported depth range is intentionally
chosen instead, validate and document it before traversal and account for all
recursive helper frames, not just nonterminal depth.

**Acceptance checks:** direct/indirect cycles with recursion-first production
ordering, high requested depth with a small tree cap, and long right-hand sides.
Preserve the existing two-/four-tree and precedence oracles.

## What is accepted and what can wait

The production-specific child traversal, full packed-alternative identity,
merged start root, real-MORK parity fixtures, bundle-v2 reader integration,
and preflight-before-unit-processing behavior are supported by the passing
tests. There is no reason to replace the two engines or change the grammar
schema to fix the findings above.

The documented single-run cap of 998 sweeps is an explicit representation
constraint. Chained schedules and epsilon productions can remain later work;
neither is needed to resolve these findings. The CLI's `--engine forest` name
is a reasonable documented choice instead of the plan's `--forest` spelling.

After corrections, update the README's stale assertion that enumeration is
unimplemented and include enumeration limits in result metadata. Preserve the
existing `MORK` environment override in the runner/CLI as required by the
pipeline plan; the current override applies only in the engine-test helper.

## Suggested correction sequence for Claude

1. Add the failing regressions above before changing the implementation.
2. Fix the runner's resource supervision and the traversal deadline/stack model.
3. Connect lossless graph output and stage the complete result bundle.
4. Run both existing suites and the new failure-path tests. Report the limits
   actually enforced and the resulting output schema in the handoff.

No commit was made as part of this review.
