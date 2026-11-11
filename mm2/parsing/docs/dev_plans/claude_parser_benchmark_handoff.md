# Parallel implementation handoff: parser measurements for Claude

Written 2026-11-11 against `da559cf`. The user requested simultaneous work on
non-overlapping components. This file assigns Claude the parser measurements;
Codex is implementing the generic streaming splitter. It does not launch Claude.

## Ownership and coordination

| Owner | Exclusive write scope for this iteration |
| --- | --- |
| Codex | `lexer/`, splitter specifications/examples/tests, source-to-bundle integration, and pipeline documentation in `docs/dev_plans/`. |
| Claude | `earley/benchmarks/`, benchmark tests under `earley/tests/`, and `earley/README.md`. Small parser instrumentation or defect fixes under `earley/grammarc/` are permitted when required by the measurements; preserve its public interfaces and output contracts. |

Use the existing version-2 bundle APIs as the boundary. Claude must not edit
`lexer/` or change its record schemas, reader APIs, or shared helpers. Report a
shared-code defect with a reproducer in `earley/benchmarks/REPORT.md` for Codex to
handle. Codex will use the parser through its current CLI without editing
`earley/`. Put Claude's progress and results in that report, not this handoff,
so neither agent needs to edit the other's files.

Inspect the shared checkout before edits. Preserve other work and stage only
owned paths if the user later requests a commit. Do not commit merely because
this handoff exists. The Git root is `/home/ni/repos/m/bits`; all project work
belongs under `mm2/parsing/`.

## Read first

- [Integrated pipeline plan](stream_splitter_and_earley_pipeline.md), especially
  parser completion, limits, and milestone 6.
- [Version-2 bundle APIs](bundle_v2_implementation.md).
- [Parser README](../../earley/README.md) and the current runner/forest code.
- [Latest review](review_runner_corrections_5087e3e.md) and its fixes in `da559cf`.
- `/home/ni/AGENTS.md` and applicable local instructions.

Baseline checked by Codex on 2026-11-11: 60 Earley tests and 83 lexer tests pass
on Python 3.14.10 with the real MORK binary.

## Task: reproducible parser scale measurements

Build a runnable harness under `earley/benchmarks/`. It must operate today,
without waiting for the splitter. Generate synthetic units using the existing
`SourcePiece` / `source_records` / `write_bundle` APIs. Feed those completed
bundles to the real parser. Generate units lazily and keep fixed-size metadata;
the benchmark driver must not accumulate all inputs or result rows in memory.

Cover these independent dimensions:

1. Increase unit count while holding each unit, grammar, and limits fixed.
   Measure whether parser working memory grows with the source's unit count.
2. Increase tokens per unit for ordinary expressions, right recursion, unit
   chains, and ambiguous concatenation. Include token-dense text and a long-token
   case so character count and parser work are distinguished.
3. Compare recognition, packed-forest output, and explicitly bounded tree
   enumeration. Verify recognition agrees across engines on completed cases.
4. Exercise sweep, wall-time, token, and tree count/depth limits. Report
   accepted/rejected/incomplete separately and never count a limit result as a
   grammatical rejection or a successful complete benchmark.

Provide a small default or `--quick` run with finite runtime and modest output,
plus explicitly requested larger runs. Respect `MORK`, parser limits, and a
supervisor timeout. Preserve the runtime's qualified address-space ceiling:
MORK reserves large arenas, so virtual address space is not resident memory.

Record machine/interpreter/binary identity, grammar and lexical fingerprints,
input sizes, configured limits, unit counts, verdicts/completion flags, elapsed
time, peak resident memory, and output/staging disk sizes. Run comparable cases
in fresh processes. Separate Python-parent and MORK-child memory measurements
where available; do not present `tracemalloc` as whole-process or Rust memory.
Document unsupported measurements instead of inventing them.

Measure subprocess startup and parsing separately where the mechanism permits
it. If an empty/control run only estimates overhead, label it an estimate; do
not claim it directly measures full-join inference time. Observe cleanup on
normal completion and interrupted/failed cases. Store generated artifacts under
ignored `earley/output/`, with a reproducible compact report in
`earley/benchmarks/REPORT.md`.

## Acceptance criteria

- One documented command runs a quick end-to-end benchmark with actual MORK.
- Results have a machine-readable format, deterministic case identities, and
  enough provenance to repeat them. Stream per-case rows instead of building
  an unbounded report object.
- Semantic assertions use known outcomes and tiny exact forest/tree fixtures
  where appropriate. Timing noise must not make correctness tests fail.
- Several unit counts demonstrate the observed memory trend; distinguish
  observations from a proved bound. Larger workloads remain opt-in.
- Small tests cover harness accounting, failure/timeout classification, and
  cleanup. Run existing Earley tests and the lexer suite after any shared-API
  integration or parser instrumentation change.
- README/report explain practical constraints and identify measured bottlenecks.
  Propose optimizations from evidence; do not add batching, parallel workers,
  nullable grammar support, or persistent MORK spaces in this assignment.

## Commands and stable integration boundary

Use `/home/ni/repos/m/bits/mm2/parsing/lexer/.venv/bin/python` and
`/home/ni/repos/m/MORK/target/release/mork`. From `parsing/`, set
`PYTHONPATH="$PWD/lexer:$PWD/earley"`. Run the two test directories separately
because both have a `tests` package.

`SourcePiece(text)` represents one unit. Pass a lazy iterable of these into
`source_records(..., namespace=..., source_id=..., max_units=...,
max_unit_chars=...)`, then into `write_bundle`. Generated IDs are the default;
use a short source ID. `BundleReader.iter_entries()` streams the index and
`read_stream(entry, ...)` reads one bounded unit. The parser consumes that same
bundle through `grammarc parse`; it does not require a split specification.

Codex will implement split specifications, incremental matching, and
`tokenizer --split-spec` using these unchanged interfaces. After both assignments
are ready, Codex will run splitter-produced bundles through the parser and add
the source-side scale measurements.

## Why this division

Dividing the splitter between two authors would put both in its matcher,
provenance, and CLI contracts. Parser measurements instead use an already tested
bundle boundary and can progress immediately. Giving Claude nullable grammar
support would also avoid file overlap, but expands semantics before the current
pipeline has end-to-end scale evidence. Measurements are the next planned task.
