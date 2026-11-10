# Critical review: Remy's contribution and Claude's span-forest plan

Reviewed by Codex on 2026-11-10:

- [Remy's sketch](../../remy.mm2), committed in `1cf8fc6`.
- [Claude's revised Earley plan](earley_span_forest_parser.md), committed in
  `2ea96e9`. Line numbers below refer to that plan version.

**Keep the architectural direction, but revise the forest identity and traversal
contract before implementation.** The proposed MM2 facts retain the alternatives
in the cases I tested. The principal correctness risk is how those facts become
Python graph nodes, edges, and enumerated trees. The plan's stated packed-node
key is insufficient to identify an alternative, and its child-expansion recipe
does not explicitly enforce the production restriction it stores.

Several arguments for the design also need correction. Remy's span references
already share child ambiguity; they are not inherently an unpacked tree format.
Retained `part` counts measure stored alternatives, not cumulative completion
work. These corrections strengthen the explanation for the proposed design
without requiring another parser algorithm.

## 1. High priority: specify complete alternative identities and production-aware traversal

**Plan locations:** fact schema and SPPF correspondence, lines 85–104;
traversal, lines 160–166; multiple-root requirement, lines 315–319.

The plan calls `(R, D, O, M, P)` the packed/intermediate node key, where `R` is
the parent production, `D` its dot position, `O` its origin, `M` its last-child
start, and `P` its end. That tuple does not identify a complete `part` alternative
because the child descriptor can differ.

For this valid grammar, `start` is the start symbol and `INT` the terminal:

```text
root: start -> atom
aone: atom  -> INT
atwo: atom  -> INT
```

On input `1`, the unchanged six-rule engine produces both facts:

```scheme
(part demo s0 g0 root 1 0 0 1 (nt atom aone))
(part demo s0 g0 root 1 0 0 1 (nt atom atwo))
```

They have the same proposed five-coordinate key. MM2 retains both because its
set key is the entire fact. A Python dictionary or JSON graph assigning one
alternative to that abbreviated key would overwrite one valid derivation.
Grouping by the key is fine only if the value preserves every alternative.

The child descriptor introduces a second obligation. `(nt atom aone)` means
expand the `aone` production of `atom` over this child span. If traversal instead
expands the symbol node through every `atom` production, it repeats alternatives
already distinguished by the two parent facts.

I exercised both interpretations with a small read-back probe over the actual
MORK dump:

| Grammar shape | Correct production-specific expansion | Expanding all child productions at every child edge |
| --- | ---: | ---: |
| `start -> atom`, two `atom -> INT` productions | 2 trees, both distinct | 4 emissions, only 2 distinct |
| `start -> atom atom`, the same two child productions | 4 trees, all distinct | 16 emissions, only 4 distinct |

These results do not demonstrate a defect in the six MM2 rules. They demonstrate
two consumer implementations the current prose does not distinguish adequately.
Post-hoc tree deduplication is not the remedy: duplicated emissions waste work
and can exhaust `--max-trees` before all distinct alternatives are returned.

**Requested contract:** distinguish symbol nodes, intermediate prefix nodes,
and complete packed alternatives. Include namespace, stream ID, and grammar ID
in every relevant scope. Within that scope, use the following identities:

| Entity | Identity and meaning |
| --- | --- |
| Symbol node | `(A, O, P)`: nonterminal `A` spanning `O..P`. |
| Intermediate prefix | `(R, D, O, P)`: the first `D` symbols of production `R` spanning `O..P`. |
| Packed alternative | `(R, D, O, M, P, C)`: one complete `part`, including child descriptor `C`. |

Then define distinct traversal operations:

1. Expanding a symbol node gathers every completed production alternative for
   that symbol and span.
2. Expanding `(nt A R2)` selects only child production `R2`, verifies that its
   left-hand side is `A`, and expands its complete prefix over the child span.
3. Expanding a prefix gathers every corresponding packed alternative and
   combines the predecessor prefix with the selected last child.
4. Dot zero contributes an empty child sequence only when the prefix origin
   equals its end.

An alternative design can omit the child's production from the reference and
point directly to the symbol node, retaining production labels on that node's
own alternatives. That can share more parent edges. It is also correct, but
the producer and traversal must adopt it together. Do not retain the present
production-specific edges while expanding them as unrestricted symbol edges.

The root wording also needs adjustment. With `first: start -> INT` and
`second: start -> INT`, the engine produces **one** start-symbol node and two
production alternatives. I verified that result. Replace “multiple accepting
start productions all appear as roots” with “the start-symbol root retains all
accepting production alternatives.” The current identity intentionally merges
those productions at the symbol-node level.

**Required tests:** both ambiguity fixtures above; a graph JSON round trip
preserving the complete alternative set; and the two-start-production fixture
with one root and two alternatives. These should test production-labelled trees,
not merely acceptance or the number of symbol nodes.

## 2. Medium priority: correct the claims about packing and the rejected representations

**Plan locations:** “What remy.mm2 contributes,” lines 33–40; alternatives,
lines 243–256.

The plan first correctly explains that Remy's children are references to spans,
then rejects his full-child-list shape as inherently unpacked because ambiguous
children multiply parent facts. Those claims are inconsistent.

Consider two alternatives for the left child over `0..1` and two for the right
child over `1..2`. A Remy-style parent can still be the single fact:

```scheme
(expr (0 2) (pair (0 1) (1 2)))
```

The two referenced child spans retain their alternatives. The parent need not
inline a choice of either child's internal derivation. I ran a minimal MM2
probe joining all four child combinations with this template: it produced
exactly one parent fact and retained the four child alternatives.

The correct reason to prefer dotted-prefix binarization is different: it shares
partial child sequences and avoids materializing every complete sequence of
split positions for long productions. Full child-reference lists can share
subtrees while still having worse storage growth with production arity.
An ordered list of child references is compatible with packing; it is not itself
an enumeration of trees. This distinction is also present in the graph-edge
definition in [Zaytsev's paper on shared packed forests](https://grammarware.net/text/2015/sppf-gcm.pdf).

Similarly, the previous `why` facts are not opaque to MM2. They contain
production, dot, origin, end, and split information that MM2 rules can join.
The proposed `node` relation is a useful materialized lookup by nonterminal and
span, and `part` exposes an explicit prefix/child relation. Those are valid
usability and indexing advantages; they do not establish that the earlier
representation could only be queried in Python.

**Requested revision:** retain the chosen `node`/`part` design, but justify it
through explicit prefix sharing and useful query relations. Replace “packing
costs nothing” with the precise statement that set semantics removes duplicate
facts once the representation supplies suitable identities. Additional joins,
writes, forest storage, and graph traversal still have measurable costs.

## 3. Medium priority: retained alternatives are not cumulative completion work

**Plan locations:** cost discussion, lines 176–185; adopted measurement
requirement, lines 215–218; milestone 5, lines 320–322.

The boundary-triple count is a good regression for this particular grammar's
completed binary-production alternatives. It does not make total `part` count
equivalent to completion joins:

- Scan also emits `part` facts.
- The same completion match is revisited in later sweeps, while its output
  remains one set member.
- Counts for completed binary productions exclude other prefix alternatives.

For `expr -> expr expr | INT` on three integer tokens, I obtained:

| Supplied rounds | Total `part` facts | Dot-2 `cat` parts | Runtime unifications | Runtime writes |
| ---: | ---: | ---: | ---: | ---: |
| 16 | 13 | 4 | 678 | 958 |
| 32 | 13 | 4 | 1,446 | 2,030 |

The canonical semantic projections were identical. The runtime counters grew
because the second run did more work even though it retained no additional
alternatives. These counters cover the whole engine, not just completion.

**Requested revision:** record separately the retained items/nodes/parts,
terminal versus nonterminal parts, sweep count, elapsed time, and available
runtime counters. If the report specifically claims a completion-join count,
instrument or count that operation rather than renaming a retained-fact count.
Keep the four-at-three-tokens boundary-triple check with its exact grammar,
production, and dot filter stated.

Recognition-only as the default is a sensible consequence of the added storage
cost. Retain the inherited process-memory limit as well as the dump-size limit;
the latter is not a substitute for limiting the in-memory forest before dumping.

## 4. Medium priority: make Remy's complete expression a grammar-and-tree regression

**Plan locations:** discussion of the sketch, lines 53–64; milestone 5,
lines 309–322.

Claude's diagnosis of the unchanged sketch is reproducible: it dumps 16 facts,
does not produce a constituent over the full character span `0..14`, and writes
`*` in the addition template. The plan appropriately adopts its representation
rather than treating that file as a finished general parser.

However, the new plan's named tree fixtures do not check the property illustrated
by Remy's opening comment: both multiplication precedence and left-associated
addition in `4 + 57 * 6 + 7`. Scheduling multiplication before addition is not
a general precedence definition once rules are repeatedly applied. Precedence
must come from the authored grammar.

I tested the unchanged forest engine with this non-nullable grammar:

```text
expr -> expr PLUS term | term
term -> term STAR atom | atom
atom -> INT
```

I extended the lexical specification only in the probe to recognize `STAR` and
fed the real tokenizer's seven-token output to both engines. Forest mode
produced 35 items, 12 symbol nodes, and 23 parts, with one derivation. The
recognition-only engine produced exactly the same item and acceptance facts.

**Requested regression:** add that complete expression and check the labelled
derivation against a hand-written oracle whose operator grouping is:

```text
(+ (+ (num 4) (* (num 57) (num 6))) (num 7))
```

This is a structural fixture, not a request to introduce semantic evaluation.
Also test repeated addition and a contrasting ambiguous expression grammar.
Keep token spans as the parser's identity and obtain character spans/lexemes
through the existing lexer data; do not reintroduce destructive whitespace
fusion into the parser.

## Amendments I accept, with implementation conditions

### Capped caller-owned identities are a reasonable simplification

I accept replacing my earlier external-sort requirement with a finite cap on
caller-owned IDs, provided the limitation is explicit. Supporting the actual
generated-unit path does not require supporting arbitrarily large collections
of arbitrary caller-owned names. A named limit error preserves the memory
promise without speculative disk-sorting machinery.

The two identity policies need precise boundaries, though. A strictly increasing
integer alone does not validate the emitted ID. For generated streams, verify
the namespace/base, the exact `<base>_u<index>` spelling, consecutive indices,
the configured count ceiling, and the upfront identifier-length bound. A caller
must not bypass duplicate checking simply by supplying a field that labels an
arbitrary name “generated.”

Define the policy once at the source-envelope boundary. Either reject mixing
generated and arbitrary IDs inside that source, or explicitly check collisions
between them. For example, arbitrary `batch_u0` collides with unit zero derived
from base `batch`. Namespace/stream pairs remain the uniqueness key.

Test a large generated sequence without growing the set, the arbitrary-ID cap
at and beyond its boundary, duplicate arbitrary IDs, and a mixed-policy attempt.
Measure actual memory for the capped representation rather than relying on
“a few megabytes.” Update the integrated plan's external-sort tests and file
ownership notes when this amendment is adopted; do not leave both contradictory
milestone definitions active.

### Recognition-only and forest modes are justified

Loading exactly one engine is the right constraint. An optional forest has a
real additional storage cost, so this is a product capability rather than a
legacy fallback. The manifest should identify the actual engine contents,
for example with a digest, in addition to its filename.

Because two files duplicate recognition rules, add parity checks of their
canonical **item and acceptance sets**, not only their final Boolean verdicts.
Generating both artifacts from one maintained rule definition is also an
option. A changed prediction rule can leave small examples accepted while
deriving a different chart; verdict-only tests would miss that divergence.

Clarify command semantics: whether tree enumeration requires `--forest`, what
finite limits apply when it is requested, and how an unrequested forest or
enumeration is represented in results. “Not requested” should not be confused
with “attempted but incomplete.” The shared per-unit deadline must also cover
Python traversal/enumeration, not stop at MORK process exit.

### Retain the previous completion and cycle requirements

The revised plan correctly carries forward verified closure before rejection,
canonical projections, a final execution marker, explicit incomplete outcomes,
and finite graphs with bounded enumeration. No request here changes those.

The sentence claiming bounded tree enumeration is satisfied structurally should
be narrowed: the schema makes the stored graph finite; the consumer still needs
cycle-aware graph traversal, depth/count enforcement, and honest truncation.
The future epsilon extension also needs an explicit empty-production expansion
case because the stated “find a final `part`” recipe has none at dot zero.
That can remain future work; it is not a reason to expand version 1 now.

## Evidence and disposition

I copied the six forest rules exactly from the new plan and the driver/five-rule
recognizer exactly from the original plan. Probes used the current lexer Python
3.14 environment and `/home/ni/repos/m/MORK/target/release/mork`. The experiment
inputs, engine copies, and dumps are in the ignored local directory
`lexer/output/span-forest-review/` under the parsing project. No production
parser or lexer file was changed.

The probes reproduced the three-token concatenation result, its two trees,
the finite unit-cycle graph, and Remy's unfinished one-shot result. They also
exercised the alternative-key collision, two independently ambiguous children,
merged start-symbol roots, repeated-sweep cost, and the complete expression
with a precedence grammar. The small tree reader used for these probes is
evidence for those cases, not a substitute for the planned tested consumer.

Before implementation, resolve the full packed-alternative identity and the
production-specific child-expansion contract, correct the packing/cost claims,
and add the missing regression cases above. With those revisions, Remy's span
references and the Earley rules form a coherent basis for the parser and its
queryable forest.
