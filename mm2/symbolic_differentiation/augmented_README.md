# Symbolic differentiation in MM2, explained from first principles

This document explains everything in this folder assuming no background
knowledge: not what a derivative is, not what "symbolic" computation
means, not how the MORK/MM2 rewriting system works, and not what a
"clean representation" is. The short `README.md` next to this file
covers the same material compactly for readers who already know these
things.

Every fact and output shown below is real: it was produced by running
the code in this folder with the `mork` binary.

---

## Part 1 — What is differentiation?

### Change, and rate of change

Many quantities in the world change over time or in response to
something else: the position of a car, the temperature of a cup of
coffee, the height of a ball thrown in the air. Often the interesting
question is not "what is the value?" but "how fast is the value changing
right now?"

A car's speedometer answers exactly that question. The odometer tells
you *position* (how far you have driven in total); the speedometer tells
you the *rate of change* of position (kilometers per hour, at this
instant). Differentiation is the mathematical operation that turns the
first kind of description into the second: given a rule for a quantity,
it produces the rule for that quantity's rate of change.

### Functions as formulas

A *function* is a rule that turns an input number into an output number.
We write the input as a letter, called a variable. For example, with the
variable `x`:

- the function `x * x` (written x² in ordinary notation) turns 3 into 9,
  turns 4 into 16, and so on;
- the function `2 * x` turns 3 into 6, turns 4 into 8.

The *derivative* of a function is a second function that answers, for
any input, "if I nudge the input up by a tiny amount, how many times
that amount does the output move?" For `2 * x` the answer is always 2.
For `x * x` it depends on where you are: near `x = 3` the answer is
about 6, near `x = 4` about 8; the derivative of `x * x` is the function
`2 * x`, which captures all of these at once.

### What "symbolic" means

**Numeric differentiation** picks a concrete input, nudges it, and
divides output change by input change — one approximate number, valid at
one point. **Symbolic differentiation** — this project — manipulates the
*formula itself* by exact algebraic rules and produces a new formula,
valid everywhere, with no approximation. It is what a calculus student
does on paper and what computer algebra systems such as Mathematica or
SymPy do inside.

---

## Part 2 — The rules of differentiation

Differentiation is governed by a small, closed, *recursive* rule set:
the derivative of a big expression is assembled from the derivatives of
its parts. No insight required, only bookkeeping — which is why a
machine can do it.

Throughout, `u` and `v` are subexpressions, `du` and `dv` their (already
computed) derivatives, and all derivatives are with respect to the
single chosen variable. The expressions in the table are written in the
constructor syntax Part 3 introduces.

| expression | its derivative |
|---|---|
| `(var x)` — the variable itself | `(num 1)` |
| `(num n)`, `(cst c)` — any constant | `(num 0)` |
| `(add u v)` | `(add du dv)` |
| `(sub u v)` | `(sub du dv)` |
| `(mul u v)` | `(add (mul du v) (mul u dv))` |
| `(div u v)` | `(div (sub (mul du v) (mul u dv)) (mul v v))` |
| `(pow u (num n))` — uⁿ | `(mul (mul (num n) (pow u (num n-1))) du)` |
| `(neg u)` — negation | `(neg du)` |
| `(sin u)` | `(mul (cos u) du)` |
| `(cos u)` | `(neg (mul (sin u) du))` |
| `(exp u)` — eᵘ | `(mul (exp u) du)` |
| `(ln u)` — natural log | `(div du u)` |

Intuitions for the three non-obvious ones: the **product rule** is a
rectangle with sides `u` and `v` — nudge the input and the area gains a
strip `du·v` along one edge and a strip `u·dv` along the other. The
**chain rule** (the `du` factor in the sin/cos/exp/ln rows) is two gears
in series — the inner expression responds to the input at rate `du`, the
outer function responds to the inner at its own rate, and rates in
series multiply. The **power rule** is the one place a rule must
*compute with numbers* rather than only rearrange formulas: it needs the
new exponent n−1, and Part 5 shows that subtraction delegated to a real
Rust function.

---

## Part 3 — The typed AST, and clean versus defaulty representations

### Expressions as trees

Every formula is a tree. `x * (x + 2)` has a multiplication at the root,
`x` as one child, and an addition (of `x` and `2`) as the other. A
**leaf** is a node with nothing under it; a **subterm** is any node with
everything under it; **depth** counts steps down from the root;
**height** counts steps up from the leaves.

### How the tree is written: one constructor per case

This project writes that tree as

```
(mul (var x) (add (var x) (num 2)))
```

Note that even the leaves are wrapped: the variable is `(var x)`, the
literal is `(num 2)`, and a symbolic parameter like `a` would be
`(cst a)`. This is the single most important design decision in the
folder, and it comes from logic-programming practice.

**The defaulty alternative.** An earlier version of this engine wrote
leaves as bare symbols: `(* x (+ x 2))`. That looks lighter, but in a
system whose only test is pattern matching it is a trap. A pattern
variable `$e` matches *everything* — a bare `x`, a bare `2`, a whole
compound — so no pattern can ask "is this a leaf?", "is this a number?",
"is this the variable?". Prolog practitioners call such representations
**defaulty**: the cases cannot be told apart by unification, so
programs need default clauses ("otherwise, it must be a …") and ad-hoc
tests. The old engine paid the price in two ways: it required the user
to declare every leaf (`(dvar x)`, `(const a)`), and it detected integer
literals by pushing *every* subterm through Rust's integer parser and
relying on parse failure to filter — classification by error.

**The clean representation.** Wrap every case in its own constructor and
the cases become distinguishable by pattern alone: `(num $n)` matches
exactly the integer literals, `(var $x)` exactly the variable, `(cst
$c)` exactly the symbolic constants, `(add $u $v)` exactly the sums. All
dispatch is unification; no defaults, no declarations, no parser
tricks. The base-case rules of the differentiator become three one-line
patterns, and the input shrinks to just the expressions themselves:

```
(diff (mul (var x) (add (var x) (num 2))))
```

One semantic note: `(var _)` means *the* variable of differentiation —
the engine differentiates with respect to it, whatever its name. A
second independent variable in the same expression is, from the
derivative's point of view, a constant: write it `(cst y)`.

---

## Part 4 — The machine: MORK and MM2

[MORK](https://github.com/trueagi-io/MORK) maintains a **space**: a set
of S-expressions, called facts. MM2 is the little language it executes;
an MM2 program is itself a set of facts loaded into the space, some of
which are instructions. Running the program transforms the space, and
the final space is the output.

### Facts, patterns, and `exec`

A **pattern** is an S-expression with `$`-prefixed variables; `(d $u
$du)` matches `(d (var x) (num 1))` with `$u = (var x)`, `$du = (num
1)`. All computation happens through facts of the shape

```
(exec TAG (, PATTERN1 PATTERN2 ...) (, TEMPLATE1 TEMPLATE2 ...))
```

— "find every simultaneous match of all the patterns, and for each
match write the templates into the space." Three properties shape
everything in this folder:

1. **An `exec` fires once and is consumed.** There is no built-in loop;
   to iterate, an `exec` writes a new `exec` into the space.
2. **Writes only add facts.** The space is a set — rewriting an
   existing fact changes nothing — so computation is *saturation*:
   facts accumulate until no rule produces anything new. (Templates in
   the `O` form invoke *sinks*, which can also remove facts or run Rust
   code while writing; this project uses removal only to swap final
   `result` facts, and Rust calls for genuine arithmetic.)
3. **There is no negation.** A pattern can demand a fact exists, never
   that one is absent. "Has anything changed?", "is there no rule for
   this?", "are these two things different?" are all inexpressible as
   plain patterns — Parts 5 and 7 show the three different lawful ways
   this project gets each of those effects.

### Which `exec` runs next: priority

Among pending `exec`s, MORK runs the one whose TAG sorts first:
expression tags beat symbol tags, fewer elements beat more, then
elements compare left to right — and **symbols compare by length first,
then alphabetically**. That last clause matters twice in this project:
it lets a 1-character tag element sort before every 2-character one
(sequencing the phases), and it once caused a real bug (Part 6) when
rule names of mixed lengths reordered a dependency chain.

Priority is the *only* sequencing mechanism in MM2; this project's whole
phase structure lives in the spelling of its tags:

```
(0 _) < (a0 _) < (az _) < (b0 _) < (c0 _) < (cz _) < (zz _) < (zza _).. < (zzt _)
setup   A rules  A drv    bases    B rules  B drv    collect  simplifier   tests
```

### Rules as data

A pattern/template pair stored as an ordinary fact —

```
((brule add) (, (sub (add $u $v)) (d $u $du) (d $v $dv))
             (, (d (add $u $v) (add $du $dv))))
```

— never fires on its own, but a driver `exec` can match it with
`((brule $k) $bp $bt)`, capturing pattern and template wholesale, and
write `(exec SOMETAG $bp $bt)`: the stored rule becomes a live
instruction. Drivers do this once per round with round-specific tags,
which is how a fixed rule set gets applied repeatedly. (Why not one
self-recreating loop per rule? A loop only continues by re-creating
itself, so it dies permanently on the first round where its own pattern
happens not to match; the driver's continuation condition is
rule-independent.)

One more pattern-language fact this project leans on: a variable may sit
in *operator position*. `(val ($f $a $b))` matches any 3-element
expression and binds `$f` to its head symbol — one rule classifies every
binary constructor at once.

---

## Part 5 — The differentiator, step by step

The rule table of Part 2 is recursive, but MM2 has no call stack. The
engine replaces the recursion with two saturation phases over explicit
facts: Phase A walks the tree top-down and records the work; Phase B
walks bottom-up and assembles the answers. Everything below follows one
real run of the input

```
(diff (mul (var x) (add (var x) (num 2))))
```

### Setup and Phase A: discovering the subterms

Setup (tag `(0 root)`) seeds `(todo Z EXPR)` — "the root expression sits
at depth zero", with depth as a Peano numeral (`Z`, `(S Z)`,
`(S (S Z))`, … — numbers as nested structure, countable by pattern
matching alone).

Phase A's driver (tag `(az Z)`) is a self-recreating loop: it matches
itself (to copy its own body forward), the fact `(todo $l $_)` ("any
work at the current depth?"), and every stored decomposition rule
`((arule $k $l) ...)`, which it instantiates at the current level. The
decomposition rule for `mul`:

```
((arule mul $l) (, (todo $l (mul $u $v)))
                (, (todo (S $l) $u) (todo (S $l) $v) (sub (mul $u $v))))
```

On our example this unfolds as: depth `Z` decomposes the `mul`, depth
`(S Z)` decomposes the `add` (the `(var x)` todo matches no rule —
leaves have no children), depth `(S (S Z))` holds only leaves, and at
depth `(S (S (S Z)))` no todo exists, so the driver's pattern fails and
the loop simply fails to perpetuate itself — termination without ever
saying "stop". Left behind, from the actual run:

```
(todo Z (mul (var x) (add (var x) (num 2))))
(todo (S Z) (var x))          (todo (S Z) (add (var x) (num 2)))
(todo (S (S Z)) (var x))      (todo (S (S Z)) (num 2))
(sub (mul (var x) (add (var x) (num 2))))
(sub (add (var x) (num 2)))
(level Z)   (level (S Z))   (level (S (S Z)))
```

The `(level l)` facts — one per depth — are the bookkeeping Phase B's
termination rests on.

### Base derivatives: clean dispatch at the leaves

Three one-shot execs (tags `(b0 ...)`) fire next, each a pure pattern
dispatch on a leaf constructor:

```
(exec (b0 num) (, (todo $l (num $n))) (, (d (num $n) (num 0))))
(exec (b0 var) (, (todo $l (var $x))) (, (d (var $x) (num 1))))
(exec (b0 cst) (, (todo $l (cst $c))) (, (d (cst $c) (num 0))))
```

Read `(d E DE)` as "the derivative of E is DE". This is the clean
representation earning its keep: the defaulty predecessor needed user
declarations plus a Rust parse of every todo to produce these same
facts. In our run they write `(d (var x) (num 1))` and
`(d (num 2) (num 0))`.

One `(b0 ...)` exec does call Rust — the power rule's exponent
decrement, `(expm1 (num n) (num n-1))` via the `pure` sink:

```
(exec (b0 pow)
  (, (sub (pow $u (num $n))))
  (O (pure (expm1 (num $n) (num $m)) $m
           (i64_to_string (sub_i64 (i64_from_string $n) (i64_one))))))
```

The `pure` sink evaluates a tree of Rust functions
(`kernel/src/pure.rs`) per match and writes the template with the result
bound to the given variable. Unlike the old engine, the call is
*computation, not classification*: the `(num $n)` pattern already
guarantees the argument parses.

### Phase B: bottom-up combination

Combination rules are stored as data (the `brule` shown in Part 4, one
per operator, transcribing Part 2's table). A rule can only fire once
its children's derivatives exist, so one application of all rules — a
**sweep** — completes exactly the nodes whose children are done, and
sweeps must repeat once per tree level. Here MM2's missing negation
bites: "sweep until nothing new appears" is inexpressible. The engine
instead runs a number of sweeps *known in advance to suffice*: its
driver (tag `(cz Z)`) runs **one sweep per `(level l)` fact**, and
depth + 1 sweeps always cover a tree of that depth. In our run:

- **Sweep 1:** the `mul` rule fails (no derivative for the `add` yet);
  the `add` rule finds `(d (var x) (num 1))` and `(d (num 2) (num 0))`
  and writes `(d (add (var x) (num 2)) (add (num 1) (num 0)))`.
- **Sweep 2:** the `mul` rule now finds both children and writes the
  product rule verbatim.
- **Sweep 3:** nothing new — a wasted sweep, harmless in a set.

Collection (tag `(zz out)`) joins each `(diff $e)` with `(d $e $de)`:

```
(result (mul (var x) (add (var x) (num 2)))
        (add (mul (num 1) (add (var x) (num 2)))
             (mul (var x) (add (num 1) (num 0)))))
```

Correct — `1·(x+2) + x·(1+0)` — and verbose. Part 7 is about making it
say `(add (add (var x) (num 2)) (var x))`… almost: read on.

---

## Part 6 — Why the scheduling is the way it is

Three constraints, each learned against the actual binary:

**Rules live in data, drivers carry the loops.** Covered in Part 4: a
self-recreating per-rule loop dies permanently on its first quiet round.

**Spawned-rule tags sort before their driver's next copy.** Within one
Phase A round, the freshly instantiated rules (tags `(a0 ...)`) must run
before the driver's next copy (tag `(az (S l))`) checks for work at the
next depth — the rules are what create that work. `a0 < az` at equal
length does it, and likewise `c0 < cz`, `zzb < zzc`, `zze < zzf < zzi`.

**Rule names in a dependency chain must share one length.** Instances of
stored rules execute in rule-name order inside a sweep, and symbols
compare length-first. The simplifier's classification chain (Part 7)
computes `val`, then `ctor`, then `isexpr`, then `def` facts, each stage
reading the previous one's output *within the same sweep* — which works
precisely because the names `aval < cbin < iexp < jdfe < nzzz < znee`
are all 4 characters and in lexicographic chain order. The first build
of this refactor named two stages `iex` and `zne`; being 3 characters,
they sorted *before* the 4-character stages they depended on, every
stage slipped one sweep, deep expressions ran out of sweep budget, and
exactly one result — the deepest example — silently vanished. Symptom to
remember: partial output with no error usually means a starved sweep
budget.

Also inherited from the first version: **Peano numerals sort
deepest-first** (an expression outranks a symbol, so `(S Z)` outranks
`Z`), so a level numeral inside a tag serves only to make the tag
distinct — never to order rounds. Ordering always comes from drivers
spawning one round at a time.

---

## Part 7 — Simplification without defaults

### The problem, and why it is the hard part

The derivative of `x·(x+2)` came out as `1·(x+2) + x·(1+0)`. Cleaning it
means rewriting `(mul (num 1) e) -> e`, `(add e (num 0)) -> e`, folding
`(add (num 1) (num 0)) -> (num 1)`, and so on, *anywhere inside* the
tree — but an MM2 pattern matches whole facts only. So both
implementations decompose the tree and rebuild it bottom-up, running
each node through a **smart constructor**: given an operator and
already-simplified children, produce the simplified node.

A smart constructor has special cases and a default: "if a child is
`(num 0)`, drop it; if both are numbers, fold; … *otherwise keep the
node as built*." That "otherwise" is the complement of the special
cases — negation again. The previous version implemented it defaultily:
special-case rules *deleted* the candidate fact they reduced, and a
later catch-all converted the survivors; dispatch by execution order and
deletion. It worked, but it reintroduced through the back door exactly
what the defaulty leaf encoding had done: cases distinguished by
anything but patterns.

### Reify the tests, enumerate the complement

The clean version makes the complement *patternable* by classifying
every simplified value into reified dispatch facts — written by rules,
consumed by rules:

```
(val V)        V occurs as a simplified value
(ctor V c)     V's constructor tag ((ctor (num 3) num), (ctor (add ..) add));
               one variable-head rule covers all binary constructors
(isexpr V)     V's tag is anything but num — membership in the data
               facts (exprtag add), (exprtag var), ...
(def V)        V is num or isexpr, i.e. not the error value UNDEFINED
(zn V NZ|Z)    for V = (num n): is n nonzero? — computed by Rust: the
(on V NO|O)      pure sink's ifnz on n, n−1, n+1; likewise "not one"
(mn V NM|M)      and "not minus-one"
(vne A B)      A and B are structurally different — from MORK's !=
               source, the complement of unification itself
```

Now every constructor's rule set is a **total, disjoint-or-agreeing case
analysis**. Multiplication's left operand, for instance, is exactly one
of: `(num 0)`, `(num 1)`, `(num -1)` (three literal patterns), a number
outside those (`zn`/`on`/`mn` all negative), an `isexpr`, or
`UNDEFINED` — and there is one rule per case. Where two rules do overlap
— `(mul (num 0) (num 5))` matches both the zero rule and the
number-number fold — their answers *agree* (both say `(num 0)`), and
agreeing duplicates collapse in a set. Nothing is deleted, no rule is a
default, and the whole simplifier is monotonic saturation. The rules for
"which tags may appear under a built `neg`" are likewise data —
`(negtag add)`, `(negtag var)`, … — set membership as facts, not code.

Two of the reified facts deserve a closer look:

- **`vne` — disequality.** The identity rules `(sub $x $x) -> (num 0)`
  and `(div $x $x) -> (num 1)` get *equality* free: repeating `$x` in a
  pattern matches only when both operands unify. Their build-rule
  complements need *dis*equality, which no pattern can express — that is
  what MORK's `!=` source is for: `(I (!= (val $x) (val $y)))` matches
  every pair of values that differ, and one rule turns those into
  `(vne A B)` facts the build rules join against.
- **`zn`/`on`/`mn` — grounded number tests.** "n is nonzero" is not a
  structural property of the symbol `n`, so it is delegated to Rust:
  `ifnz` evaluates a 64-bit integer and returns one of two symbols,
  which lands in the space as a fact. The test becomes data; dispatch on
  it is again just a pattern.

### What the simplifier does with all this

What it computes: `(add (num 0) e) -> e` and mirror, `(sub e (num 0))
-> e`, `(sub e e) -> (num 0)`, `(mul (num 0) e) -> (num 0)`,
`(mul (num 1) e) -> e`, `(mul (num -1) e) -> (neg e)` (all with
mirrors), `(div (num 0) e) -> (num 0)`, `(div e (num 1)) -> e`,
`(div e e) -> (num 1)`, `(pow e (num 1)) -> e`, `(pow e (num 0)) ->
(num 1)`, `(neg (num n)) -> (num -n)`, `(neg (neg e)) -> e`, and integer
`add`/`sub`/`mul` folded by Rust. Division by zero is not an identity
but an error value: `(div e (num 0)) -> UNDEFINED` — `(div (num 0)
(num 0))` included — and UNDEFINED is *contagious*: every constructor
has a rule collapsing a node with an UNDEFINED child to UNDEFINED, and
every other rule requires its operands `def` or `isexpr`, so the error
can never be swallowed by, say, the zero rule.

On the Part 5 example the simplified result is:

```
(result (add (mul (var x) (var x)) (mul (num 2) (var x)))
        (add (add (var x) (var x)) (num 2)))
```

(that is the `example.mm2` case; d(x² + 2x) = 2x + 2, kept as
`(x + x) + 2` since like-term collection is out of scope).

### The two implementations

**`simplify.mm2` — post-process.** A structural sibling of the
differentiator, running after collection in the 3-character `(zz? _)`
tag range: seed each result's derivative as its own decomposition
problem (`stodo`/`ssub` namespace), decompose top-down recording
`(slevel l)` facts, emit `(s leaf leaf)` base cases by constructor
dispatch, then rebuild bottom-up — per recorded level, one *classify*
sweep (`zze`, the chain of Part 6) and one *construct* sweep (`zzf`, the
case analysis). `(s E S)` means "E simplifies to S". Because children
are clean before a parent is assembled, redundancy is always at the root
of the node being built, where the case analysis can see it — that is
why one bottom-up pass fully simplifies. Final step: each `(result E D)`
is swapped for `(result E S)` through a staging fact.

**`diff_engine_fused.mm2` — fused.** A standalone engine that never
writes an unsimplified derivative. It cannot just reuse the plain
engine's combination rules — they build multi-level trees in one
template (the product rule writes `(add (mul du v) (mul u dv))` at
once), so redundancy like `(mul (num 1) v)` appears *nested* where no
root-level case analysis reaches. Instead every derivative is built one
node at a time through request/response facts: `(mkq E)` asks for the
simplified form of a single node whose children are already simplified
values, `(mkd E S)` answers, keyed by the request, resolved by the same
total case analysis (classification is triggered by whatever appears as
a request argument). Requests persist — nothing deletes them; re-issued
requests re-resolve to the same answers. A derivative is a chain of up
to three requests plus a completion (quotient: `du·v`, `u·dv`, `v·v`,
then the difference, then the division), so the driver runs **four**
logic/classify/resolve rounds per depth level, sequenced by instance
tags `(c0 ((l r ph) k))` that sort round-major, then phase-major.

The two implementations differ in one visible way: the post-process pass
simplifies *everything* it walks, including copies of input subterms
inside derivatives (the `u` in `(mul (cos u) du)`); the fused engine
keeps those verbatim. On inputs with no redundancy of their own — all
the shipped examples and tests — their outputs are byte-identical, and
that identity is checked.

---

## Part 8 — How the tests work

`test.mm2` (plain engine, unsimplified expectations) and
`test_simplify.mm2` (either simplifying configuration) follow the wiki
page "MM2 Example: Testing Your Code". Each case supplies input and
expected answer:

```
(diff (pow (var x) (num 3)))
(solution (pow (var x) (num 3)) (mul (num 3) (pow (var x) (num 2))))
```

Test `exec`s (tags `(zzt _)`, sorting after everything else) build the
*symmetric difference* between produced `result` facts and expected
`solution` facts: copy both sets into `(MISTAKE ...)` facts, remove
every fact present in both (the one legitimate use of the removal sink),
then write `(CORRECT e)` per case and remove it again wherever a
`MISTAKE` survives. A perfect run ends with one `CORRECT` per case and
no `MISTAKE`s; a failure leaves both the produced and the expected fact
visible.

The simplified suite includes the cases that exercise each identity: the
double collapse in d(cos(−x)) = sin(−x), the same-operand cancellations
d(x/x) = 0 and d(ln(eˣ)) = 1, and division by zero surfacing as
UNDEFINED both directly and through an enclosing sum.

---

## Part 9 — Running it yourself

From this folder (the `mork` binary must be built; see the wiki's
"Getting started" page):

```
./run.sh                                  # examples, unsimplified
./run.sh test.mm2                         # unsimplified test suite
./run.sh example.mm2 simplify.mm2         # simplified (post-process)
./run.sh test_simplify.mm2 simplify.mm2   # simplified test suite
ENGINE=diff_engine_fused.mm2 ./run.sh     # simplified (fused engine)
ENGINE=diff_engine_fused.mm2 ./run.sh test_simplify.mm2
./run.sh yourfile.mm2                     # your own input
```

A minimal input file — note there are no declarations:

```
(diff (mul (num 3) (sin (var x))))
```

Things worth trying to deepen the picture:

- Add an expression to `example.mm2` and predict, before running, how
  many `(level ...)` facts Phase A records and in which sweep of
  Phase B the root's `d` fact appears.
- Add an identity both implementations lack — say `(ln (num 1)) ->
  (num 0)` — as one rule in `simplify.mm2`'s `zzf` store and one in
  `diff_engine_fused.mm2`'s `p3` store. The discipline to follow: give
  the new rule a pattern disjoint from (or agreeing with) `lnb`'s, and
  narrow `lnb` so the two stay that way — in a clean rule set, adding a
  special case always means subtracting it from the build case.
- Break the name-length rule on purpose: rename `simplify.mm2`'s
  `iexp` rule to `iex` and watch the deepest example's result vanish
  with no error (Part 6 explains the mechanism).
- Run with `--steps N` (`mork run file --steps N`) for increasing N and
  diff the outputs to watch the space evolve one `exec` at a time; the
  script in `bits/bash_diff_util/mork_step_diff.sh` automates this.
