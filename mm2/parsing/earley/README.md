# MM2 Earley engines

The two engine artifacts from the
[span-forest Earley plan](../docs/dev_plans/earley_span_forest_parser.md) and
the `grammarc` package: grammar compiler, bundle runner, and the
production-aware forest traversal with bounded tree enumeration. Tests run
everything under the real MORK binary. Assignment history lives in the
[implementation handoff](../docs/dev_plans/claude_implementation_handoff.md).

## The two engines

| File | Rules | Result relations |
| --- | --- | --- |
| `earley.mm2` | `ased bprd cscn dcmp eacc` | `item`, `accepted` |
| `earley_forest.mm2` | `ased bprd cscn dcmp dnod eacc` | `item`, `accepted`, plus the span-keyed forest `node`/`part` |

Load exactly one engine per space. Each file carries its own variants of the
scan, complete, and accept rules, so loading both would run both variants
against the same items. The grammar is data (`grm-*` facts), the tokens are
data (`lex-token`/`lex-end`), and the engines contain no grounded arithmetic
and no grammar-specific rules. The fact schemas and the identity rules for
forest consumers (a packed alternative is the whole `part` fact, child
descriptor included) are specified in the plan.

## Running an engine

```bash
/home/ni/repos/m/MORK/target/release/mork run INPUT.mm2 DUMP.mm2 --aux-path ENGINE.mm2
```

Results are read from the dump file, never from stdout. `INPUT.mm2` supplies:

- the grammar facts and one `(parse NS S G)` demand per stream/grammar pair,
  where `NS`/`S` name a token stream and `G` a grammar;
- the token facts, either ground or from a lexer bundle's `tokens.mm2`;
- a round table `(nextround r001 r002) … (nextround rNNN rNNN+1)` chained from
  `r001` with three-digit zero-padded round symbols, one entry per sweep
  (MM2 compares symbols length-first, so unpadded numbers would misorder);
- one `(budget B)` fact naming the budget.

After the whole round table is consumed, the engine writes `(swept B)`. A
dump without that fact means the scheduled sweeps did not all run — for
example under a `--steps` cap — and must not be interpreted at all. `(swept
B)` certifies that the schedule finished, not that the Earley closure is
complete: non-acceptance is only a rejection once the canonical semantic
projection (the `item`/`accepted` facts of that `(NS, S, G)`, plus
`node`/`part` in forest mode, excluding round tables and instrumentation) is
identical across an increased budget. The tests double the budget;
`tests/fixtures/grammar_chain31.mm2` is the standing counterexample where 12
and 24 rounds both end cleanly, differ in their projections, and carry no
acceptance, while 64 rounds accept.

## The grammar compiler

`grammarc` validates the version-1 grammar JSON (exactly the fields
`version`/`start`/`productions`; lowercase production names and nonterminals,
uppercase terminal kinds, nonempty right-hand sides of single-key `nt`/`t`
objects; unique names, every referenced nonterminal defined) and serializes a
compiled grammar to the `grm-*` facts plus the demand and round-table facts
of the engine contract. It builds on the lexer's shared helpers — strict JSON
loading, the fingerprint recipe, `checked_atom`, `validate_identifier`, the
`ConfigurationError` hierarchy with source/production/field context — so run
it with the sibling `lexer/` directory importable (the test support sets that
up; scripts use `export PYTHONPATH="$PWD/lexer:$PWD/earley"` from
`parsing/`). `CompiledGrammar.check_terminals(declared_kinds)` rejects
grammar terminals absent from a stream's declared kind catalog by name. The
worked-example grammar's fingerprint,
`8711aca694c020c03214bd2105a002121864f95c644556d81121422f9281851d`, is a
pinned fixture, and the generated facts for it are tested equal to the
hand-written `tests/fixtures/grammar_expr_demo.mm2` (plus the `grm-grammar`
version fact) and to recognize the real lexer bundle under MORK.

## The runner

`grammarc parse` recognizes every unit of a completed version-2 token bundle:

```bash
cd mm2/parsing
export PYTHONPATH="$PWD/lexer:$PWD/earley"
lexer/.venv/bin/python -m grammarc parse \
  --grammar earley/tests/fixtures/grammar_expr_demo.json --grammar-id gexp \
  --tokens <bundle directory> --output-dir <results directory>
```

The runner first validates the whole archive by exhausting the reader's
record stream (gaps and dropped empties included), then processes one unit at
a time: it reads the unit's stream under explicit token/character/payload
limits, checks the grammar's terminals against the stream's declared kind
catalog, and runs the engine in a fresh MORK process per sweep budget,
doubling the budget (16, 32, …, capped by `--max-sweeps`, at most 998 — one
run's three-digit round-symbol table bounds a single schedule) until the
canonical projection is identical across consecutive budgets. Per unit it
records `recognition` (`accepted` on a sound acceptance fact; `rejected` only
with established closure; otherwise `incomplete` with the exhausted limit
named), `closure_complete`, `forest_complete` and `enumeration_complete`
(`null` when not requested, `false` when attempted and cut short), the
budgets that ran to their marker, fact counts, and the enumerated `trees`
when requested. A `MORK` environment variable overrides the default engine
binary path for the runner and the command alike.

Resource limits are enforced while the work runs, not inspected afterwards.
One absolute deadline per unit (`--timeout-seconds`, default 30 s) covers
every engine rerun and all Python processing after it — dump parsing,
projection, forest construction, tree copying, tree enumeration; expiry
preserves sound acceptance and any closure established inside the budget but
marks the unfinished output incomplete with the deadline named. A
completion claim is only accepted while the deadline still holds, so work
that crosses it after a stage's last checkpoint (a final sort, the last tree
copy) downgrades that stage to incomplete; trees copied before expiry and a
fully built graph are kept. The budget bounds the runner's work through
enumeration — the command's serialization of the returned rows is outside
it. The engine process runs under RLIMIT_FSIZE at `--max-dump-bytes`, which
constrains the dump and both captured streams, so the OS stops an oversized
writer at the bound, and under RLIMIT_AS at `--max-process-bytes` (default
16 GiB: the release binary reserves just under 10 GiB of virtual address
space at startup, so the ceiling bounds growth beyond that fixed
reservation; it is address space, not resident memory). A limit outcome is
reported only on evidence of that particular exhaustion: the runner's own
timeout; the file-size signal, or a write-failure diagnostic with a
constrained file at the ceiling, naming the affected stream (a file merely
at the ceiling is not evidence — a writer may fill it exactly and fail for
an unrelated reason); or an allocation-failure abort under the memory cap.
Every other nonzero engine exit is a runtime diagnostic (exit 2) carrying a
bounded stderr prefix — read bounded, never sliced from a whole-file read —
with a note when the captured stderr itself hit the ceiling.

Results are staged in a sibling temporary directory and published to
`--output-dir` in one no-replace rename (the lexer bundle writer's
`publish_directory`) only after every unit is written, so a failed or
interrupted run leaves no partial output and never blocks a retry at the
same path. The published set is fixed: `results.jsonl` (one row per unit,
without graphs), `forests.jsonl` in forest mode (one row per unit with the
lossless packed graph and its `graph_complete` flag), and `summary.json`
naming the engine file, its SHA-256, and every limit including
`max_trees`/`max_depth`. Exit status: 0 all units completed, 1 some rejected
and none incomplete, 3 any incomplete, 2 configuration/runtime failure, 130
interrupted. A requested forest or enumeration cut short by a limit counts
as incomplete for the exit status even when recognition accepted.

## The forest consumer

`grammarc.Forest` reads one unit's `node`/`part` facts under the revised
plan's identity contract: a packed alternative is the whole `part` fact,
child descriptor included, and a child `(nt A R2)` expands through production
`R2` alone — expanding the child's symbol node through every production would
emit duplicate trees, because the parent already holds one edge per child
production. `Forest.graph()` is the lossless JSON form of the complete
alternative set; `Forest.enumerate(max_trees, max_depth)` returns Remy's
full-child-list tree shape as a bounded output view and reports whether it
exhausted every alternative (a unit cycle, a count/depth cut, or deadline
expiry makes it incomplete). Traversal keeps its state on explicit stacks, so
the supported limits govern termination and a deep unit cycle cannot exhaust
the Python call stack before the requested depth applies. The constructor
takes the runner's per-unit deadline; construction and `graph()` raise
through it, while `enumerate` stops and keeps the trees found before expiry.
The runner wires enumeration behind `--max-trees`/`--max-depth`, which
require `--engine forest`; per unit it records the trees,
`enumeration_complete` (true only when the graph is also closed), and keeps
"not requested" (`null`) distinct from "attempted but incomplete" (`false`).

## Tests

```bash
cd mm2/parsing/earley
/home/ni/repos/m/bits/mm2/parsing/lexer/.venv/bin/python -m unittest discover -s tests -v
```

Sixty tests: eleven engine tests against the real binary (a `MORK`
environment variable overrides the binary path), eight compiler tests,
twenty-four runner tests that build real version-2 bundles through the lexer
pipeline and drive them through the runner and the command (including the
deadline carried through every Python stage with sound acceptance preserved,
completion claims validated after the final graph sort and the last tree
copy, the oversized-dump writer stopped at the bound by the OS, real
memory-limit exhaustion as a verified incomplete outcome, ordinary engine
failures staying diagnostics with and without a memory cap, an exactly-full
write with an unrelated failure staying a diagnostic, stdout write-limit
failures as confirmed resource outcomes, a flooded stderr as a truncated
diagnostic read under a memory bound, staged publication that survives
missing bundles, interruption, and midway failures without blocking a retry,
and the fixed forest-mode file set), and seventeen forest tests (the
`x + 12` and Remy-oracle trees, the two- and four-tree sibling fixtures with
no duplicate emissions, the merged start root, explicit cycle truncation,
count-limited partial enumeration, the graph JSON round trip, runner-level
enumeration and graph publication including cyclic graphs, a recursion-first
unit cycle under a 10,000 depth limit, and deadline cuts during
construction, graph rendering, enumeration, and the final tree copy). The
engine tests cover: the `x + 12` worked example with its
pinned grammar fingerprint and 13-item chart; wrong, truncated, and empty
streams rejecting only after projection convergence; genuinely unproductive
recursion as stable non-acceptance; the 31-production unit chain, where an
exhausted budget is provably not a rejection; stream/grammar isolation in a
shared space; Remy's `4 + 57 * 6 + 7` under a precedence grammar with the
exact completed-part set of the oracle derivation
`(+ (+ 4 (* 57 6)) 7)`; concatenation-ambiguity `part` counts matching the
boundary-triple formula at 3 and 8 tokens; direct and indirect unit cycles as
finite explicit graph facts; packed alternatives distinguished only by their
child descriptor, independent child ambiguity, and the merged start root; the
two engines agreeing on canonical item and acceptance sets while the
recognition engine emits no forest facts; and a deliberately short `--steps`
cap failing the marker check.

Run this suite and the lexer suite separately (both use a `tests/` package).
Generated run files live under the ignored `output/` directory.
