# Symbolic differentiation in MM2

Computes exact derivatives of expression trees by forward rewriting in the
MORK space, over a **clean (strongly typed) AST**: every case of the
expression grammar has its own constructor, so every rule dispatches by
pattern (unification) alone. There are no catch-all default rules, no
deletion-ordered else-branches, and no classify-by-parse-failure — the
"clean rather than defaulty representation" discipline from Prolog
practice. Integer arithmetic (constant folding, the power rule's exponent
decrement, zero/one tests) is grounded in Rust via the `pure` sink.

## The AST

```
leaves:     (num N)    integer literal, N an i64 symbol
            (var x)    THE variable of differentiation (one per program;
                       the name is documentation)
            (cst c)    any other symbolic leaf (parameters, other
                       variables): derivative 0
compounds:  (add u v) (sub u v) (mul u v) (div u v)
            (pow u (num N))     exponent embedded, an i64 literal
            (neg u) (sin u) (cos u) (exp u) (ln u)
```

The AST is self-describing, so the input is just `(diff EXPR)` facts —
the old `(dvar _)` / `(const _)` declarations are gone, and so is the
old integer detector that pushed every subterm through Rust's parser
and relied on parse failure to filter.

## Files

- `diff_engine.mm2` — the engine (rules only, no data)
- `simplify.mm2` — opt-in post-process simplifier: concatenated after the
  engine, it rewrites each `(result E D)` in place with D simplified
- `diff_engine_fused.mm2` — standalone alternative engine that fuses
  simplification into the differentiation rewriting itself, never writing
  an unsimplified derivative
- `example.mm2` — sample inputs
- `test.mm2` — test suite for unsimplified results (plain engine only)
- `test_simplify.mm2` — test suite for simplified results, shared by both
  simplification implementations
- `run.sh` — concatenates input + engine (+ optional layers), runs `mork run`

## Usage

```
./run.sh                                  # plain engine, unsimplified results
./run.sh test.mm2                         # expect CORRECT per case, no MISTAKE
./run.sh example.mm2 simplify.mm2         # post-process simplification
./run.sh test_simplify.mm2 simplify.mm2   # simplified-results suite
ENGINE=diff_engine_fused.mm2 ./run.sh example.mm2        # fused engine
ENGINE=diff_engine_fused.mm2 ./run.sh test_simplify.mm2  # same suite, fused
```

Output: `(result EXPR D)`, e.g.

```
(diff (pow (var x) (num 3)))
=> plain:      (result (pow (var x) (num 3)) (mul (mul (num 3) (pow (var x) (num 2))) (num 1)))
=> simplified: (result (pow (var x) (num 3)) (mul (num 3) (pow (var x) (num 2))))
```

## How the differentiator works

Differentiation is structural recursion, but MM2 has no call stack —
only pattern matching against the space and monotonic writes. The engine
replaces the recursion with two saturation phases over subterm facts.

**Setup** (`(0 _)` tag). `(todo Z EXPR)` seeds each diff root at depth
level `Z` (a Peano numeral).

**Phase A — top-down decomposition** (`(a0 _)`, `(az _)` tags). A
self-recreating driver (the wiki's Reachability P1 pattern) walks depth
levels. Decomposition rules are stored as data — `((arule $k $l)
PATTERNS TEMPLATES)` — and the driver instantiates all of them at the
current level by unifying `$l` (the Counter Machine pattern), because a
per-operator loop would die on any level where its operator happens not
to occur. Each level produces `(todo (S l) child)` per child, `(sub E)`
per compound subterm, and one `(level l)` fact. The loop ends when a
level generates no todos.

**Base derivatives** (`(b0 _)` tags). One-shot execs dispatching on the
leaf constructors: `(num _) -> (num 0)`, `(var _) -> (num 1)`,
`(cst _) -> (num 0)`. The only `pure` call here is the power rule's
exponent decrement — `(expm1 (num n) (num n-1))` via `sub_i64` — real
arithmetic whose argument the `(num $n)` pattern guarantees to parse.

**Phase B — bottom-up combination** (`(c0 _)`, `(cz _)` tags).
Combination rules stored as data join child derivatives into parent
derivatives (`(d E DE)` facts). One sweep of all rules per `(level l)`
fact: MM2 has no negation, so "nothing new was derived" is not
expressible, but the level count is tree depth + 1 and each sweep
completes at least one more height layer, so the count always suffices.

**Collect** (`(zz _)` tag). `(diff $e)` joined with `(d $e $de)` yields
`(result $e $de)`.

## The two simplification implementations

Both eliminate the redundancy the derivative rules generate:
`(add (num 0) e) -> e`, `(mul (num 1) e) -> e`, `(mul (num 0) e) ->
(num 0)`, `(mul (num -1) e) -> (neg e)`, `(sub e (num 0)) -> e`,
`(sub e e) -> (num 0)`, `(div (num 0) e) -> (num 0)`, `(div e (num 1))
-> e`, `(div e e) -> (num 1)`, `(pow e (num 1)) -> e`, `(pow e (num 0))
-> (num 1)`, `(neg (num n)) -> (num -n)`, `(neg (neg e)) -> e`, integer
`add`/`sub`/`mul` folded by Rust. Division by zero is an error value:
`(div e (num 0)) -> UNDEFINED`, `(div (num 0) (num 0))` included, and
`UNDEFINED` is contagious — any node over it collapses to it. Both pass
`test_simplify.mm2` and produce byte-identical result sets.

### Clean dispatch instead of an else-branch

A smart constructor's hard case is the *default*: "no simplification
applied, keep the node as built" — the complement of the special cases,
which naive pattern matching cannot express. The previous version
implemented it defaultily (special-case rules deleted the candidate they
reduced; a later catch-all converted survivors — dispatch by execution
order and deletion). This version enumerates the complement as patterns
over reified classification facts, computed for every simplified value:

```
(val V)       V occurs as a value
(ctor V c)    V's constructor tag; one variable-head rule
              (val ($f $a $b)) -> (ctor ($f $a $b) $f) covers every
              binary constructor, one literal rule per 2-element one
(isexpr V)    ctor is anything but num     [(exprtag c) membership data]
(def V)       num or isexpr — i.e. not UNDEFINED
(zn V NZ|Z)   (on V NO|O)  (mn V NM|M)
              for V = (num n): n nonzero / not-one / not-minus-one,
              computed by Rust (the pure sink's ifnz on n, n-1, n+1)
(vne A B)     A, B structurally different, from the != source — the
              complement of unification, used by the build rules whose
              identity siblings (sub e e) / (div e e) own the equal case
```

With these, every constructor's rule set is a **total case analysis**:
e.g. `mul`'s left operand is either `(num 0)`, `(num 1)`, `(num -1)`
(literal patterns), a number outside those (`zn`/`on`/`mn` all negative),
an `isexpr`, or `UNDEFINED` — six disjoint cases, each with its own
rule, and the few overlapping pairs (a fold and a zero rule both
matching `(mul (num 0) (num 5))`) always **agree**, so duplicates
collapse in the set-based space. Nothing is ever deleted; the whole
simplifier is monotonic saturation. Set membership is data
(`(exprtag c)`, `(negtag c)` facts), not code.

### `simplify.mm2` (post-process)

A structural sibling of the engine, running after `(zz out)` in the
3-character `(zz? _)` tag range: seed each result's derivative into its
own `stodo`/`ssub` namespace, decompose top-down, emit leaf base cases
`(s leaf leaf)` by constructor dispatch, then rebuild bottom-up — one
classify sweep (`zze`) plus one construct sweep (`zzf`) per recorded
`slevel`. `(s E S)` means "E simplifies to S"; because children are
clean before a parent is assembled, redundancy is always at the root of
the node being built, where the case analysis sees it.

### `diff_engine_fused.mm2` (fused)

The plain engine's combination rules build multi-level trees in one
template (the product rule writes `(add (mul du v) (mul u dv))` at
once), so nested redundancy appears where no root-level rule set can
reach it. The fused engine builds every derivative one node at a time
through smart-constructor facts: `(mkq E)` requests the simplified form
of a node whose children are already simplified, `(mkd E S)` answers,
keyed by the request. Requests persist (nothing deletes them); the same
total case analysis resolves each to exactly one answer. Chains run up
to three requests deep (quotient, power), so the driver runs four
logic/classify/resolve rounds per depth level, sequenced by tags
`(c0 ((l r ph) k))` that sort round-major then phase-major. Semantic
difference from the post-process pair: input subterms copied verbatim
into derivatives (the `u` in `(mul (cos u) du)`) are not simplified.

### One scheduling rule worth knowing

Within a sweep, rule instances execute in rule-name order, and MM2
compares symbols **length-first**. The classification chain (`aval` →
`c***` → `iexp` → `jdf*` → `nz**` → `znee`) therefore uses uniform
4-character names in lexicographic chain order; a 3-character name
anywhere in the chain would jump the queue and delay its stage by a full
sweep, starving deep expressions of their sweep budget (this exact bug
occurred during development and surfaced as one missing result on the
deepest example).

## Limitations / possible extensions

- One variable of differentiation per program: `(var _)` *is* that
  variable. Multiple simultaneous variables would need a marker joined
  through every rule, and "some other variable" is precisely a
  disequality — expressible now via the `!=` source if wanted.
- Remaining redundancy is what the rule set does not cover: no
  like-term collection (`(add (var x) (var x))` stays, rather than
  `(mul (num 2) (var x))`), no constant evaluation of the unary
  functions (`(ln (num 1)) -> (num 0)`), no trigonometric identities.
  Each new identity is: its rule, plus a narrowing of the build rules'
  case analysis so the two stay disjoint or agreeing.
- `(pow u E)` requires a literal `(num N)` exponent — a symbolic
  exponent is a different derivative rule (`u^v` needs `ln`), not a
  missing case of this one.
