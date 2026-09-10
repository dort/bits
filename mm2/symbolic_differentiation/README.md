# Symbolic differentiation in MM2

Computes exact derivatives of expression trees by forward rewriting in the
MORK space. Integer handling is grounded: integer leaves are recognized and
the power rule's exponent decrement is computed by Rust i64 functions via
the `pure` sink (`kernel/src/pure.rs`), not by Peano encodings. The test
file additionally uses the `+`/`-` sinks for set difference.

## Files

- `diff_engine.mm2` — the engine (rules only, no data)
- `example.mm2` — sample inputs
- `test.mm2` — test suite in the wiki's `MISTAKE`/`CORRECT` style
- `run.sh` — concatenates an input file with the engine and runs `mork run`

## Usage

```
./run.sh                # example.mm2: prints (result EXPR D) facts
./run.sh test.mm2       # expect one (CORRECT EXPR) per case, no MISTAKE
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

## Limitations / possible extensions

- Output is unsimplified: `(* 1 x)`, `(+ ... 0)` etc. remain. A
  simplification pass fits the same decompose/rebuild architecture and
  could be chained after `(zz out)`; the grounded phase's constant
  detection would let it fold integer arithmetic with `sum_i64` and
  `product_i64`.
- `(pow u n)` requires an i64 literal exponent. A symbolic exponent gets
  no `expm1` fact, so the subterm silently produces no derivative
  (`d(u^v) = u^v·(v·du/u + ln(u)·dv)` would need the general rule).
- Non-integer leaves must still be declared via `(dvar _)`/`(const _)`:
  MM2 patterns cannot test "is a symbol" and the engine does not use
  negation, so an undeclared symbolic leaf never gets a base `(d leaf _)`
  fact and the affected root produces no result. Integer leaves are
  exempt because the grounded phase identifies them by parsing.
