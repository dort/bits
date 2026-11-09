# Detailed plan: MM2 Earley parsing over the lexer token contract

## Status of the prior step

The Python 3.14 lexer planned in `detailed_plan_python_tokenization.md` is
implemented in `lexer/`, reviewed in `review_lexer_implementation.md`, and
accepted: 45 tests pass under the project's CPython 3.14.10, and the MM2
transport (token edges, declared-kind catalog, fingerprint facts, hex-chunk
payloads) is verified against the real MORK runtime. This document plans the
step the lexer plan deferred: an Earley parser written in MM2 that consumes
the `lex-*` facts.

This document plans only the recognizer and derivation-witness layer plus its
Python grammar compiler. Semantic evaluation, format-specific grammars,
ambiguity scoring, and error recovery are later work. Implementation lives in
`bits/mm2/parsing/earley/`, a sibling of `lexer/`.

**The core design below is already probe-verified, not speculative.** On
2026-11-09 a hand-written five-rule engine (exactly the rules in this plan)
was run against the lexer's real `output/expression/tokens.mm2`: a
left-recursive expression grammar produced `(accepted demo s0 g0)` for
`x + 12` in 3 ms, and a deliberately inadequate grammar loaded into the same
space produced no acceptance and only two items — stalled, goal-directed, and
uncontaminated by the first grammar's items.

## Why Earley fits MM2

Intuition first: an Earley parser maintains a growing set of "items," each
recording partial progress of one grammar production over the input. The
parser only ever adds items, never retracts one. MM2's entire execution model
is monotonic saturation of a fact set. The two are the same shape.

Mechanism: every Earley operation is a Horn rule — new item from existing
items plus grammar facts plus token facts. No negation appears anywhere:
acceptance is a positive fact, and rejection is its absence. The lexer
contract was designed for exactly this consumption: `(lex-token NS S P Q K)`
already stores each token's successor position `Q`, so the parser's scan step
is a pure join with no arithmetic, and `(lex-end NS S N C)` supplies the
accepting boundary `N` as a joinable value.

Earley's predict step is also the goal-directed component: only nonterminals
reachable from the start symbol at reachable positions ever generate items.
This is the same magic-sets discipline as the sieve — delete the demand fact
`(parse NS S G)` and nothing derives.

## Alternatives considered

| Decision | Chosen approach and benefit | Alternative and tradeoff |
| --- | --- | --- |
| Parsing algorithm | Earley: accepts any context-free grammar as written (left and right recursion, ambiguity), predict gives goal direction, all four operations are monotonic joins. Also the stated project goal. | CYK needs Chomsky-normal-form conversion (obscures the authored grammar and complicates forest read-back) and derives every derivable span with no goal direction, but its sweep count is exactly the input length — no saturation-budget question. GLR/LR need automaton construction, a separate compiler artifact. |
| Dot and position arithmetic | Successor facts as data: `(grm-dot G I I2)` from the grammar compiler, token successors already in `lex-token`. Zero `pure` calls in the engine. | `sum_i64` via the pure sink per advance: works, but pays one grounded evaluation per rule firing in the hottest rules, and the sieve work showed data beats repeated pure evaluation. |
| Terminal/nonterminal dispatch | Constructors in the grammar facts: `(grm-rhs G R I (t K))` and `(grm-rhs G R I (nt A))`. Scan and predict dispatch purely by unification — the clean-representation rule from the differentiation refactor. | Bare symbols plus classification facts (`(grm-term G K)`): one more join per rule and a defaulty representation that invites classify-by-failure mistakes. |
| Items and multiple grammars | Items carry the grammar id: `(item NS S G P R D O)`. Two grammars can parse one stream in one space without cross-joining (probe-verified), and predict/scan/complete need no join against the demand fact. | Items without `G`, constrained to one grammar per space: one field smaller, but a silent cross-contamination hazard the moment a second grammar loads, and the hot rules then need the `(parse ...)` join to find `G`. |
| Scheduling | Stored rules plus a sweep driver, with the round budget emitted as `(nextround ...)` data by the Python side, which knows the token count. Fixpoint is verified externally: the test harness doubles the budget and requires a byte-identical dump. | Unrolling into one-shot exec ladders (the sieve2 doctrine) needs a statically known sweep count; Earley's count depends on grammar chain depths, not just a query-computable logarithm. Revisit after measurement if re-derivation cost dominates. |
| Grammar authoring format | JSON with the lexer's schema discipline (versioned, duplicate-key rejection, fingerprint by the identical recipe), compiled to facts by a Python package that imports the lexer's `tokenizer` for the shared transport checks (`checked_atom`, error hierarchy, fingerprint). | A BNF text format reads better but adds a parser before the parser works. Duplicating the transport helpers instead of importing them would fork the 63-byte guard into two copies. |

Do not add semantic actions, grammar composition, or incremental reparsing in
this first implementation.

## Grammar specification (Python side)

A new package `earley/grammarc/` mirrors `lexer/tokenizer/`: load and
validate a JSON grammar, compile it, and serialize MM2 facts plus a manifest.

Schema, version `1`:

```json
{
  "version": 1,
  "start": "expr",
  "productions": [
    {"name": "sum",  "lhs": "expr", "rhs": [{"nt": "expr"}, {"t": "PLUS"}, {"nt": "term"}]},
    {"name": "lift", "lhs": "expr", "rhs": [{"nt": "term"}]},
    {"name": "num",  "lhs": "term", "rhs": [{"t": "INT"}]},
    {"name": "ref",  "lhs": "term", "rhs": [{"t": "IDENT"}]}
  ]
}
```

- Production names and nonterminals match `[a-z][a-z0-9_]{0,31}`; terminals
  match the lexer's kind regime `[A-Z][A-Z0-9_]{0,31}`. Case separates the
  vocabularies; the constructors make the separation structural anyway.
- Production names are unique. `start` and every referenced nonterminal must
  be some production's `lhs` (no undefined nonterminals). Each `rhs` element
  is an object with exactly one of `nt`/`t`.
- **Epsilon productions are rejected in version 1** (`rhs` nonempty). The
  lexer never emits empty tokens, and empty derivations need the nullable
  precomputation (Aycock–Horspool): the compiler would emit
  `(grm-nullable G A)` facts and the engine one extra advance rule. That is a
  planned extension, not a v1 feature; the fact schema below leaves room for
  it.
- JSON hygiene and the fingerprint are byte-identical to the lexer's:
  duplicate-key rejection via `object_pairs_hook`, `parse_constant`
  rejection, exact integer `version`, and SHA-256 over
  `json.dumps(grammar, ensure_ascii=True, sort_keys=True,
  separators=(",", ":"), allow_nan=False)`.
- Given `--tokens <lexer manifest or bundle>`, the compiler checks that every
  terminal is in the lexer's declared-kind catalog and fails with the
  offending names otherwise. This is where the `lex-kind` facts pay off:
  the worst silent failure (grammar terminal never emitted, parse silently
  empty) becomes a named configuration error before MORK runs.

## Grammar fact schema

Placeholders; generated files substitute ground values. `G` is the grammar
id (caller-supplied, same identifier regime as namespaces), `R` a production
name, `A` a nonterminal, `K` a terminal kind, `I` a zero-based position in a
production's right-hand side, `L` a right-hand-side length, and `D0`/`D1`
the two fingerprint halves in the lexer's `h`+32-hex encoding.

```scheme
(grm-grammar G 1)                 ; grammar + transport contract version
(grm-spec G sha256 D0 D1)
(grm-start G A)
(grm-prod G R A L)                ; production R: A -> length-L body
(grm-rhs G R I (t K))             ; terminal at body position I
(grm-rhs G R I (nt A))            ; nonterminal at body position I
(grm-dot G I I2)                  ; I2 = I + 1, for I in 0 .. max L - 1
```

All atoms pass the lexer's `checked_atom` guard; every one is short by
construction (names ≤ 32 bytes, decimal indices bounded by production
length).

## The engine (probe-verified)

One item fact per Earley item. `NS S` name the token stream, `G` the
grammar, `P` the current input position, `R` the production, `D` the dot
(how many body symbols are consumed), `O` the origin (input position where
this production instance started). `P` sits directly after the stream/grammar
prefix because the two expensive rules, scan and complete, both bind it.

```scheme
(item NS S G P R D O)
(parse NS S G)                    ; the demand fact — the magic-set root
(accepted NS S G)                 ; the positive acceptance verdict
```

The five rules, exactly as probed. Names are uniform 4-character,
lexicographically in dependency order (`ased < bprd < cscn < dcmp < eacc`),
per the scheduling doctrine:

```scheme
((prule ased) (, (parse $ns $s $g) (grm-start $g $a) (grm-prod $g $r $a $l))
              (, (item $ns $s $g 0 $r 0 0)))

((prule bprd) (, (item $ns $s $g $p $r $d $o)
                 (grm-rhs $g $r $d (nt $a)) (grm-prod $g $r2 $a $l))
              (, (item $ns $s $g $p $r2 0 $p)))

((prule cscn) (, (item $ns $s $g $p $r $d $o)
                 (grm-rhs $g $r $d (t $k))
                 (lex-token $ns $s $p $q $k) (grm-dot $g $d $d2))
              (, (item $ns $s $g $q $r $d2 $o)))

((prule dcmp) (, (item $ns $s $g $p $r $l $o) (grm-prod $g $r $a $l)
                 (item $ns $s $g $o $r2 $d2 $o2)
                 (grm-rhs $g $r2 $d2 (nt $a)) (grm-dot $g $d2 $d3))
              (, (item $ns $s $g $p $r2 $d3 $o2)))

((prule eacc) (, (parse $ns $s $g) (grm-start $g $a) (grm-prod $g $r $a $l)
                 (item $ns $s $g $n $r $l 0) (lex-end $ns $s $n $c))
              (, (accepted $ns $s $g)))
```

Mechanism notes, one per rule:

- **ased** seeds one dot-zero item at position 0 for each start production;
  everything else derives from these, so deleting `(parse ...)` derives
  nothing.
- **bprd** (predict): an item whose next body symbol is nonterminal `$a`
  demands dot-zero items for `$a`'s productions at the current position.
  Duplicate predictions collapse under set semantics, which is what makes
  left recursion terminate.
- **cscn** (scan): the next body symbol is terminal `$k` and the token edge
  at `$p` carries `$k`, so the item advances to the edge's stored successor
  `$q`. No arithmetic: both successors are data.
- **dcmp** (complete): the repeated variable `$l` in the first two patterns
  unifies the item's dot with its production's length — "dot at end" tested
  by unification alone. The parent item is found by matching its current
  position to the completed item's origin `$o`.
- **eacc**: a completed start production spanning origin 0 to position `$n`,
  where `$n` also joins `lex-end`'s token count, is acceptance of exactly
  the whole input.

Driver and budget, reusing the sieve's verified pattern (spawned tag `d0`
sorts before driver tag `dz`, so each sweep's rules run before the driver
advances):

```scheme
(exec (dz r001)
  (, (exec (dz $r) $p $t) (nextround $r $r2) ((prule $k) $sp $st))
  (, (exec (d0 ($r $k)) $sp $st) (exec (dz $r2) $p $t)))
```

The `(nextround r001 r002) ...` table is **emitted by the Python side**,
which knows the token count `N` from the lexer manifest. Within one sweep
the rules run in name order (predict, scan, complete), so a sweep advances
at least one scan plus its surrounding predictions and completions; chains
of completions (right recursion) and of predictions (deep nonterminal
nesting) consume extra sweeps. Default budget: `4 * (N + 2)` rounds,
refined by measurement in milestone 4.

**Termination honesty:** MM2 cannot detect its own fixpoint, and a too-small
budget silently under-derives (acceptance may be missing with no error). Two
mitigations, both mandatory: the test harness reruns every fixture with a
doubled budget and requires a byte-identical dump (external fixpoint proof
per test case), and the README documents the budget as part of the contract
rather than presenting saturation as unconditional.

## Complexity and scale

Item count is the standard Earley bound: at most one item per (production,
dot, origin, position), so O(|G| · N²) facts for grammar size |G| and token
count N. The MM2-specific cost is that a sweep driver re-instantiates every
rule against the whole space each sweep — there is no semi-naive delta — so
total work is roughly sweeps × full-join cost, worst case O(N) × O(N²·|G|).
Version 1 targets inputs up to a few hundred tokens and must measure item
counts, sweep counts at fixpoint, and wall time across N before any
optimization. The known escape hatches if measurement demands them:
per-position unrolled ladders for the scan chain, and splitting the item
relation by dot progress to shrink the complete join.

## Derivation witnesses (milestone 3)

Recognition answers "does it parse"; the forest answers "how." Witness facts
are emitted by the same scan/complete rules extended with one extra template
each (monotonic, so ambiguity accumulates as multiple witnesses for one
item):

```scheme
(why NS S G P R D O (scan K P0))        ; item arrived by scanning K at P0
(why NS S G P R D O (comp R2 M))        ; item arrived when R2, spanning
                                        ; M .. P, completed
```

Python-side extraction (in `grammarc`) reads the dumped space, walks `why`
facts backward from the accepting item, and reconstructs derivation trees,
enumerating alternatives where multiple witnesses exist. The classic
ambiguity fixture (`expr -> expr PLUS expr | INT` over `1 + 2 + 3`) must
yield exactly its two trees. Forest extraction is deliberately outside MM2:
tree assembly is traversal with ordering, not saturation, and the lexer
already set the precedent that reassembly belongs to the consumer.

## Running

`mork run <data.mm2> <dump.mm2> --aux-path <engine.mm2>` is the invocation
shape (verified by the lexer's MORK tests and this plan's probe): data —
grammar facts, token facts, demand, budget — as the main input, the fixed
engine as the auxiliary file, results read from the dump file rather than
scraped from stdout. A `grammarc parse` subcommand orchestrates it
end-to-end: lexer bundle in, grammar in, demand and budget generated,
`mork` invoked (repository-relative discovery with a `MORK` environment
override, as in the neighboring projects), verdict and optional trees out.

## Worked example

Grammar `g0` as in the schema section, fingerprint halves
`h8711aca694c020c03214bd2105a00212` `h1864f95c644556d81121422f9281851d`
(computed with the pinned recipe; a test must re-derive them, as
`test_plan_fixture_is_synchronized` does for the lexer). Against the lexer's
`x + 12` bundle (`IDENT PLUS INT`, `lex-end ... 3 6`), the probe produced
`(accepted demo s0 g0)` with 13 items for `g0` — among them
`(item demo s0 g0 1 lift 1 0)` (an `expr` found at positions 0–1) and the
left-recursive climb `(item demo s0 g0 3 sum 3 0)` whose completion yields
the accepting `expr` over the whole input. Grammar `g1` (`expr -> term`,
`term -> INT`) in the same space stopped at its two seed/predict items:
no token edge satisfies its only scan, and no acceptance appears.

## Proposed directory layout

```text
parsing/
  earley/
    README.md                    # Usage, contract, budget semantics, limits
    earley.mm2                   # The engine: prule store + driver skeleton
    grammarc/
      __init__.py                # load/compile/serialize/extract API
      __main__.py                # compile and parse subcommands
      spec.py                    # schema validation (imports lexer tokenizer)
      serialize.py               # grm-* facts, demand, budget table
      forest.py                  # dump reader and derivation-tree extraction
    specs/
      expression_demo.json       # The worked-example grammar
      ambiguous_demo.json        # expr -> expr PLUS expr | INT
    tests/
      test_grammar_spec.py
      test_recognizer.py         # real-MORK accept/reject matrix
      test_forest.py
      fixtures/
    output/                      # Ignored generated output
```

Run with the lexer's interpreter and environment (`lexer/.venv`); the
compiler imports `tokenizer` with `lexer/` on the path. No new environment,
no third-party dependencies.

## Milestones

### 1. Grammar compiler

Schema validation with the lexer's JSON discipline, compilation, `grm-*`
serialization through `checked_atom`, fingerprint, `--tokens` terminal
cross-check, demand/budget emission. **Done when:** valid grammars compile
deterministically, each listed invalid grammar fails with the field and
production named, and the worked example's fingerprint halves match this
document.

### 2. Recognizer

`earley.mm2` finalized from the probe; accept/reject test matrix against
real MORK: the worked example; left recursion (`sum`), right recursion
(budget stress), nested parentheses (requires extending the demo lexical
specification with paren rules — an engine test case, not an application);
rejection on wrong token, truncated input, empty input versus
nullable-free grammar; two grammars in one space; two streams in one space.
Every fixture reruns at doubled budget and must dump byte-identical.
**Done when:** the matrix passes and the budget doubling changes nothing.

### 3. Witnesses and forest extraction

Extend scan/complete with `why` templates; implement `forest.py`; ambiguity
fixture yields exactly two trees; unambiguous fixtures yield exactly one
tree matching a hand-written oracle. **Done when:** extracted trees
reproduce each fixture's oracle and the recognizer-only results are
unchanged by the extra templates.

### 4. End-to-end command, measurement, documentation

`grammarc parse` runs text → tokens → facts → mork → verdict/trees from one
command; measure items, sweeps-to-fixpoint, and wall time over increasing N
and grammar size; justify the default budget constant from those
measurements; README documents the contract, the budget semantics, and the
limitations (no epsilon, no semantic actions, scale envelope). **Done when:**
both demonstrations run from documented commands and the measured budget
evidence is recorded.

## Related follow-up outside this plan

`bits/mm2/git/load-into-mm2-from-git.py` still emits quoted symbols beyond
63 bytes, which the runtime truncates and collapses
(`review_detailed_plan_python_tokenization.md` §1). Retrofitting it onto the
lexer's chunk codec is now a mechanical change and should be scheduled as
its own small task once this parser step stabilizes the shared transport
helpers.
