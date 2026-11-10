# MM2 Earley engines

The two engine artifacts from the
[span-forest Earley plan](../docs/dev_plans/earley_span_forest_parser.md),
the `grammarc` grammar specification compiler, and tests that run everything
under the real MORK binary. There is no production runner, bundle reader, or
tree enumerator here yet; those are later assignments in the
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

## Tests

```bash
cd mm2/parsing/earley
/home/ni/repos/m/bits/mm2/parsing/lexer/.venv/bin/python -m unittest discover -s tests -v
```

Nineteen tests: eleven engine tests against the real binary (a `MORK`
environment variable overrides the binary path) and eight compiler tests, one
of which also runs MORK on compiler-generated facts. The engine tests cover: the `x + 12` worked example with its
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
