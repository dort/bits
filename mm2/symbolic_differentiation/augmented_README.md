# Symbolic differentiation in MM2, explained from first principles

This document explains everything in this folder assuming no background
knowledge: not what a derivative is, not what "symbolic" computation means,
and not how the MORK/MM2 rewriting system works. The short `README.md` next
to this file covers the same material compactly for readers who already
know these things.

Every fact and output shown below is real: it was produced by running the
code in this folder with the `mork` binary.

---

## Part 1 — What is differentiation?

### Change, and rate of change

Many quantities in the world change over time or in response to something
else: the position of a car, the temperature of a cup of coffee, the
height of a ball thrown in the air. Often the interesting question is not
"what is the value?" but "how fast is the value changing right now?"

A car's speedometer answers exactly that question. The odometer tells you
*position* (how far you have driven in total); the speedometer tells you
the *rate of change* of position (kilometers per hour, at this instant).
Differentiation is the mathematical operation that turns the first kind of
description into the second: given a rule for a quantity, it produces the
rule for that quantity's rate of change.

### Functions as formulas

A *function* is a rule that turns an input number into an output number.
We write the input as a letter, called a variable. For example, with the
variable `x`:

- the function `x * x` (written x² in ordinary notation) turns 3 into 9,
  turns 4 into 16, and so on;
- the function `2 * x` turns 3 into 6, turns 4 into 8.

The *derivative* of a function is a second function that answers, for any
input, "if I nudge the input up by a tiny amount, how many times that
amount does the output move?" For `2 * x` the answer is always 2: increase
`x` by any small step and the output increases by exactly twice that step.
For `x * x` the answer depends on where you are: near `x = 3`, nudging `x`
up by a tiny step raises `x * x` by about 6 times that step (9 → a bit
more than 9), and near `x = 4` by about 8 times. The derivative of
`x * x` is the function `2 * x`, which captures all of these at once.

The traditional notation for "the derivative of E with respect to x" is
dE/dx. This code writes the same idea as a fact `(d E D)`, read as "the
derivative of expression E is expression D."

### What "symbolic" means

There are two very different ways a computer can differentiate.

**Numerically:** pick a concrete input, say `x = 3`, nudge it a little,
say to `3.001`, evaluate the function at both points, and divide the
change in output by the change in input. This yields one approximate
*number* (here roughly 6.001), valid only at that input, with rounding
error.

**Symbolically:** manipulate the *formula itself*, following exact
algebraic rules, and produce a new formula. Input: the expression
`x * x`. Output: the expression `1*x + x*1` (which a human would tidy to
`2*x`). No numbers are plugged in, nothing is approximate, and the answer
is valid for every input at once.

This project does the second kind. It is the same kind of manipulation a
calculus student does with pencil and paper, and the same kind performed
inside computer algebra systems such as Mathematica or SymPy.

---

## Part 2 — The rules of differentiation

The reason differentiation can be done by a machine at all is that it is
governed by a small, closed set of rules, and the rules are *recursive*:
the derivative of a big expression is assembled out of the derivatives of
its parts. You never need insight, only bookkeeping.

Throughout, `u` and `v` stand for any two subexpressions, `du` stands for
the (already computed) derivative of `u`, and `dv` for the derivative of
`v`. All derivatives are taken with respect to the single chosen variable
`x`.

### The two base cases

- **The variable itself:** the derivative of `x` is `1`. If you nudge `x`
  by a step, the quantity "x" moves by exactly that step — a ratio of 1.
- **A constant:** the derivative of any constant (like `2`, or a named
  parameter like `a` that does not depend on `x`) is `0`. Nudging `x`
  does not move it at all.

### The sum rule

The derivative of `u + v` is `du + dv`.

Intuition: if two quantities are added, their rates of change add. If
your salary grows by 3 per year and your side income by 2 per year, your
total income grows by 5 per year.

### The product rule

The derivative of `u * v` is `du*v + u*dv`.

Intuition: picture a rectangle whose width is `u` and height is `v`; the
product is its area. When `x` is nudged, the width grows a little (by
`du` times the nudge) and the height grows a little (by `dv` times the
nudge). The area gains a thin vertical strip of size `du * v` and a thin
horizontal strip of size `u * dv`. (It also gains a tiny corner square,
but that corner is a small-times-small quantity and vanishes in the limit
of tiny nudges.) Hence the two terms.

### The chain rule

For a function applied to an inner expression — say `sin(u)` where `u` is
itself built from `x` — the derivative is the derivative of the outer
function *evaluated at* `u`, multiplied by `du`.

Intuition: two gears in series. The inner expression `u` responds to `x`
at some rate (`du`), and the outer function responds to `u` at its own
rate; the overall response is the product of the two rates.

### The full rule table used by this engine

| expression | its derivative | rule name in the code |
|---|---|---|
| `x` (the diff variable) | `1` | base case |
| any declared constant `c` | `0` | base case |
| `(+ u v)` | `(+ du dv)` | `sum` |
| `(- u v)` | `(- du dv)` | `dif` |
| `(* u v)` | `(+ (* du v) (* u dv))` | `prod` |
| `(/ u v)` | `(/ (- (* du v) (* u dv)) (* v v))` | `quot` |
| `(neg u)` (negation, −u) | `(neg du)` | `neg` |
| `(sin u)` | `(* (cos u) du)` | `sin` |
| `(cos u)` | `(neg (* (sin u) du))` | `cos` |
| `(exp u)` (eᵘ) | `(* (exp u) du)` | `exp` |
| `(ln u)` (natural logarithm) | `(/ du u)` | `ln` |

You do not need to understand *why* the sin/cos/exp/ln lines are what
they are (those are standard calculus facts); what matters for this
project is their *shape*: every line builds the answer for a whole
expression out of `u`, `v`, `du`, and `dv` — the parts and the parts'
derivatives. That shape is what the rewriting machinery below exploits.

---

## Part 3 — Expressions as trees

### S-expression notation

The code writes formulas in *prefix* notation with parentheses, called
S-expressions: the operator comes first, then its arguments. Ordinary
`x*(x+2)` becomes:

```
(* x (+ x 2))
```

Read inside-out: `(+ x 2)` is "x plus 2", and `(* x ...)` multiplies `x`
by that. This notation makes the structure of a formula completely
explicit — there are no precedence rules to remember, the nesting *is*
the structure.

### The tree view

Every S-expression is a tree. For `(* x (+ x 2))`:

```
        (*)            depth 0   (the root)
        /  \
      x     (+)        depth 1
            /  \
          x     2      depth 2   (leaves)
```

Vocabulary used throughout the rest of this document:

- a **leaf** is a name with nothing inside it: `x`, `2`, `a`;
- a **subterm** is any node of the tree together with everything under
  it — here the subterms are `(* x (+ x 2))`, `x`, `(+ x 2)`, and `2`;
- **depth** counts steps down from the root (root = depth 0);
- **height** counts steps up from the leaves (leaf = height 0). The
  height of the root equals the maximum depth of any leaf.

The differentiation rules of Part 2 consume this tree bottom-up: the
derivative at each node is built from the derivatives of the nodes
directly below it, and the leaves are where the base cases apply.

---

## Part 4 — The machine: MORK and MM2

[MORK](https://github.com/trueagi-io/MORK) is a Rust program that
maintains a **space**: a set of S-expressions, called facts. MM2
("Minimal MeTTa 2") is the little language it executes. An MM2 program
*is itself a set of facts* loaded into the space; some of those facts are
instructions, the rest are data. Running the program transforms the
space, and the final space is the output.

### Facts and patterns

A fact is any S-expression: `(parent Tom Bob)`, `(d x 1)`,
`(todo Z (* x (+ x 2)))`. Facts have no built-in meaning; `d` and `todo`
mean something only because the rules in this project treat them
consistently.

A **pattern** is an S-expression that may contain **variables**, written
with a `$` prefix. The pattern `(d $u $du)` matches the fact `(d x 1)`
with `$u = x` and `$du = 1`. One pattern can match many facts, and a
pattern with several conjoined parts must find bindings that satisfy all
parts at once.

### The `exec` instruction

All computation happens through facts of this shape:

```
(exec TAG (, PATTERN1 PATTERN2 ...) (, TEMPLATE1 TEMPLATE2 ...))
```

meaning: "find every way to match *all* the patterns simultaneously
against the space, and for each such match, write the templates (with the
matched variables filled in) into the space as new facts."

Three properties of `exec` shape the whole design of this project:

1. **It fires once and is consumed.** After an `exec` runs it is removed
   from the space, whether or not anything matched. There is no built-in
   loop. To iterate, an `exec` must *write a new `exec` into the space* —
   programs schedule their own future steps as data.
2. **Writes only add facts** (with a narrow exception: `O`-form sinks can
   remove facts; the test harness uses this, the engine itself does not).
   The space is a set, so writing a fact that already exists changes
   nothing. Computation is *saturation*: facts accumulate until no rule
   produces anything new.
3. **There is no negation.** A pattern can require that a fact *exists*;
   it cannot require that a fact is *absent*. In particular a program
   cannot directly ask "has anything changed since last round?" — a
   limitation that forces the termination trick described in Part 6.

### Which `exec` runs next: priority

When several `exec` facts are present, MORK repeatedly picks the one
whose TAG comes first in a "shortlex" ordering: an expression tag beats a
plain symbol tag; between expressions, fewer elements beats more; at
equal length, elements are compared left to right, and symbols compare by
length then alphabetically (so `0 < a0 < az < b0 < bz < zz` for the tags
this project uses — shorter first, then dictionary order).

Priority is therefore the *only* sequencing mechanism in MM2. This
project encodes its entire phase structure — setup, then decomposition,
then combination, then collection, then tests — purely in the spelling of
its tags.

### One more instrument: rules as data

Because `exec` bodies are just S-expressions, a program can store a
pattern/template pair as an ordinary fact, for example:

```
((brule sum)  (, (sub (+ $u $v)) (d $u $du) (d $v $dv))
              (, (d (+ $u $v) (+ $du $dv))))
```

This is *not* an `exec` — it never fires on its own. But another `exec`
(a "driver") can match it with the pattern `((brule $k) $bp $bt)`,
capturing the whole stored pattern into `$bp` and the whole stored
template into `$bt`, and then write `(exec SOMETAG $bp $bt)` — turning
the stored rule into a live instruction. The driver can do this
repeatedly with different tags, effectively calling the same rule once
per round. This reflective trick comes from the wiki's Counter Machine
example, and Part 6 explains why it is necessary here.

---

## Part 5 — The engine, step by step

### The problem to solve

The rule table of Part 2 is recursive: to differentiate `(* x (+ x 2))`
you first differentiate `x` and `(+ x 2)`, and to differentiate
`(+ x 2)` you first differentiate `x` and `2`. In an ordinary programming
language you would write a recursive function and the language's call
stack would manage the order of work. MM2 has no functions and no call
stack — only pattern matching over the space and the ability to add
facts.

The engine replaces the recursion with two sweeps over explicit facts:

- **Phase A** walks the tree *top-down*, recording every subterm as a
  fact. This is the "unwinding" half of the recursion: it discovers all
  the work.
- **Phase B** walks *bottom-up*, repeatedly applying the rule table to
  attach a derivative fact to every recorded subterm, starting from the
  leaves. This is the "returning" half: it assembles the answers.

Everything below follows one real run. Input:

```
(dvar x)                  ; differentiate with respect to x
(const 2)                 ; 2 is a constant leaf
(diff (* x (+ x 2)))      ; the expression to differentiate
```

### Setup (tags `(0 dvar)`, `(0 const)`, `(0 root)`)

Three `exec`s fire first (their tags start with `0`, which sorts before
everything else) and write the base facts:

```
(d x 1)                   ; base case: derivative of the variable is 1
(d 2 0)                   ; base case: derivative of a constant is 0
(todo Z (* x (+ x 2)))    ; "the root expression is at depth zero"
```

`Z` is zero written as a *Peano numeral*: numbers represented
structurally, with `Z` for zero and `(S n)` for "one more than n", so
depth two is `(S (S Z))`. Peano numerals let the program count using
nothing but pattern matching — `(S $l)` matches any number ≥ 1 and binds
`$l` to its predecessor — which fits a system whose only operation is
matching.

### Phase A: top-down decomposition

For each operator there is a stored decomposition rule. The one for `*`:

```
((arule prod $l) (, (todo $l (* $u $v)))
                 (, (todo (S $l) $u) (todo (S $l) $v) (sub (* $u $v))))
```

Read: "if some expression `(* $u $v)` is known to sit at depth `$l`, then
record its two children `$u` and `$v` at depth `(S $l)` (one deeper), and
record `(sub (* $u $v))` — this product is a subterm we will need a
derivative for."

A driver `exec` (tag `(az Z)`) matches three things at once: itself (so
it can copy its own body forward — the self-recreating loop from the
wiki's Reachability tutorial), the fact `(todo $l $_)` (is there any work
at the current depth? `$_` is a wildcard), and every stored
`((arule $k $l) ...)` fact. For each rule it writes a live
`(exec (a0 ($l $k)) ...)` instance, and it also writes one bookkeeping
fact `(level $l)` and a copy of itself for the next depth,
`(exec (az (S $l)) ...)`.

On our example this unfolds as:

- **depth `Z`:** `(todo Z (* x (+ x 2)))` exists, so the driver fires.
  The instantiated `prod` rule matches and writes
  `(todo (S Z) x)`, `(todo (S Z) (+ x 2))`, and `(sub (* x (+ x 2)))`.
  Bookkeeping: `(level Z)`.
- **depth `(S Z)`:** todos exist, driver fires again. The `sum` rule
  matches `(todo (S Z) (+ x 2))` and writes `(todo (S (S Z)) x)`,
  `(todo (S (S Z)) 2)`, and `(sub (+ x 2))`. The leaf todo
  `(todo (S Z) x)` matches no rule and produces nothing.
  Bookkeeping: `(level (S Z))`.
- **depth `(S (S Z))`:** todos exist (both are leaves), driver fires,
  all rules find nothing, only `(level (S (S Z)))` is written.
- **depth `(S (S (S Z)))`:** no `(todo (S (S (S Z))) ...)` fact exists,
  so the driver's pattern fails as a whole, it writes nothing — including
  no copy of itself — and the loop is over.

This is how the loop terminates *without* being able to say "stop": the
driver only continues by re-creating itself, and it only re-creates
itself while its pattern still matches. When the work runs out, the loop
simply fails to perpetuate itself.

Phase A has now left in the space: a `(sub E)` fact for every compound
subterm, and `(level ...)` facts counting the depths — here three of
them: `Z`, `(S Z)`, `(S (S Z))`. Both are consumed by Phase B.

### Phase B: bottom-up combination

For each operator there is a stored combination rule — the rule table of
Part 2 translated literally. Two of them:

```
((brule sum)  (, (sub (+ $u $v)) (d $u $du) (d $v $dv))
              (, (d (+ $u $v) (+ $du $dv))))
((brule prod) (, (sub (* $u $v)) (d $u $du) (d $v $dv))
              (, (d (* $u $v) (+ (* $du $v) (* $u $dv)))))
```

Read the first: "if `(+ $u $v)` is a needed subterm, and derivatives for
both `$u` and `$v` are already known, then the derivative of the sum is
the sum of the derivatives." The `(sub ...)` conjunct is essential: it
restricts the rule to subterms that actually occur in the input. Without
it the rule would combine *every* pair of known derivatives into
derivatives of sums nobody asked about, and the space would grow without
bound.

One application of all the rules is called a **sweep**. A single sweep is
not enough, because a rule can only fire when its children's derivatives
already exist. Watch the example:

- **Sweep 1:** the `prod` rule needs `(d (+ x 2) $dv)`, which does not
  exist yet, so it fails. The `sum` rule finds `(d x 1)` and `(d 2 0)`
  and writes `(d (+ x 2) (+ 1 0))`.
- **Sweep 2:** now the `prod` rule finds `(d x 1)` and
  `(d (+ x 2) (+ 1 0))` and writes
  `(d (* x (+ x 2)) (+ (* 1 (+ x 2)) (* x (+ 1 0))))`.

In general, after k sweeps, every subterm of height ≤ k has its
derivative: sweep 1 handles all nodes whose children are leaves, sweep 2
all nodes whose children were finished by sweep 1, and so on up the tree.
(This holds regardless of the order in which rules happen to run *within*
one sweep — a rule that fires too early in a sweep simply fails and
succeeds in a later sweep.)

### How many sweeps? The termination trick

Here MM2's lack of negation bites: the natural stopping rule — "sweep
until a sweep adds nothing new" — cannot be expressed, because no pattern
can detect the *absence* of change. The engine instead runs a number of
sweeps that is *known in advance to be enough*:

> Phase B's driver (tag `(bz Z)`) runs **exactly one sweep per
> `(level l)` fact** that Phase A recorded.

Phase A recorded one level per depth of the tree, so the count is
(maximum depth + 1). The root's height equals the maximum depth, and each
sweep completes at least one more height layer, so this count always
suffices — usually with a few wasted sweeps at the end that match nothing
and add nothing, which is harmless in a set-based space. The driver
terminates the same way Phase A's did: it advances by matching
`(level $l)` for the next `$l`, and past the last recorded level that
match fails and the driver does not re-create itself.

Like Phase A's driver, it launches each sweep by reflectively
instantiating the stored `brule` facts into live `exec`s tagged
`(b0 ($l $k))`.

### Collection (tag `(zz out)`)

One final `exec` joins each requested root with its derivative:

```
(exec (zz out) (, (diff $e) (d $e $de)) (, (result $e $de)))
```

Final answer in the space, exactly as produced by the run:

```
(result (* x (+ x 2)) (+ (* 1 (+ x 2)) (* x (+ 1 0))))
```

which is the product rule verbatim: `1·(x+2) + x·(1+0)`. A human would
simplify this to `2x + 2`; see Part 7 for why the engine does not.

---

## Part 6 — Why the scheduling is the way it is

This part explains three design decisions that look arbitrary until you
know the failure they avoid. All three were confirmed against the actual
`mork` binary, not just the wiki.

### Why rules are stored as data instead of being independent loops

The obvious design gives each operator its own self-recreating loop
(one for `+`, one for `*`, ...). It fails on expressions like
`(* (+ x 1) (+ x 2))`: the `+`-loop at depth 0 finds no `+` there (the
root is `*`), so its pattern fails, so it does not re-create itself — and
it is gone forever, even though `+` subterms appear at depth 1 one step
later. A loop's continuation must not depend on its *own* rule matching.

Hence the driver/rules-as-data split: one driver per phase carries the
loop, its continuation condition is operator-independent ("any todo at
this depth" / "a level fact for this sweep"), and it re-instantiates
*all* stored rules every round, whether or not they will match.

### Why the tags are spelled `a0`, `az`, `b0`, `bz`

Within one Phase A round, the freshly spawned rule instances (tagged
`(a0 ...)`) must run *before* the driver's next copy (tagged
`(az (S l))`): the next driver checks "any todo at depth l+1?", and the
depth-(l+1) todos are created by the depth-l rules. If the driver ran
first it would find nothing and the loop would die after one round. The
tag spelling forces the right order: `a0` and `az` are both 2-letter
symbols, and at equal length symbols compare alphabetically, so
`a0 < az` and the rules win. The same holds for `b0 < bz` in Phase B,
and the leading letters sequence the phases: `0... < a... < b... < zz`.

### Why the round counter never appears where it would need to sort

A tempting alternative is to tag each sweep's rule instances with the
sweep's Peano number and let priority order the sweeps. This fails
because of how shortlex treats Peano numerals: an expression outranks a
symbol, so `(S Z)` outranks `Z`, and in general **deeper Peano numerals
sort first** — priority would run the sweeps in *reverse*. The engine
avoids the trap: the level numeral inside a tag like `(b0 ((S Z) sum))`
serves only to make the tag *distinct* (the space is a set — two sweeps
with identical tags would collapse into one), never to order rounds.
Ordering comes solely from the driver spawning one sweep at a time and
the `b0 < bz` letter ordering within each round.

---

## Part 7 — Reading the output, and why it is not simplified

The engine's answers are correct but verbose: `(+ (* 1 (+ x 2)) (* x (+
1 0)))` instead of `(+ (* 2 x) 2)`. This is deliberate scope control.
Simplification — rewriting `(* 1 e)` to `e`, `(+ e 0)` to `e`, folding
`(+ 1 0)` to `1`, and so on — is a *second* rewriting system: the rules
must reach subterms nested anywhere inside the result, which requires its
own decompose/rebuild pass of exactly the same two-phase shape as the
differentiator. It composes cleanly after the collection step (its tags
would sort after `(zz out)`), and it is the natural next extension; it is
just not required for the differentiation itself to be correct.

Two other limitations, and their reasons:

- **Every leaf must be declared** via `(dvar x)` or `(const c)`. An MM2
  pattern cannot ask "is this a bare symbol?" (a variable like `$u`
  matches leaves and compound expressions alike), and without negation
  the engine cannot detect "leaf with no base fact" to warn about it. An
  undeclared leaf simply never receives a `(d leaf _)` fact, so every
  subterm containing it silently stays underivable and the affected
  `(diff ...)` produces no `(result ...)`. If a result is missing, check
  the declarations first.
- **No power rule** `(pow u n)`. Its derivative `n·u^(n−1)·du` needs
  arithmetic on the exponent (computing n−1), which means either Peano
  arithmetic rules or MORK's `pure` numeric sinks — both doable, neither
  free, so it is left out of this version.

---

## Part 8 — How the tests work

`test.mm2` follows the wiki page "MM2 Example: Testing Your Code". Each
test case supplies the input *and* the expected answer:

```
(diff (sin (* x x)))
(solution (sin (* x x)) (* (cos (* x x)) (+ (* 1 x) (* x 1))))
```

After the engine finishes, test `exec`s (tags `(zzt 0)` through
`(zzt 3)`, which sort after everything in the engine) compare the
produced `result` facts against the `solution` facts by building their
*symmetric difference* — the set of facts appearing in one but not both:

1. copy every produced result into a `(MISTAKE ...)` fact;
2. copy every expected solution into a `(MISTAKE ...)` fact;
3. *remove* `(MISTAKE ...)` for every fact present in **both** — this
   step uses the `O`-form sink `(O (- fact))`, the one place the project
   deletes facts;
4. write `(CORRECT e)` for every test case, then remove it again for any
   case that still has a `MISTAKE`.

A perfect run therefore ends with one `(CORRECT ...)` per case and no
`MISTAKE` facts. A wrong or missing derivative leaves the disagreeing
facts visible as `(MISTAKE ...)` — showing both what was produced and
what was expected — and deletes that case's `CORRECT`. This was verified
in both directions: the shipped suite passes all six cases, and
deliberately corrupting one `solution` makes exactly that case flip to
`MISTAKE`.

---

## Part 9 — Running it yourself

From this folder (the `mork` binary must be built; see the wiki's
"Getting started" page):

```
./run.sh                  # differentiate the examples in example.mm2
./run.sh test.mm2         # run the test suite
./run.sh yourfile.mm2     # your own input
```

A minimal input file:

```
(dvar x)
(const 3)
(diff (* 3 (sin x)))
```

Things worth trying to deepen the picture:

- Add a new expression to `example.mm2` and predict, before running, how
  many `(level ...)` facts Phase A will record and which sweep of
  Phase B will produce the root's `d` fact.
- Delete a `(const ...)` declaration and watch the corresponding
  `result` silently disappear (Part 7 explains why).
- Add a new unary operator: one `arule` line, one `brule` line — for
  example `sqrt` with derivative `(/ du (* 2 (sqrt u)))`, plus
  `(const 2)` in the input.
- Run with `--steps N` (`mork run file --steps N`) for increasing N and
  diff the outputs to watch the space evolve one `exec` at a time; the
  script in `bits/bash_diff_util/mork_step_diff.sh` automates this.
