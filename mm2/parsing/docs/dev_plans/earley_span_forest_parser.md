# Plan: MM2 Earley parser with a span-keyed forest in the space

Written 2026-11-10 by Claude. This revises the Earley portion of the pipeline
plan in the direction of `parsing/remy.mm2`, and every new engine claim below
was verified against the local release MORK binary before being written down.

Relationship to the earlier documents:

- [Codex's integrated pipeline plan](stream_splitter_and_earley_pipeline.md)
  remains the plan of record for shared foundations, the split specification,
  the streaming algorithm, the version-2 bundle, and commands (its sections
  1–4 and 6, milestones 1–3 and 6). This document **replaces its section 5 and
  milestones 4–5** (grammar compilation, execution, witnesses, forests) and
  amends two smaller points listed at the end.
- [Codex's review of the original Earley plan](../../review_detailed_plan_mm2_earley_parser.md)
  stands: all five of its required revisions are incorporated here, restated
  as adopted requirements rather than re-argued.
- [The original Earley plan](../../detailed_plan_mm2_earley_parser.md) remains
  the design history for the grammar JSON schema, the five recognition rules,
  and the sweep driver, all of which are kept.
- [`parsing/remy.mm2`](../../remy.mm2) sets the direction for how parse
  results are represented, and this plan is organized around adopting it.

## What remy.mm2 contributes

Remy's sketch parses `4 + 57 * 6 + 7` with hand-written rules over tokens that
carry character spans, `(tok (num 4) 0 1)` meaning the token `4` occupies
characters 0 to 1. Its load-bearing ideas, in order of importance:

1. **The span is the identity of a constituent.** A parse result is a fact
   `(expr ($s $e) body)` keyed by its half-open span `($s $e)`. Two
   derivations of the same text region meet at the same key.
2. **Children are referenced by span, never inlined.** The body
   `(* ($eleft $left) ($right $eright))` names its operands by *their* spans.
   The parse "tree" is therefore a graph of small facts joined through span
   keys, not one nested term. Under MM2's set semantics this is decisive:
   identical sub-derivations are stored once, and an ambiguous region is
   simply several facts sharing one span key. Packing — the property that
   makes a shared parse forest compact — costs nothing; it is what set
   semantics already does.
3. **Adjacency is a shared endpoint.** Remy's combination rules join an
   expression ending at `$left` with an operator starting at `$left`. No
   successor list is needed; the span arithmetic is free unification. Our
   `(lex-token NS S P Q K)` facts already carry both endpoints, so this works
   unchanged at the token level.
4. **Trivia is fused into spans, not parsed.** His first rule deletes
   whitespace tokens by widening the preceding token's span. In our pipeline
   this concern is already settled one stage earlier: the lexer's skip kinds
   remove trivia from the token index space while `lex-span` facts preserve
   character provenance. The fusion rule is subsumed; no engine rule deals
   with trivia.

What the sketch leaves open, established by running it unchanged against the
release binary (2026-11-10, 0 ms, 16 expressions dumped): its four execs are
one-shot, so combination stops after one pass per rule — the dump contains
`(expr (0 11) ...)` and `(expr (4 14) ...)` but no expression covering the
whole input, because that needs a second pass of the addition rule. The
addition rule's template also writes `*` where `+` is meant (a transcription
slip, interpreted as intended). And the rules are bottom-up with the grammar
baked into exec code: every combinable region is built whether or not any goal
needs it, and precedence does not exist. These are exactly the gaps the
already-probed Earley engine fills: a sweep driver supplies saturation,
grammar-as-data supplies labels and precedence, and prediction supplies goal
direction. The merge of the two is this plan.

## The design: Earley recognition, Remy's forest

Intuition first: an Earley item *is already* a span-keyed fact — "a prefix of
production R spanning tokens O to P". Remy's representation and Earley's item
set are the same idea at different stages of completion. So the engine keeps
the five verified recognition rules and, in forest mode, additionally records
two span-keyed relations as it goes: completed constituents, and the
binarized parent-child edges that explain them. Nothing is reconstructed
afterwards; the forest is a projection of work the rules do anyway.

### Fact schema

Symbols, used consistently below: `NS` namespace and `S` stream ID (one token
input), `G` grammar ID (one immutable compiled grammar), `A` a nonterminal,
`R`/`R2` production names, `L` a production's right-hand-side length, `D` a
dot position (count of consumed right-hand-side symbols), `O` the origin
(token index where the production instance starts), `P` the end token index,
`M` the split index (start of the last consumed child), `K` a terminal kind.

```scheme
(node NS S G A O P)            ; nonterminal A derives tokens O..P
(part NS S G R D O M P C)      ; the prefix of production R up to dot D spans
                               ; O..P; its last child spans M..P and is C
; C = (t K)                    ; a terminal: the token at M..P of kind K
; C = (nt A R2)                ; a nonterminal: node (A, M, P), derived via R2
```

`node` is Remy's `(expr (S E) ...)` with the grammar symbol made explicit and
the body factored out. `part` is his children-by-span body, binarized: because
Earley consumes one right-hand-side symbol per dot advance, the natural edge
is "prefix at dot D = prefix at dot D−1 plus one child", and the full child
list of a completed production is recovered by walking dots L, L−1, …, 1.
This binarization is not a compromise; it is what makes the forest packed
(a shared left prefix is stored once no matter how many right alternatives
extend it). In SPPF terms (Scott and Johnstone's shared packed parse forest),
`node` facts are the symbol nodes keyed `(A, O, P)` and `part` facts are the
packed/intermediate nodes keyed `(R, D, O, M, P)`. The child reference
`(nt A R2)` carries the child's production label `R2`, which the review
required for representing alternative derivations faithfully.

Acceptance unifies with the forest: the input is accepted exactly when a
`node` fact for the start symbol spans `0..N`, with `N` taken from
`(lex-end NS S N C)`.

### Engine rules, probe-verified

Six stored rules, uniform 4-character names in chain order
`ased < bprd < cscn < dcmp < dnod < eacc`, zero `pure` calls, instantiated by
the unchanged sweep driver with the round budget as data:

```scheme
((prule ased) (, (parse $ns $s $g) (grm-start $g $a) (grm-prod $g $r $a $l))
              (, (item $ns $s $g 0 $r 0 0)))
((prule bprd) (, (item $ns $s $g $p $r $d $o) (grm-rhs $g $r $d (nt $a)) (grm-prod $g $r2 $a $l))
              (, (item $ns $s $g $p $r2 0 $p)))
((prule cscn) (, (item $ns $s $g $p $r $d $o) (grm-rhs $g $r $d (t $k)) (lex-token $ns $s $p $q $k) (grm-dot $g $d $d2))
              (, (item $ns $s $g $q $r $d2 $o) (part $ns $s $g $r $d2 $o $p $q (t $k))))
((prule dcmp) (, (item $ns $s $g $p $r $l $o) (grm-prod $g $r $a $l) (item $ns $s $g $o $r2 $d2 $o2) (grm-rhs $g $r2 $d2 (nt $a)) (grm-dot $g $d2 $d3))
              (, (item $ns $s $g $p $r2 $d3 $o2) (part $ns $s $g $r2 $d3 $o2 $o $p (nt $a $r))))
((prule dnod) (, (item $ns $s $g $p $r $l $o) (grm-prod $g $r $a $l))
              (, (node $ns $s $g $a $o $p)))
((prule eacc) (, (parse $ns $s $g) (grm-start $g $a) (node $ns $s $g $a 0 $n) (lex-end $ns $s $n $c))
              (, (accepted $ns $s $g)))
```

Only three deltas from the verified recognizer: `cscn` and `dcmp` gain one
forest template each (a template addition changes no join structure and no
scheduling), `dnod` is new (the repeated `$l` unifies the item's dot with the
production length, so it fires only on completed items), and `eacc` tests the
`node` fact instead of re-deriving completion. Recognition-only mode is the
original five rules unchanged.

Probe results (2026-11-10, release binary, three grammars sharing one space,
16-round budget, 10 ms wall clock including the real lexer bundle for
`x + 12` loaded via `--aux-path`):

| Grammar | Input | Forest evidence in the dump |
| --- | --- | --- |
| `expr → expr PLUS term \| term; term → INT \| IDENT` | `x + 12` (real lexer output, stream `demo s0`) | `(node … expr 0 3)`, accepted; walking `part` facts from it reproduces the unique tree: `(part … sum 3 0 2 3 (nt term num))`, `(part … sum 2 0 1 2 (t PLUS))`, `(part … sum 1 0 0 1 (nt expr lift))`. |
| `expr → expr expr \| INT` (ambiguous) | three `INT` tokens | One node `(node … expr 0 3)` with exactly two packed alternatives: `(part … cat 2 0 1 3 (nt expr cat))` and `(part … cat 2 0 2 3 (nt expr int))` — the split-at-1 and split-at-2 derivations share the key. |
| `expr → expr \| INT` (unit cycle) | one `INT` | Finite cyclic graph: `(part … loop 1 0 0 1 (nt expr loop))` alongside `(part … loop 1 0 0 1 (nt expr inte))`. The cycle is explicit data, and recognition terminates. |

Two properties of the dump worth stating because the traversal contract
relies on them. First, `part` facts exist for prefixes that never complete
(the probe contains `(part … sum 1 0 0 3 (nt expr sum))`, a predicted
continuation of the accepted parse that found no `PLUS`); these are
unreachable from any `node` and are never visited — no cleanup pass exists or
is needed. Second, `node` and `part` are monotonic additions like `item`, so
the closure and convergence machinery below applies to them unchanged.

### Traversal and bounded enumeration (Python, `grammarc/forest.py`)

The forest consumer reads the dumped facts; it performs no inference.

- **Roots:** every `(node NS S G A 0 N)` where `A` is the start symbol — all
  accepting derivations, per the review's multiple-roots requirement.
- **Expanding a node `(A, O, P)`:** for each production `R` of `A` with
  length `L`, each `(part NS S G R L O M P C)` is one packed alternative; its
  last child is `C` over `M..P`, and the remaining children come from
  recursing on the prefix key `(R, L−1, O, M)`, down to dot 0 (the empty
  prefix at `O`).
- **Enumeration of concrete trees** is a separate, bounded operation with
  explicit count and depth limits and an explicit truncation marker, exactly
  as the review requires: the graph may contain cycles (probe row three) and
  acyclic ambiguity can hold exponentially many trees. The shared graph —
  optionally re-serialized to JSON with the same span keys — is the primary
  forest output; enumerated trees are a convenience view.

### Cost, and why forest mode is a flag

`node` facts are bounded by nonterminals times spans, `O(|A|·N²)`. `part`
facts materialize completion *joins*, not just items: for the ambiguous
concatenation grammar the probe shows the dot-2 `part` count equals the
number of boundary triples (4 = C(4,3) at N=3, matching the review's measured
84 = C(9,3) at N=8 and 680 = C(17,3) at N=16), so `part` storage is Θ(N³) for
such grammars. The same joins run in recognition-only mode — the review's
point that completion work is already cubic stands — but forest mode also
*stores* their witnesses in the space and the dump. Therefore `grammarc
parse` defaults to recognition-only (five rules) and takes `--forest` to load
the six-rule engine, with the dump-size limit doing double duty as the forest
budget. The two rule files are self-contained alternatives
(`earley/earley.mm2`, `earley/earley_forest.mm2`); the runner loads exactly
one, since rules are data facts and loading both would run both variants of
`cscn`/`dcmp` against the same items.

## Adopted requirements from the review (unchanged in substance)

1. **Rejection requires established closure.** Per-unit outcomes are
   accepted / rejected / incomplete with distinct exit statuses; the sweep
   budget grows (doubling) until the semantic projection stabilizes or a
   limit makes the unit incomplete. The 31-production unit-chain grammar is a
   regression: small budgets report incomplete, never rejection.
2. **Convergence compares a canonical semantic projection**, now defined as
   the deduplicated, sorted `item`, `node`, `part`, and `accepted` facts for
   the requested `(NS, S, G)` — excluding round tables, execs, and
   instrumentation. `node`/`part` lag `item` by at most one sweep inside the
   same sweep batch (rule order `cscn < dcmp < dnod`), so projection equality
   across two consecutive completed budgets certifies all four relations at
   once. The execution-completed marker (a fact scheduled after the final
   sweep) is still required before any comparison; a clean process exit alone
   proves nothing.
3. **Finite shared graph first, bounded tree enumeration second** — satisfied
   structurally by the schema above rather than by consumer discipline.
4. **Epsilon stays out of grammar version 1 as a scope choice, not a
   correctness need.** The review demonstrated the unchanged engine accepts
   empty derivations under repeated sweeps. When version 2 admits them, the
   schema extends without change: an epsilon completion is a `node` with
   `O = P` and a `part` at dot 0 is simply absent (the empty prefix is the
   recursion base already).
5. **No conventional Earley runtime bound is claimed.** Milestone
   measurements record items, `part` counts (equivalently completion joins),
   witness growth, sweeps, and wall time separately, on unit chains, right
   recursion, and the ambiguous concatenation grammar.

The review's clarifications are adopted as stated there: the shared
strict-JSON/fingerprint helpers are extracted to `tokenizer/config.py` with
the lexer migrated in the same change; `grammarc parse` consumes a completed
version-2 token bundle (raw-text convenience composes the existing APIs
later); a grammar ID denotes one immutable compiled grammar and conflicting
loads are rejected at the orchestration boundary; monotonic-saturation
language is scoped to this engine, not MM2 as a whole.

## Alternatives considered

- **Pure bottom-up chart parsing (remy.mm2 generalized with a sweep
  driver).** One stored rule per grammar production, no items, no
  prediction; `node`-like facts are the only relation. Pros: fewest concepts;
  the forest is the whole state; closest to the sketch. Cons: no goal
  direction — every nonterminal is built over every derivable span whether or
  not the start symbol can use it, which on long units with rich grammars
  does strictly more work than prediction admits; productions longer than two
  symbols need binarization anyway (a compile step inventing intermediate
  symbols — the dotted prefix by another name); and grammar-in-exec-code
  means per-grammar MM2 code generation subject to the rule-name shortlex
  ordering constraints, which are easy to violate mechanically and painful to
  debug. Rejected: Earley with forest templates reaches the same facts
  goal-directed, with the grammar as plain data.
- **Keep the previous `why` witness design** (item-keyed witness facts,
  forest reconstructed only in Python). Pros: smallest diff from the original
  plan. Cons: witnesses keyed by item coordinates rather than span keys make
  the dump opaque to further MM2 queries, acceptance stays separate from the
  forest, and the Python extractor must re-derive constituent structure that
  `node`/`part` state directly. Rejected: same information, worse key.
- **Assemble n-ary derivation facts in MM2** — Remy's literal
  `(expr (S E) (op (c1) (c2)))` shape with the full child list per fact, via
  per-length assembly rules. Pros: human-readable complete derivations
  queryable in one fact. Cons: it is the *unpacked* form — one fact per
  combination of child alternatives, so a production with two ambiguous
  children multiplies rather than shares, and fixed-arity rules cap
  right-hand-side length. Rejected for the engine; the bounded Python
  enumerator produces exactly this shape as its output view.
- **Dedicated acceptance rule on items (previous `eacc`)** versus
  acceptance from `node`. Kept the node-based form in forest mode (one
  concept fewer, probe-verified) and the item-based form in the five-rule
  recognition-only file.

## Amendments to the pipeline plan of record

Two points in the integrated plan change; everything else there is adopted.

1. **Duplicate stream-ID checking: bounded set with a cap, not external
   sorting.** Split-derived IDs `<base>_u<index>` are unique by construction
   and validated arithmetically (strictly increasing emitted-unit index).
   Caller-owned IDs arise only when a caller hands the serializer multiple
   explicit streams, which today is tests and small compositions. The writer
   therefore checks caller-owned IDs in an in-memory set up to a fixed cap
   (100,000 IDs, a few megabytes) and raises a named limit error beyond it,
   stating that unbounded caller-owned ID sets are unsupported in this
   release. The 8 MiB-run/32-way-merge external sort is deferred until a real
   producer of unbounded caller-owned IDs exists; building it now is
   speculative machinery on a path no caller exercises. The memory bound is
   preserved either way — one is a cap, the other an algorithm, and the cap
   is honest about which inputs it serves.
2. **`grammarc parse` grows `--forest`, `--max-trees`, and `--max-depth`**,
   with recognition-only as the default for the cost reason above, and the
   result record gains the four completion flags already specified
   (`recognition`, `closure_complete`, `forest_complete`,
   `enumeration_complete`) — unchanged — plus the engine-file identity
   (which rule file ran) in the manifest, since two engines now exist.

## Milestones (replacing the integrated plan's 4 and 5)

Milestones 1–3 (shared foundations, version-2 archive, splitter) and 6
(scale evidence) proceed exactly as the integrated plan specifies, with
amendment 1 applied inside milestone 2.

### Milestone 4 — grammar compiler and honest recognition

`earley/grammarc` (spec.py, serialize.py, runner.py, `__main__.py`) and
`earley/earley.mm2` (the five verified rules). Grammar JSON schema, pinned
fingerprint, and the 13-item worked example carry over from the original
plan. The runner implements budget doubling over the semantic projection
(`item` + `accepted` in this mode), the execution-completed marker, per-unit
limits, fresh space per unit, and the accepted/rejected/incomplete contract.

**Complete when:** the worked expression, left and right recursion, wrong
tokens, truncated input, multiple grammars and streams in isolation fixtures,
the 31-production unit chain (incomplete under small budgets, accepted under
sufficient ones, never falsely rejected), and a genuinely unproductive
recursive grammar (stable rejection distinguishable from exhaustion) all
behave as specified against the real binary, reading real version-2 bundles.

### Milestone 5 — span-keyed forest

`earley/earley_forest.mm2` (the six rules above), `grammarc/forest.py`
(traversal, graph serialization with span keys, bounded enumeration), and the
`--forest` path in the runner with the projection extended to `node`/`part`.

**Complete when:** the probe fixtures are regressions — the `x + 12` tree
reproduces exactly; the ambiguous concatenation input yields one root node
with two packed alternatives and bounded enumeration emits exactly two trees;
direct and indirect unit cycles yield finite graphs and explicitly truncated
enumerations; multiple accepting start productions all appear as roots;
ambiguity in more than one child position combines correctly; forest mode
changes no recognition verdict on the milestone-4 suite; and `part` counts on
the concatenation grammar match the boundary-triple formula at two sizes, so
the cost documentation stays tied to measurement.

## Follow-ups unchanged by this plan

The git-history converter (`bits/mm2/git/load-into-mm2-from-git.py`) still
awaits its retrofit onto the chunk transport codec. Once forest dumps exist,
its query toolkit gains a second consumer of span-keyed facts; nothing there
blocks or is blocked by this plan.
