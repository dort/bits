# Review: MM2 Earley parser plan

Reviewed by Codex on 2026-11-09:
[detailed_plan_mm2_earley_parser.md](detailed_plan_mm2_earley_parser.md),
introduced in commit `0788da6`. Line references below refer to that version.

**Revise before implementation.** The five recognition rules, tagged grammar
symbols, token-successor joins, and grammar-qualified items are a sound basis.
The main problems are the definition of a completed parse, the proposed
convergence test, and unbounded tree extraction. These can produce false
rejections, tests that cannot pass, or a nonterminating consumer respectively.
They do not require replacing Earley or moving recognition out of MM2.

I read the plan, the lexer contract and implementation, the existing MORK
integration tests, the sieve scheduling examples, and the runtime scheduler.
I also ran the plan's exact five rules and driver against the local release
binary. The findings distinguish observed runtime behavior from design
recommendations. This review does not modify the plan or parser implementation.

## 1. High priority: establish completion for every parse before returning rejection

**Location:** “Why Earley fits MM2,” lines 33–35; “Driver and budget,” lines
196–209; recognizer and command milestones, lines 309–336.

The default budget depends only on token count. Grammar depth is unrestricted,
so even a one-token input can require more sweeps than the default permits.
Testing selected fixtures with twice the budget does not establish completion
for a new grammar supplied to the command. Documenting this limitation still
leaves the command liable to report a valid input as rejected.

For a concrete counterexample, use start nonterminal `a00` and these 31
productions, where `INT` is the lexer's integer terminal:

```text
a00 -> a01
a01 -> a02
... one unit production per consecutive pair ...
a29 -> a30
a30 -> INT
```

A unit production has exactly one nonterminal on its right-hand side. All these
productions satisfy the proposed version-1 restrictions. For input `1`, the
token count is one, so the proposed default is 12 rounds.

| Rounds actually supplied | Item facts | Acceptance fact |
| ---: | ---: | --- |
| 12 | 13 | absent |
| 24 | 25 | absent |
| 64 | 62 | present |
| 128 | 62 | present |

These are measured results from the unchanged engine. The 12- and 24-round
runs had no pending `exec` facts: finishing the driver does not establish
completion of the Earley closure. In particular, the plan's statement that
each sweep advances at least one scan is false for a long prediction chain.

**Recommended change:** make convergence part of `grammarc parse`, not just its
test harness. Run additional complete sweeps, or rerun with increasing budgets,
until the relevant derived fact set stops changing. Specify three outcomes:

- **Accepted:** a valid acceptance fact exists. Recognition alone can report
  this before closure; complete forest output still requires closure.
- **Rejected:** closure is established and acceptance is absent.
- **Incomplete:** a time, round, or memory limit prevents establishing closure.
  Give this a distinct result and exit status.

The existing Python orchestration can own this check while all Earley inference
continues to run in MM2. A proved bound that incorporates grammar structure is
an alternative, but an empirically chosen constant times input length is not
such a bound. Also check that the runtime completed the scheduled work before
treating unchanged output as evidence of closure.

**Required regression:** this chain must either accept or explicitly report
incomplete when constrained by a small limit. It must never report rejection
merely because its budget expired. Include a genuinely unproductive recursive
grammar to verify that stable nonacceptance is distinguishable from exhaustion.

## 2. High priority: compare semantic results, not entire dumps

**Location:** scheduling alternative, line 54; convergence requirement, lines
204–209 and 317–318.

The required byte-identical dump comparison cannot pass as written. The input
contains the budget's `nextround` facts, none of the five rules removes them,
and MORK dumps the entire space. Doubling the budget changes that space even
when the parser has already reached its fixed point.

I ran the worked expression at 20 and 40 rounds. Both runs accepted and
contained the same 13 item facts. Their full dumps differed in exactly 20
additional `nextround` facts. The sets of `item` and `accepted` facts were
identical.

**Recommended change:** define a canonical semantic projection of a dump:
parse its facts, select `item`, `accepted`, and, when enabled, `why` for the
requested stream and grammar, remove duplicates, and sort their canonical
representations. Compare that projection across runs with the same grammar,
tokens, and demand. Exclude scheduling data and runtime instrumentation.
Validate execution completion separately rather than ignoring unfinished work.

For this monotonic engine, equality after additional complete sweeps is useful
evidence: once a whole sweep adds nothing, repeating the same rules over the
same fixed input cannot restart progress. Comparing only the acceptance Boolean
is insufficient; both incomplete chain runs above lack acceptance while their
item sets differ. When promising complete derivations, compare witnesses too.

**Required regression:** the 20-/40-round expression runs pass the projected
comparison, while the 12-/24-round chain runs fail it.

## 3. High priority: separate a finite witness graph from enumeration of all trees

**Location:** “Derivation witnesses,” lines 224–243; milestone 3, lines 320–326.

Rejecting epsilon productions does not ensure that the derivation graph is
acyclic or that the number of trees is finite. The proposed grammar schema
permits this grammar with start symbol `expr`:

```text
loop: expr -> expr
base: expr -> INT
```

Input `1` has a direct derivation through `base`, and derivations with one, two,
or any number of `loop` applications. Recognition terminates because duplicate
items collapse. Enumerating all those trees cannot finish.

With the proposed witness templates added to the scan and complete rules, the
local runtime produced four items and three witnesses, including:

```scheme
(why demo s0 g0 1 loop 1 0 (comp loop 0))
```

This says that the completed `loop` production over token positions zero to one
can use that same completed production as its child. A recursive walk without
cycle handling revisits the same node indefinitely. Simply dropping a visited
node would silently discard valid derivations.

**Recommended change:** make a finite, shared witness graph the primary forest
result. Preserve cycles explicitly. Provide tree enumeration as a separate,
bounded operation with documented count/depth limits and a clear indication
when enumeration is incomplete. Even without cycles, an ambiguous grammar can
have exponentially many trees. Recognition should continue to accept grammars
with unit cycles; restricting tree enumeration does not require restricting
recognition.

Spell out the backward traversal contract as well: dot-zero items represent
empty prefixes; a scan refers to its predecessor prefix and token occurrence;
a completion refers to its predecessor prefix and completed child production.
Collect every completed start production spanning the input as a root. Preserve
production identities when representing alternative derivations.

The proposed witness fields look sufficient for these references with the
current grammar and token facts. The missing part is the extraction contract,
not evidence that another MM2 inference rule is needed. The distinction between
recognition and a compact representation of all derivations is also central to
[Scott and Johnstone's work on parsing from cubic recognizers](https://pure.royalholloway.ac.uk/en/publications/recognition-is-not-parsing-sppf-style-parsing-from-cubic-recognis/).

**Required regressions:** direct and indirect unit cycles; ambiguity in more
than one child position; multiple accepting start productions; and bounded
enumeration of a larger ambiguous input. Keep the proposed two-tree expression
fixture, but do not use it as the only check of forest extraction.

## 4. Medium priority: correct the explanation for excluding epsilon

**Location:** grammar restrictions, lines 86–91.

The claim that empty derivations require nullable precomputation does not apply
to this repeated whole-space saturation engine. The absence of empty lexer
tokens is also independent of whether a grammar can derive empty input.

A zero-length production is already complete at dot zero. Prediction or seeding
creates that item; completion can advance a waiting parent without consuming a
token. Later sweeps revisit parents created after the empty completion, which
is the case that requires special care in a once-only worklist implementation.

Using hand-written grammar facts, without changing any engine rule, I observed:

| Grammar | Input | Rounds | Result |
| --- | --- | ---: | --- |
| `expr ->` empty body | empty | 8 | accepted, 1 item |
| `expr -> empty empty`, with `empty ->` empty body | empty | 16 | accepted, 4 items |

These probes bypass the proposed compiler's epsilon rejection; they demonstrate
what the engine supports, not what the version-1 schema currently promises.

[Aycock and Horspool's paper](https://webhome.cs.uvic.ca/~nigelh/Publications/PracticalEarleyParsing.pdf)
describes repeated prediction/completion as an existing solution to the empty-rule
ordering problem, then develops nullable precomputation to avoid that repeated
work. The plan already chooses repeated sweeps.

**Requested correction:** if epsilon remains deferred, describe that as an
intentional testing and forest-support scope limit. Do not introduce nullable
facts solely to solve a correctness problem the current scheduling already
addresses. Supporting epsilon now is also reasonable after defining closure
and empty-derivation witnesses, but this review does not require expanding v1.

## 5. Medium priority: distinguish item count from completion-join work

**Location:** “Complexity and scale,” lines 213–222.

The quadratic item bound is useful, but it does not imply quadratic work per
full sweep. A completion combines a parent origin, a split position, and a
child end position. Many combinations yield the same resulting item, so set
deduplication of outputs does not eliminate the joins that produce them.

For a concrete example, let `expr -> expr expr | INT` parse a sequence of integer
tokens. For every three boundaries `origin < split < end`, the completion rule
can join the left and right expressions. With witnesses enabled, each split is
retained as a distinct explanation for the completed two-child production.
The local runtime produced 84 such witnesses for eight tokens and 680 for
sixteen tokens. These counts equal the number of triples of boundaries:
`choose(9, 3)` and `choose(17, 3)` respectively.

For one fixed grammar, define `N` as the input token count and `B` as the number
of full sweeps. Completion joins can therefore already be cubic in `N` in one
sweep. Repeating them can introduce a factor of `B`; the plan's stated
`O(N) × O(N² · |G|)` worst-case time is not established. Dependence on grammar
size also needs to account for pairs of compatible productions, not just the
number of resulting item facts.

**Recommended change:** retain the item-space bound, define grammar size as
including production-body lengths, and remove the unsupported runtime bound.
Measure successful completion joins or runtime unifications, witness counts,
and sweep counts alongside items and wall time. Include long unit chains,
right recursion, and the ambiguous concatenation grammar in the measurements.
Choose any later indexing or scheduling change from those results.

## 6. Clarifications to settle while revising the plan

These are smaller than the three correctness requirements above.

- **Shared compiler helpers:** the proposed dependency on `tokenizer` is sensible,
  but the shared fingerprint/strict-JSON API does not yet exist. In
  [lexer/tokenizer/spec.py](lexer/tokenizer/spec.py), fingerprinting is inline
  in `compile_spec()`, which validates lexical specifications, and JSON hooks
  are private functions. `checked_atom` is available from
  [lexer/tokenizer/serialize.py](lexer/tokenizer/serialize.py). Name the small
  shared helper API to extract and migrate the lexer to it in the same change.
  Keep the existing digest fixtures as regression checks. Importing the lexer
  compiler cannot directly validate a grammar specification.
- **Command inputs:** “Running” describes `grammarc parse` as consuming a lexer
  bundle; milestone 4 describes it as consuming raw text. Specify the required
  command arguments and primary input contract. Consuming an existing completed
  bundle is a clear first interface; optional tokenization can call the existing
  lexer API. Define checks for bundle version, completion, stream identity,
  counts, and agreement between manifest metadata and the loaded token facts.
- **Identity in a shared space:** state that a grammar ID identifies one immutable
  compiled grammar, just as a namespace/stream pair identifies one token input.
  Distinct IDs isolate the demonstrated parses. Reusing an ID for different
  grammar facts merges them; merely storing two `grm-spec` fingerprints does
  not prevent that merge. Validate conflicting loads at the orchestration
  boundary. The driver table also needs one owner per run when several parses
  share a space.
- **MM2 terminology:** the parser's item relation is monotonic. MM2 itself is a
  rewriting system whose scheduler consumes `exec` instructions and whose
  sinks can remove facts. Replace “MM2's entire execution model is monotonic
  saturation” with the narrower statement about this engine. Similarly,
  deleting demand after execution does not retract existing items; the
  goal-direction claim applies to starting a fresh space without demand.
  The relevant local references are
  [the runtime scheduler](../../../MORK/kernel/src/space.rs) and
  [the MM2 operational semantics](../../../MORK.wiki/Minimal-MeTTa-2-(MM2).md).

## Verified parts worth retaining

- The documented grammar fingerprint reproduces exactly:
  `8711aca694c020c03214bd2105a002121864f95c644556d81121422f9281851d`.
- The unchanged engine accepts the real lexer serialization of `x + 12` and
  produces the documented 13 items. The successor joins and completed-dot
  unification work with the current runtime.
- The `d0`/`dz` scheduling order works in the probes. Every budget tested
  completed its scheduled executions without leaving pending `exec` facts.
- Structural terminal/nonterminal tags, grammar-qualified items, declared-kind
  checks, and preserving lexeme transport in the existing lexer are appropriate.
- Keeping recognition in MM2 and graph traversal in Python is a useful division
  of responsibilities. The review does not recommend another parsing engine,
  third-party dependency, or format-specific grammar.

## Evidence and revised completion criteria

Runtime probes used `/home/ni/repos/m/MORK/target/release/mork` and the lexer's
Python 3.14 environment. The recognition engine was copied exactly from the
plan's rule and driver code blocks. Witness probes added only the described
scan and completion templates. Generated inputs and dumps are available locally
under the ignored directory
`lexer/output/earley-plan-review/`; they are supporting experiments, not a new
parser implementation or committed test suite.

Before implementation, update the plan so that:

1. Rejection requires established closure, and exhausted limits have an explicit
   incomplete outcome for every command invocation.
2. Convergence compares canonical parser facts, with execution completion
   checked separately.
3. Forest output preserves sharing and cycles, while concrete tree enumeration
   has a bounded, documented contract.
4. The epsilon explanation and runtime complexity claims reflect this engine's
   actual mechanism.
5. The compiler-sharing and command-input contracts are concrete enough to
   implement and test without duplicating existing infrastructure.

With those revisions, the plan provides a reasonable basis for the next step.
