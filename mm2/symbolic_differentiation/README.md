# Symbolic differentiation in MM2

Computes exact derivatives of expression trees by forward rewriting in the
MORK space. Integer handling is grounded: integer leaves are recognized and
the power rule's exponent decrement is computed by Rust i64 functions via
the `pure` sink (`kernel/src/pure.rs`), not by Peano encodings. The test
file additionally uses the `+`/`-` sinks for set difference.

## Files

- `diff_engine.mm2` — the engine (rules only, no data)
- `simplify.mm2` — opt-in post-process simplifier: concatenated after the
  engine, it rewrites each `(result E D)` in place with D simplified
- `diff_engine_fused.mm2` — standalone alternative engine that fuses
  simplification into the differentiation rewriting itself, never writing
  an unsimplified derivative (see "Two simplification implementations")
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

Input facts:

```
(dvar x)          ; the variable of differentiation (exactly one)
(const a)         ; every non-integer leaf symbol besides the dvar
(diff EXPR)       ; an expression to differentiate (any number)
```

Integer literals (`2`, `-7`, ...) need no declaration: the grounded phase
detects them by parsing with Rust's i64 parser.

Output: `(result EXPR D)` with D unsimplified, e.g.

```
(diff (sin (* x x)))
=> (result (sin (* x x)) (* (cos (* x x)) (+ (* 1 x) (* x 1))))
(diff (pow x 3))
=> (result (pow x 3) (* (* 3 (pow x 2)) 1))
```

Supported operators: binary `+ - * /` and `(pow u n)` with an i64 literal
exponent, unary `neg sin cos exp ln`.

## How it works

Differentiation is structural recursion, but MM2 has no call stack — only
pattern matching against the space and monotonic writes. The engine
replaces the recursion with two saturation phases over subterm facts.

**Setup** (`(0 _)` tags). `(d $x 1)` for the diff variable, `(d $c 0)` for
each declared constant, and `(todo Z EXPR)` seeding each diff root at
depth level `Z`.

**Grounded integer arithmetic** (`(b0 _)` tags, between the phases). Two
one-shot execs call Rust i64 functions through the `pure` sink. One writes
`(d n 0)` for every integer leaf, using the call tree
`(sub_i64 (i64_from_string $e) (i64_from_string $e))` — n − n, which
evaluates iff `$e` parses as an i64. The other writes `(expm1 n m)` with
m = n − 1 for every `(pow u n)` exponent. The sink drops any match whose
evaluation errors (`sinks.rs` catches the `EvalError` and continues), so
compound subterms and non-integer symbols are skipped rather than
crashing; a `pow` with a symbolic exponent therefore gets no `expm1` fact
and silently produces no derivative.

**Phase A — top-down decomposition** (`(a0 _)`, `(az _)` tags). A
self-recreating driver (the Reachability P1 pattern) walks depth levels.
Decomposition rules are stored as data — `((arule $k $l) PATTERNS
TEMPLATES)` — and the driver instantiates all of them at the current level
by unifying `$l` (the Counter Machine pattern), because a per-operator
loop would die on any level where its operator happens not to occur. Each
level produces `(todo (S l) child)` for every child, `(sub E)` for every
compound subterm, and one `(level l)` fact. The driver's continuation
condition is `(todo $l $_)`: when a level generates no todos (all leaves),
the driver writes nothing and the loop ends.

**Phase B — bottom-up combination** (`(c0 _)`, `(cz _)` tags). Combination
rules are also stored as data, level-free: from `(sub (+ $u $v))` and the
child derivatives `(d $u $du)`, `(d $v $dv)`, write
`(d (+ $u $v) (+ $du $dv))`; the `pow` rule additionally joins the
grounded `(expm1 $n $m)` fact to build
`(d (pow $u $n) (* (* $n (pow $u $m)) $du))`. One sweep of all rules only joins subterms
whose children already have `d` facts, so sweeps must repeat once per tree
level — but MM2 has no negation, so "no new fact was derived" is not
expressible as a stopping condition. Instead the driver runs exactly one
full sweep per `(level l)` fact recorded in phase A. The level count is
tree depth + 1, and after k sweeps every subterm of height ≤ k has its
derivative, so this count always suffices and the loop terminates by
running out of level facts.

**Collect** (`(zz _)` tag). `(diff $e)` joined with `(d $e $de)` yields
`(result $e $de)`.

### Priority layout

MM2 selects the highest-priority `exec` by shortlex order on the tag.
All tags here are arity-2 expressions, so order is lexicographic on the
first element:

```
(0 _) < (a0 _) < (az _) < (b0 _)  < (c0 _) < (cz _) < (zz _) < (zzt _)
setup   A rules  A driver grounded B rules  B driver collect  tests
```

Within a phase, the spawned rule tag (`a0`/`c0`) deliberately sorts before
the driver tag (`az`/`cz`) so each level's rule instances run before the
driver advances to the next level — the same trick the Counter Machine
uses (`(JZ n)` sorts before `(clocked n)`). The grounded execs sit at
`(b0 _)`: after every phase-A exec (so all `todo`/`sub` facts exist) and
before every phase-B sweep (so `expm1` and integer `d` facts are ready).

One trap this layout avoids: Peano numerals sort *deeper-first* under
shortlex (an expression outranks a symbol, so `(S Z)` outranks `Z`).
Ordering across levels therefore cannot rely on the level numeral inside
a tag; correctness here only needs "all of this level's rule execs before
the next driver", which the `a0 < az` symbol ordering provides.

## Two simplification implementations

Both eliminate the redundancy the derivative rules generate —
`(+ 0 e) -> e`, `(* 1 e) -> e`, `(* 0 e) -> 0`, `(* e (neg 1)) -> (neg e)`,
`(/ e 1) -> e`, `(pow e 1) -> e`, `(pow e 0) -> 1`, `(neg 0) -> 0`, and
integer `+ - *` folded by Rust — turning e.g. the derivative of `(+ (* x x) (* 2 x))`
from `(+ (+ (* 1 x) (* x 1)) (+ (* 0 x) (* 2 1)))` into `(+ (+ x x) 2)`.
Both must pass `test_simplify.mm2` with identical answers, and they
produce byte-identical result sets on `example.mm2`.

Each needs an else-branch — "no special case applied, keep the built
form" — which MM2 cannot express as negation. Both implement it by
**sequencing plus deletion**: special-case rules fire first and delete
the candidate fact they reduce; a later default rule converts every
surviving candidate verbatim. Whatever the special cases deleted, the
default never sees.

**`simplify.mm2` (post-process).** A structural sibling of the engine,
running after `(zz out)` in the 3-character `(zz? _)` tag range: seed
each result's derivative into its own `stodo`/`ssub` namespace,
decompose top-down, ground integer leaves with an i64 parse round-trip,
then rebuild bottom-up one sweep per recorded `slevel`. Assembly writes
a candidate `(sraw E (op su sv))` from simplified children; parents
match only the finished `(s E S)` facts, never `sraw`, so partially
reduced forms cannot leak upward. Because children are clean before a
parent is assembled, redundancy is always at the candidate's root where
one cleanup pass can see it.

**`diff_engine_fused.mm2` (fused).** The plain engine's combination
rules build multi-level trees in one template (the product rule writes
`(+ (* du v) (* u dv))` at once), so nested redundancy appears where no
root-level cleanup can reach it. The fused engine therefore builds every
derivative one level at a time through smart-constructor facts:
`(mkq E)` requests the simplified form of a single node whose children
are already simplified, and `(mkd E S)` answers it, keyed by the
request. A derivative is a chain of requests (product: `du*v`, `u*dv`,
then their sum; quotient and power chain three deep), so the combination
driver runs four construction rounds per depth level — logic, folds,
special cases, default per round — instead of the plain engine's one
sweep. Semantic difference from the post-process pair: input subterms
copied verbatim into a derivative (the `u` inside `(* (cos u) du)`) are
not simplified; the post-process pass simplifies everything it walks.

## Limitations / possible extensions

- Remaining redundancy is what the rule set does not cover: no
  like-term collection (`(+ x x)` stays, rather than `(* 2 x)`), no
  `(neg (neg e)) -> e`, no trigonometric identities. Each is one more
  special-case rule in whichever implementation. When a new rule's
  pattern overlaps an existing one with a different answer, the rule
  name's lexicographic position decides the winner (first match deletes
  the candidate): the `muln*` neg-collapse rules sort after `mul0*`/
  `mul1*`, so `(* 0 (neg 1))` folds to `0`, not `(neg 0)`.
- `(pow u n)` requires an i64 literal exponent. A symbolic exponent gets
  no `expm1` fact, so the subterm silently produces no derivative
  (`d(u^v) = u^v·(v·du/u + ln(u)·dv)` would need the general rule).
- Non-integer leaves must still be declared via `(dvar _)`/`(const _)`:
  MM2 patterns cannot test "is a symbol" and the engine does not use
  negation, so an undeclared symbolic leaf never gets a base `(d leaf _)`
  fact and the affected root produces no result. Integer leaves are
  exempt because the grounded phase identifies them by parsing.
