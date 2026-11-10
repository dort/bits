# Plan: MM2 Earley parser with a span-keyed forest in the space

Written 2026-11-10 by Claude; revised the same day to fold in Codex's review
of the first committed version (`2ea96e9`). This revises the Earley portion
of the pipeline plan in the direction of `parsing/remy.mm2`, and every new
engine claim below — including each runtime claim adopted from that review —
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
- [Codex's review of this plan's first version](review_earley_span_forest_parser.md)
  (2026-11-10) is incorporated throughout: the full packed-alternative
  identity and the production-aware traversal contract, corrected packing and
  cost claims, the merged start-root wording, the precedence-grammar
  regression, and implementation conditions on both amendments. Its runtime
  claims were independently reproduced before adoption.

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
   once the representation gives shared sub-derivations identical spellings,
   set semantics stores each exactly once, and an ambiguous region is simply
   several facts sharing one span key. That is what makes the forest packed.
   The joins, writes, storage, and traversal that produce and consume the
   facts still have measurable costs; packing removes duplication, not work.
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
the two relations carry three entities with distinct identities, all scoped
by `(NS, S, G)`:

| Entity | Identity | Meaning |
| --- | --- | --- |
| Symbol node | `(A, O, P)` | nonterminal `A` spanning `O..P`; one `node` fact |
| Intermediate prefix | `(R, D, O, P)` | the first `D` symbols of production `R` spanning `O..P` |
| Packed alternative | `(R, D, O, M, P, C)` | one complete `part` fact, child descriptor included |

The child descriptor `C` belongs to the alternative's identity, not to its
payload. With the grammar `start → atom; atom → INT | INT` (productions
`aone` and `atwo`) on one token, the engine retains both
`(part … root 1 0 0 1 (nt atom aone))` and
`(part … root 1 0 0 1 (nt atom atwo))` — identical in the five positional
coordinates, two distinct derivations, kept apart because MM2's set key is
the whole fact (probe-verified 2026-11-10). Any consumer map or graph keyed
on fewer than all six components silently overwrites a valid derivation. The
child reference `(nt A R2)` carries the child's production label `R2`, which
the review of the original plan required for representing alternative
derivations faithfully; the traversal contract below says what that label
obliges the consumer to do.

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

The forest consumer reads the dumped facts; it performs no inference. The
contract is production-aware: a child descriptor `(nt A R2)` commits to the
child's production, and the traversal honors that commitment rather than
re-deriving the choice.

- **Root:** the start-symbol node `(node NS S G A 0 N)`. There is exactly
  one such node per accepted unit; distinct accepting start productions are
  its packed alternatives, not separate roots (probe: `start → INT | INT`
  yields one `node` fact and two `part` alternatives).
- **Expanding a symbol node `(A, O, P)`:** for each production `R` of `A`
  with right-hand-side length `L`, gather the packed alternatives of the
  completed prefix `(R, L, O, P)`.
- **Expanding a prefix `(R, D, O, P)`:** each fact
  `(part NS S G R D O M P C)` is one packed alternative, child descriptor
  included. Combine the predecessor prefix `(R, D−1, O, M)` with the last
  child `C` over `M..P`.
- **Expanding a child `(nt A R2)` over `M..P`:** select production `R2`
  alone, verify its left-hand side is `A`, and expand its completed prefix
  `(R2, |R2|, M, P)`. Expanding the child's symbol node through every
  production of `A` instead double-counts, because the parent already holds
  one edge per child production: the two-`atom`-production grammar then
  emits 4 trees of which 2 are distinct, and `start → atom atom` emits 16 of
  4 (review's measurement, interpretation confirmed by the retained facts).
  Post-hoc deduplication is not a remedy — the duplicate emissions waste
  work and can exhaust `--max-trees` before all distinct alternatives are
  returned.
- **Recursion base:** dot 0 is the empty prefix; it contributes an empty
  child sequence exactly when its origin equals its end.
- **Enumeration of concrete trees** is a separate, bounded operation with
  explicit count and depth limits and an explicit truncation marker: the
  graph may contain cycles (probe row three) and acyclic ambiguity can hold
  exponentially many trees. The shared graph — re-serialized to JSON under
  the identities in the table above, preserving the complete alternative set
  — is the primary forest output; enumerated trees are a convenience view.

A considered variant drops the production label from the child descriptor
and points parent edges at the child's symbol node, keeping production labels
only on that node's own alternatives. It shares more parent edges and is
equally correct, but producer and traversal must adopt it together. Version 1
keeps the production-labelled descriptor; what is ruled out is the mixture —
production-specific edges expanded as unrestricted symbol edges.

### Cost, and why forest mode is a flag

`node` facts are bounded by nonterminals times spans, `O(|A|·N²)`. `part`
facts store one fact per distinct derivation step: for the ambiguous
concatenation grammar `expr → expr expr | INT`, the `part` facts of
production `cat` at dot 2 number exactly the boundary triples — 4 = C(4,3)
at N=3 (probe), matching the review's measured 84 = C(9,3) at N=8 and
680 = C(17,3) at N=16 — so `part` storage is Θ(N³) for such grammars. That
exact grammar, production, and dot filter is the stated form of the
regression check, kept at two input sizes.

Retained facts measure stored alternatives, not cumulative completion work:
scan emits `part` facts too, later sweeps revisit the same matches while
their outputs remain single set members, and completed-production counts
exclude prefix alternatives. Measured on the claim-verification probe (three
grammars in one space): doubling the budget from 32 to 64 rounds left the
item/node/part/accepted projection byte-identical while the runtime's
whole-engine counters grew from 2,153 to 4,713 unifications and 3,083 to
6,763 writes. Milestone measurements therefore record separately: retained
items, nodes, and parts (terminal and nonterminal parts distinguished),
sweep count, elapsed time, and the runtime's unification and write counters.
A completion-join count is reported only if that operation is itself
instrumented or counted, never by renaming a retained-fact count.

What forest mode adds is storage, not joins: the same joins run in
recognition-only mode, but forest mode also keeps their witnesses in the
space and the dump. `grammarc parse` therefore defaults to recognition-only
(five rules) and takes `--forest` to load the six-rule engine. The inherited
per-process memory limit applies in both modes alongside the dump-size
limit; the latter bounds output files and is not a substitute for bounding
the in-memory forest before dumping. The two rule files are self-contained
alternatives (`earley/earley.mm2`, `earley/earley_forest.mm2`); the runner
loads exactly one, since rules are data facts and loading both would run
both variants of `cscn`/`dcmp` against the same items.

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
3. **Finite shared graph first, bounded tree enumeration second.** The
   schema makes the *stored* graph finite; cycle-aware traversal, depth and
   count enforcement, and honest truncation remain consumer obligations,
   tested in milestone 5.
4. **Epsilon stays out of grammar version 1 as a scope choice, not a
   correctness need.** The review demonstrated the unchanged engine accepts
   empty derivations under repeated sweeps. When version 2 admits them, the
   schema extends without change: an epsilon completion is a `node` with
   `O = P` and a `part` at dot 0 is simply absent (the empty prefix is the
   recursion base already). The traversal contract will then need an explicit
   empty-production case, because a completed zero-length production has no
   final `part` to find; that case stays future work with the extension.
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
  plan. Cons: `why` facts are joinable in MM2 too — they carry production,
  dot, origin, end, and split — so the difference is usability, not
  possibility. `node` adds a materialized lookup by nonterminal and span,
  `part` an explicit prefix/child relation, and acceptance unifies with the
  forest instead of standing apart. Rejected: same information, better
  indexed and named by `node`/`part`.
- **Assemble n-ary derivation facts in MM2** — Remy's literal
  `(expr (S E) (op (c1) (c2)))` shape with the full child list per fact, via
  per-length assembly rules. Pros: human-readable complete derivations
  queryable in one fact. Cons: because the children are span references, a
  child's internal ambiguity stays at the child's own facts — the shape is
  compatible with packing, not inherently unpacked. What grows is the number
  of split placements: an arity-k production over one span stores one fact
  per placement of its k−1 internal boundaries, where dotted-prefix
  binarization shares every partial child sequence. Fixed-arity rules also
  cap right-hand-side length. Rejected for the engine on those two grounds;
  the bounded Python enumerator produces exactly this shape as its output
  view.
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

   Implementation conditions (from the review, adopted): a strictly
   increasing integer alone does not validate a generated ID — the writer
   verifies the namespace/base, the exact `<base>_u<index>` spelling,
   consecutive indices, the configured unit-count ceiling, and the upfront
   identifier-length bound, and no input field may label an arbitrary name
   "generated" to bypass the duplicate set. The policy is fixed once at the
   source-envelope boundary: one source uses generated IDs or caller-owned
   IDs, never both, since mixing collides (arbitrary `batch_u0` against unit
   zero derived from base `batch`); namespace/stream pairs remain the
   uniqueness key. Required tests: a long generated sequence with no set
   growth, the cap at and one past its boundary, duplicate arbitrary IDs,
   and a mixed-policy attempt — with the capped set's actual memory measured,
   not assumed. Adopting this amendment also updates the integrated plan's
   external-sort test and ownership notes so that two contradictory
   milestone definitions are never both active.
2. **`grammarc parse` grows `--forest`, `--max-trees`, and `--max-depth`**,
   with recognition-only as the default for the cost reason above, and the
   result record gains the four completion flags already specified
   (`recognition`, `closure_complete`, `forest_complete`,
   `enumeration_complete`) — unchanged — plus the engine identity in the
   manifest, since two engines now exist.

   Implementation conditions (from the review, adopted): tree enumeration
   requires `--forest` and always carries finite count and depth limits; a
   result distinguishes "not requested" from "attempted but incomplete" for
   both forest and enumeration; the per-unit deadline covers Python
   traversal and enumeration, not only the MORK process; the manifest
   identifies the engine by content digest as well as filename; and because
   the two engine files duplicate the recognition rules, the suite checks
   parity of their canonical item and acceptance sets on shared fixtures,
   not final verdicts alone — a drifted prediction rule can leave small
   examples accepted while deriving a different chart. Generating both files
   from one maintained rule definition is an acceptable way to keep them
   aligned.

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
(the production-aware traversal contract above, graph serialization under
the full identities, bounded enumeration), and the `--forest` path in the
runner with the projection extended to `node`/`part`.

**Complete when** the fixtures below are regressions on production-labelled
trees, not merely on acceptance or symbol-node counts:

- The `x + 12` tree reproduces exactly, and Remy's complete expression
  `4 + 57 * 6 + 7` under the precedence grammar
  `expr → expr PLUS term | term; term → term STAR atom | atom; atom → INT`
  yields the hand-written oracle
  `(+ (+ (num 4) (* (num 57) (num 6))) (num 7))`, with a unique packed
  alternative at every completed span (probed 2026-11-10 on seven tokens:
  35 items, 12 nodes, 23 parts, accepted). Companions: a repeated-addition
  input checking left association, and a deliberately ambiguous expression
  grammar for contrast.
- The ambiguous concatenation input yields one root node with two packed
  alternatives, and bounded enumeration emits exactly two trees.
- Identically-shaped sibling productions expand production-specifically:
  `start → atom` with `atom → INT | INT` enumerates exactly 2 distinct trees
  and `start → atom atom` exactly 4, with no duplicate emissions.
- The start-symbol root retains all accepting production alternatives: two
  accepting start productions give one root node with two alternatives.
- A graph JSON round trip preserves the complete alternative set, child
  descriptors included.
- Direct and indirect unit cycles yield finite graphs with explicitly
  truncated enumerations, and ambiguity in more than one child position
  combines correctly.
- Forest mode changes no recognition verdict on the milestone-4 suite, and
  the two engine files agree on canonical item and acceptance sets over the
  shared fixtures.
- `part` counts on the concatenation grammar match the boundary-triple
  formula at two input sizes under the stated grammar/production/dot filter.

Token spans remain the parser's identity; character spans and lexemes come
from the existing lexer data, and no destructive whitespace fusion enters
the parser.

## Follow-ups unchanged by this plan

The git-history converter (`bits/mm2/git/load-into-mm2-from-git.py`) still
awaits its retrofit onto the chunk transport codec. Once forest dumps exist,
its query toolkit gains a second consumer of span-keyed facts; nothing there
blocks or is blocked by this plan.
