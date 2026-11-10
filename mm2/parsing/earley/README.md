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
named), `closure_complete`, `forest_complete` (`null` unless `--engine
forest` was requested), `enumeration_complete` (always `null`: tree
enumeration is not implemented), the budgets that ran to their marker, and
fact counts. Wall time (default 30 s per unit, covering all reruns),
dump-size, and optional process-memory (`--max-process-bytes`, RLIMIT_AS)
ceilings all turn into `incomplete`, never into a claimed rejection; engine
process failures without a memory cap are runtime diagnostics (exit 2).
Results go to `results.jsonl` plus a `summary.json` naming the engine file
and its SHA-256. Exit status: 0 all units completed, 1 some rejected and none
incomplete, 3 any incomplete, 2 configuration/runtime failure, 130
interrupted. A requested forest or enumeration cut short by a limit counts as
incomplete for the exit status even when recognition accepted.

## The forest consumer

`grammarc.Forest` reads one unit's `node`/`part` facts under the revised
plan's identity contract: a packed alternative is the whole `part` fact,
child descriptor included, and a child `(nt A R2)` expands through production
`R2` alone — expanding the child's symbol node through every production would
emit duplicate trees, because the parent already holds one edge per child
production. `Forest.graph()` is the lossless JSON form of the complete
alternative set; `Forest.enumerate(max_trees, max_depth)` returns Remy's
full-child-list tree shape as a bounded output view and reports whether it
exhausted every alternative (a unit cycle or a count/depth cut makes it
incomplete). The runner wires this behind `--max-trees`/`--max-depth`, which
require `--engine forest`; per unit it records the trees,
`enumeration_complete` (true only when the graph is also closed), and keeps
"not requested" (`null`) distinct from "attempted but incomplete" (`false`).

## Tests

```bash
cd mm2/parsing/earley
/home/ni/repos/m/bits/mm2/parsing/lexer/.venv/bin/python -m unittest discover -s tests -v
```

Thirty-six tests: eleven engine tests against the real binary (a `MORK`
environment variable overrides the binary path), eight compiler tests, seven
runner tests that build real version-2 bundles through the lexer pipeline
and drive them through the runner and the command, and ten forest tests
(the `x + 12` and Remy-oracle trees, the two- and four-tree sibling
fixtures with no duplicate emissions, the merged start root, explicit cycle
truncation, count-limited partial enumeration, the graph JSON round trip,
and runner-level enumeration). The engine tests cover: the `x + 12` worked example with its
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
