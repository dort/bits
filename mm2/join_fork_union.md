# Join, Fork, and Union in MORK and MM2

*A tutorial from first principles*

Three words — **union**, **join**, and **fork** — name three different ideas that come
from three different traditions:

- **union** comes from *set theory*: combining two collections into one.
- **join** comes from two places at once: *databases* (combining tables by matching
  shared values) and *parallel computation* (waiting for split-off work to finish and
  combining the results).
- **fork** comes from *parallel computation*: splitting one task into several
  independent subtasks.

In MORK and MM2 all three ideas operate in one machine, and — this is the reason the
distinctions are worth studying — they sit at **different levels** of that machine:

| word | where it lives | is it a built-in? |
|---|---|---|
| union | the storage layer: every write to the space is a union | yes, ambient and unavoidable |
| join (relational) | the query layer: every multi-pattern match is a join | yes, it is what pattern lists mean |
| fork / join (process) | the program layer: a naming convention written as ordinary data | no — programs define it themselves |

This tutorial builds up from nothing: what a set is, what an expression is, how MM2
programs run, and then each of the three concepts in turn, ending with a close reading
of the program `Going_Wide_02.mm2`, where a process-level fork/join is built out of
the storage-level union and the query-level join.

Every output shown below was produced by actually running the programs with the
`mork` binary in `MM2_Structuring_Code/structuring_code/mm2_programs/`:

```sh
cd MM2_Structuring_Code/structuring_code/mm2_programs
./mork run <FILE_NAME>.mm2
```

**What MORK and MM2 are.** MORK (MeTTa Optimal Reduction Kernel) is the engine: a
Rust program containing a database and a virtual machine. Its database — called the
**space** — stores expressions in a *trie*, a tree of shared prefixes (the Rust type is
`PathMap`, in `MORK/kernel/src/space.rs`). MM2 ("MeTTa Minimal 2", the *metta
calculus*) is the minimal language that MORK executes. MM2 has exactly one kind of
instruction, called an `exec`. Everything else in an MM2 file — inputs, definitions,
rules, intermediate results — is plain data sitting in the space.

---

## Part I — Sets

A **set** is a collection of things in which:

1. a thing is either *in* the set or *not in* it — there is no "in it twice";
2. there is no order — a set containing `a` and `b` is the same set as one
   containing `b` and `a`.

The things in a set are called its **elements**. We write a set by listing its
elements in braces: `{a, b, c}`.

Three basic ways to combine two sets A and B:

- **union** (written A ∪ B): the set of everything that is in A *or* in B (or both).
  `{a, b} ∪ {b, c} = {a, b, c}`. Note `b` appears once — sets have no duplicates.
- **intersection** (A ∩ B): everything that is in A *and* in B.
  `{a, b} ∩ {b, c} = {b}`.
- **difference** (A \ B): everything in A that is *not* in B.
  `{a, b} \ {b, c} = {a}`.

Two properties of union matter later:

- Union only ever *adds*. If an element is in A, it is in A ∪ B, no matter what B is.
  An operation with this only-adds character is called **monotonic**.
- Union is **idempotent**: A ∪ A = A. Adding the same elements again changes nothing.

---

## Part II — Expressions and the space

### Expressions

The elements MORK stores are **expressions**, built from three ingredients:

- **Symbols**: bare names like `a`, `and`, `case/2`, or numbers like `0` and `1`.
  A symbol has no internal structure; two symbols are equal exactly when they are
  spelled the same.
- **Tuples**: a parenthesized sequence of expressions, like `(a 1)` or
  `(and (or 1 0) 1)`. The number of elements a tuple holds is its **arity**:
  `(a 1)` has arity 2, `(and x y)` has arity 3. Tuples nest to any depth.
- **Variables**: names beginning with `$`, like `$x`. A variable stands for an
  unknown expression. Expressions without variables are called **ground**.

### The space is a set

The space is a *set of expressions*, and this is enforced by its storage. Each
expression is serialized into a sequence of bytes (its *path*) and inserted into the
trie; inserting a path that is already present changes nothing. Set semantics are not
a convention the programmer maintains — they are what the data structure does.

You can see this by concatenating two files and running them. One file contains
`a` and `b`; the other contains `b` and `c`:

```sh
./mork run Basics_03_file1_file2.mm2
```
```
a
b
c
```

Loading files into the space **is** set union. `b` was in both files and appears
once. (The printout order is the trie's traversal order, not the order things were
written — a set has no order to preserve.)

Because the trie shares prefixes, expressions that begin the same way share storage.
A thousand expressions of the form `(sensor-reading ...)` store the
`sensor-reading` part once. This *prefix compression* is why the path-heavy
representations in Part VI are cheaper than they look.

### Keeping sets apart: predication

If everything lands in one big set, how do you keep "file 1's data" and "file 2's
data" distinct? By wrapping each element in a tuple that names its origin:
`(file1 a)` and `(file2 a)` are different expressions, so they coexist without
merging. The wrapper is called a **predication**, and the leading symbol acts as a
location or namespace. Because of prefix sharing, a predication is also an *index*:
all `(file1 ...)` expressions live under one trie prefix and can be enumerated
without touching anything else.

---

## Part III — Patterns, unification, and the exec

### Patterns

A **pattern** is an expression that may contain variables. A pattern *describes a
subset of the space*: the pattern `(file1 $x)` describes every expression in the
space that is a 2-tuple whose first element is the symbol `file1` — and for each
such expression, it *binds* `$x` to the second element. A set of variable
assignments like `{ $x => a }` is called a **binding**.

### Unification

Matching in MORK is done by **unification**: given two expressions (either of which
may contain variables), find a substitution for the variables that makes the two
expressions identical, or report that none exists. The result, when it exists, is
the **most general unifier (MGU)** — the substitution that forces nothing beyond
what the two expressions require. Examples:

```
unify : (1 2) and (1 2)         MGU: {}                      ; constants match themselves
unify : $x and (1 2)            MGU: { $x => (1 2) }         ; a variable matches anything
unify : ($x 2) and (1 $y)       MGU: { $x => 1, $y => 2 }    ; matching runs both directions
```

One rule carries most of the weight in everything that follows: **the same variable
appearing twice must receive the same value.** Unifying `($x $x)` with `(1 2)`
fails, because `$x` cannot be both `1` and `2`. A repeated variable is a
*constraint*.

### The exec

MM2's single instruction:

```
(exec <priority> <sources> <sinks>)
```

- `<priority>` is a ground expression that determines *when* this exec runs relative
  to other execs (ordering explained in Part VI).
- `<sources>` is a list of patterns, written `(, <pattern> <pattern> ...)`. All
  patterns are matched against the space *simultaneously*; each way of satisfying
  all of them at once yields one binding.
- `<sinks>` is a list of templates, written `(, <template> ...)`. For every binding
  the sources produced, every template is instantiated (its variables replaced by
  their bound values) and the result is written into the space.

When an exec runs, it is removed from the space, it computes **all** bindings, and it
performs **all** its writes, as one transaction. A run of an MM2 program is nothing
but: pick the next exec by priority, run it, repeat.

A concrete run (`Basics_07_Sources_Sinks.mm2`) — the space holds `(a 1)`, `(a 2)`,
`(b 3)`, and:

```
(exec 0
   (, (a $x) (b $y) )
   (, (ab $x $y)    )
)
```

The sources produce two bindings, `{ $x => 1, $y => 3 }` and `{ $x => 2, $y => 3 }`,
and the sink writes both instantiations:

```
(a 1)
(a 2)
(b 3)
(ab 1 3)
(ab 2 3)
```

There is a second sink form, `(O ...)`, whose entries are actions:
`(+ <template>)` adds, like the `,` form; `(- <template>)` **removes** the
instantiated template from the space. Removal is the one non-monotonic operation in
the language, and Part VI shows it is exactly the operations needed to make a loop halt.

---

## Part IV — Union

### Union is ambient

You have already seen the first and most important fact about union in MORK: **it is
not an operation you call — it is what the space does.**

- Loading a file unions its expressions into the space.
- Every `,`-sink write unions the instantiated templates into the space. Writing an
  expression that is already present changes nothing (idempotence, from Part I).
- Loading two files, or running two execs that write overlapping results, produces
  the union of their outputs with duplicates collapsed, automatically.

Monotonicity and idempotence are inherited from set union, and both are load-bearing:
Part VI's main loop re-runs the same rewrites over the same data every cycle and
relies on "already present ⇒ no change" for that to be harmless.

### Union as a program

Union between two *predicated* subsets is a two-line exec. With arguments stored at
locations `arg_a` and `arg_b` and the result to be placed at `ret`
(`Set_Ops_03_Union.mm2`):

```
(exec 0
   (, (arg_a $a)
      (arg_b $b)
   )
   (, (ret   $a)
      (ret   $b)
   )
)
```

Read it as: for every `$a` in the `arg_a` set and every `$b` in the `arg_b` set,
write `$a` and `$b` into the `ret` set. Given `arg_a = {a, b, c}` and
`arg_b = {b, c, d}`, running it yields:

```
(ret a)
(ret b)
(ret c)
(ret d)
```

Two subtleties hide in this small program:

1. **The two patterns share no variable**, so the sources produce the *cartesian
   product* of bindings — all 9 pairs (`$a`, `$b`). The sink writes `(ret $a)` nine
   times for three distinct values, and `(ret $b)` nine times for three distinct
   values. The space's set semantics collapse those 18 writes into 4 elements. Union
   as a *program* is the cartesian product of matches flattened by union as a
   *storage property*.
2. **If either argument set is empty, the sources produce no bindings at all**, and
   nothing is written — not even the elements of the non-empty set. An exec's sources
   must *all* match for anything to happen. The set-theoretic union with an empty set
   would return the other set; this program returns nothing. Union-as-program and
   union-as-storage-property agree only when both inputs are non-empty.

### A terminology collision to defuse now

In *lattice theory* (the branch of order theory that generalizes sets ordered by
inclusion), the union-like operation is called **join** (written ∨) and the
intersection-like operation is called **meet** (∧). MORK's own code uses this
vocabulary: the trie library exposes a `Lattice` trait
(`pathmap::ring::Lattice`, imported in `space.rs`), and a benchmark in
`MORK/kernel/src/main.rs` defines `\/` ("join") as *maximum* and `/\` ("meet") as
*minimum* over numbers.

So when reading around this ecosystem, "join" can mean **union** (lattice usage) or
the two quite different things described next (relational usage, process usage).
The rest of this tutorial uses "join" only in the relational and process senses, and
flags the lattice sense where it appears.

---

## Part V — Join: the relational sense

Put intersection next to union and look at the one-character difference
(`Set_Ops_04_Intersection.mm2`):

```
(exec 0
   (, (arg_a $a)
      (arg_b $a)     ; <- same variable as the line above
   )
   (, (ret $a) )
)
```

The two source patterns now share the variable `$a`, and Part III's rule applies:
the same variable must receive the same value everywhere. A binding exists only for
values present in *both* sets. With the same inputs as before:

```
(ret b)
(ret c)
```

This — matching several patterns simultaneously with shared variables constraining
the combination — is precisely what databases call a **join** (specifically a
*natural join*). A pattern list `(, p1 p2 ... pn)` is what logic calls a
*conjunctive query*: find every assignment of the variables that satisfies pattern 1
AND pattern 2 AND ... AND pattern n. The spectrum runs:

- **no shared variables** → cartesian product (the union program in Part IV);
- **all patterns identical in one shared variable** → intersection (the program above);
- **partially shared variables** → a genuine relational join. In Part III's example,
  if the space held `(a 1 x)`, `(a 2 y)`, `(b 1 p)`, then
  `(, (a $k $v) (b $k $w))` would join the `a`-set and `b`-set on the shared key
  `$k`, yielding only `{ $k => 1, $v => x, $w => p }`.

**Mechanism.** MORK executes a pattern list by opening one trie cursor (a *zipper*)
per pattern and walking their product (`Space::query_multi` in `space.rs` builds a
`ProductZipper` over one read-zipper per source pattern). Shared variables prune the
walk: once `$a` is fixed to `b` on the first cursor, the second cursor descends only
the `b` branch of its subtree instead of enumerating everything. The join is not
"generate all combinations, then filter" — the trie structure lets constraint
propagation cut off whole subtrees before they are visited.

The closing remark of the set-operations tutorial is worth restating as the summary
of Parts IV and V: these operations generally need not be *defined*, they need to be
*understood* — a set operation happens implicitly every time an exec runs. Every
exec is: a relational join over the space (sources) followed by a union into the
space (sinks), with optional set difference (`O`-sink removals).

---

## Part VI — Fork and join: the process sense

Now the third tradition. In parallel programming, **fork** means "split one task
into independent subtasks" and **join** means "wait until the subtasks are done,
then combine their results." `Going_Wide_02.mm2` builds exactly this discipline —
and the punchline is that its *join* is implemented by Part V's relational join,
and its bookkeeping works because of Part IV's union semantics.

### The problem

The program evaluates a Boolean formula, stored in the space as one nested
expression:

```
(INPUT
   (if (or (1)
           (not (and (or (1) (0))
                     (1)
                )
           )
       )
       (and (1)
            (or (0) (1))
       )
   )
)
```

Here `0` and `1` are the truth values false and true, and `and`, `or`, `not`, `if`
are the usual logical connectives. A bare value is wrapped as a 1-tuple, `(1)`, to
distinguish "the constant one" from other uses of the symbol.

What the connectives do is given not by built-in logic but by a **finite function**:
a truth table written as plain expressions of the form `(eval <expr> -> <result>)`,
one per case:

```
(eval (and 0 0) -> 0)
(eval (and 0 1) -> 0)
(eval (and 1 0) -> 0)
(eval (and 1 1) -> 1)
... (or, if, not, and the bare values (0), (1))
```

Evaluating one node is then a single pattern match: to evaluate `(and 1 0)`, match
`(eval (and 1 0) -> $out)` against the table and read `$out`. No arithmetic, no
built-in Booleans — evaluation is table lookup, which is to say: a join against the
table.

The obstacle is the *shape* of the input. Pattern matching reaches a fixed depth: a
pattern like `($op $x $y)` sees the top node of a tree, and `$x`, `$y` bind to whole
subtrees. To match a *leaf* buried five levels down you would need a pattern nested
five levels deep — and a different pattern for every possible tree shape. Evaluation
must start at the leaves, so the nesting itself is the enemy. The tutorial's goal
("going wide") is to process *many nodes per exec*, and one nested expression
exposes only one node at a time.

### The representation: paths as disjoint predications

The fix is to invert the tree. Instead of one deep expression, store one *flat*
expression per node, keyed by the **path** from the root to that node:

```
((.   case/2) and)                        ; the root is a 2-argument node: and
(((.  arg/0 ) case/2) or)                 ; root's argument 0 is a 2-argument node: or
((((. arg/0 ) arg/0 ) case/0) 1)          ; that node's argument 0 is the value 1
((((. arg/0 ) arg/1 ) case/0) 0)          ; ... and its argument 1 is the value 0
(((.  arg/1 ) case/2) if)                 ; root's argument 1 is a 2-argument node: if
((((. arg/1 ) arg/0 ) case/0) 1)
((((. arg/1 ) arg/1 ) case/0) 1)
```

Read `(. arg/0)` as "the 0th argument of the root", `((. arg/0) arg/1)` as "the 1st
argument of the 0th argument of the root", and so on: a path is a tuple that grows
one step per level of descent. The tag at the end of each path records what kind of
node lives there: `case/0` marks a bare value, `case/1` a 1-argument node, `case/2`
a 2-argument node.

Every node of the tree is now a top-level element of the space, matchable by the
shallow pattern `(($path <tag>) $value)` regardless of how deep it originally sat.
Two properties make the representation sound:

- **Disjoint paths**: two different nodes have two different paths, so their
  expressions never collide in the set.
- **Prefix sharing**: all descendants of a node have paths extending that node's
  path, so the trie stores each ancestor path once (Part II).

### fork: the splitter

The conversion from nested input to path representation is done by rewrite rules the
program stores as *data* under the name `DEF fork` — three rules, dispatched on
tuple arity. The recurring symbols:

| symbol | meaning |
|---|---|
| `$ctx` | the path built so far ("context"); starts as `DONE` at the root |
| `$case/0`, `$case/1`, `$case/2` | the node's own symbol: a bare value, a 1-argument operator, a 2-argument operator (the `/n` in the *variable name* is documentation for humans; the arity dispatch is done by the tuple *pattern shape*) |
| `$x`, `$y` | the argument subtrees, still nested |
| `(fork P)`, `(join P)` | tags marking "work pending at path P" and "result or operator available at path P" |

```
; case/0 — a bare value: nothing below it, convert directly to a join
(DEF fork
      (, ((fork $ctx) ($case/0)) )
      (, ((join ($ctx case/0)) $case/0) )
)
; case/1 — unary node: deposit the operator for joining, keep forking the argument
(DEF fork
      (, ((fork $ctx) ($case/1 $x))   )
      (, ((fork ($ctx arg/0 )) $x     )
         ((join ($ctx case/1)) $case/1)
      )
)
; case/2 — binary node: deposit the operator, fork both arguments
(DEF fork
      (, ((fork $ctx) ($case/2 $x $y)))
      (, ((fork ($ctx arg/0 )) $x     )
         ((fork ($ctx arg/1 )) $y     )
         ((join ($ctx case/2)) $case/2)
      )
)
```

A fork step consumes nothing (its sinks only add — remember writes are unions) and
produces, from one pending node:

- one `(join ...)` fact carrying the node's operator, parked at an extended path —
  this is the breadcrumb the joining phase will need;
- one new `(fork ...)` work item per argument subtree, each at its own extended path.

This *is* the fork of fork/join: one work item becomes several independent work
items on **disjoint paths**. Independence here is not about threads — it is about
data: no two forked subtasks ever write to the same path, so they cannot interfere,
so a single exec can process *every* pending fork in the space in one transaction.
Repeatedly applied, the rules peel the input tree one layer per application:

```
((fork DONE) (and (or (1) (0)) (if (1) (1))))

=> after one fork pass (the root, arity 2):
((join (DONE case/2)) and)
((fork (DONE arg/0)) (or (1) (0)))
((fork (DONE arg/1)) (if (1) (1)))

=> after another pass (both children, in the same transaction — this is "going wide"):
((join (DONE case/2)) and)
((join ((DONE arg/0) case/2)) or)
((fork ((DONE arg/0) arg/0)) (1))
((fork ((DONE arg/0) arg/1)) (0))
((join ((DONE arg/1) case/2)) if)
((fork ((DONE arg/1) arg/0)) (1))
((fork ((DONE arg/1) arg/1)) (1))

=> after the last pass (all four leaves at once):
((join (DONE case/2)) and)
((join ((DONE arg/0) case/2)) or)
((join (((DONE arg/0) arg/0) case/0)) 1)
((join (((DONE arg/0) arg/1) case/0)) 0)
((join ((DONE arg/1) case/2)) if)
((join (((DONE arg/1) arg/0) case/0)) 1)
((join (((DONE arg/1) arg/1) case/0)) 1)
```

### join: the collector, and where the two senses of "join" meet

The joining rules run the tree back up, evaluating as they go:

```
; case/0 — a bare value: look it up in the table
(DEF join
      (, ((join ($ctx case/0)) $case/0)
         (eval ($case/0) -> $out)
      )
      (, ((join $ctx) $out) )
)
; case/2 — an operator plus BOTH argument results
(DEF join
      (, ((join ($ctx case/2)) $case/2)
         ((join ($ctx arg/0 )) $x     )
         ((join ($ctx arg/1 )) $y     )
         (eval ($case/2 $x $y) -> $out)
      )
      (, ((join $ctx) $out)  )
)
; (case/1 analogous, with one argument)
```

Look at the `case/2` sources as what Part V says they are: a **four-way relational
join on the shared variable `$ctx`** (and on `$case/2`, `$x`, `$y` against the
table). A binding exists for a node only when *all four* facts are simultaneously
present in the space:

1. the operator parked at `($ctx case/2)` — deposited by fork;
2. the result of argument 0 at `($ctx arg/0)`;
3. the result of argument 1 at `($ctx arg/1)`;
4. a truth-table row matching the operator applied to those two results.

If argument 1 has not been computed yet, pattern 3 has no match *for that `$ctx`*,
so no binding forms *for that node*, and the rule simply does nothing there — while
still firing for every node whose arguments *are* ready. This is the
synchronization of fork/join, and there is no waiting machinery anywhere: **the
barrier "wait until all subtasks are done" is the relational join's requirement
that all patterns match on the shared `$ctx`.** A parent's result appears exactly
one pass after the last of its children's results appears. The result propagates
one level up per pass, and the value written at the original context —
`((join DONE) $out)` — is the answer for the whole tree.

For the small example: the leaf lookups produce `((join ((DONE arg/0) arg/0)) 1)`
and its three siblings; the next pass finds `or` with `1` and `0`, and `if` with `1`
and `1`, writes `((join (DONE arg/0)) 1)` and `((join (DONE arg/1)) 1)`; the pass
after that finds `and` with `1` and `1` and writes `((join DONE) 1)`.

Note what join does *not* do: it does not remove the child results it consumed. The
space accumulates every intermediate fact, monotonically, until cleanup (below).
Union semantics make this safe; prefix compression makes it cheap.

### The main loop: driving fork and join to a fixed point

The rules above are inert data (`DEF fork ...`, `DEF join ...` are just expressions
in the space). One exec, `MAIN`, turns them into running execs each cycle — it
matches the `DEF`s *and itself*, and spawns:

```
(exec (1 fork) <fork sources> <fork templates>)   ; one per DEF fork
(exec (0 join) <join sources> <join templates>)   ; one per DEF join
(exec (TERM)  ...)                                ; termination check
(exec (RESET) ...)                                ; respawn MAIN if work remains
```

Priorities are ground expressions ordered by their trie path encoding; the working
rule of thumb is *lower-arity tuple before higher-arity tuple, then shorter symbol
before longer symbol*. Running the program with increasing `--steps` values shows
the actual order within each cycle:

```
(TERM) → (RESET) → the three (0 join) execs → the three (1 fork) execs → MAIN respawns
```

Walking one cycle:

- **TERM** fires only when `((join DONE) $OUTPUT)` exists — the root result. Its
  sinks use the `O` form: `(+ (OUTPUT $OUTPUT))` publishes the answer, and
  `(- ((fork $f_env) $arg))`, `(- ((join $j_env) $res))` delete *every* accumulated
  fork and join fact (the sources bind them all; every binding is deleted). Until
  the root result exists, TERM's sources have no binding and it dies having done
  nothing — selection by match failure, the same mechanism as everywhere else.
- **RESET** matches `(($fork_join $ctx) $val)` — "any fork- or join-tagged fact
  exists" — and respawns MAIN. After TERM's sweep nothing matches, RESET dies,
  MAIN is never respawned, and the program halts. Removal (`-`) is the only
  non-monotonic ingredient, and it is exactly what termination requires: a
  monotonic system can stop *producing new facts* but cannot make a "keep going"
  condition become false.
- The **join** execs run before the **fork** execs (`(0 join)` precedes
  `(1 fork)`), so results propagate up before new work is peeled off.

One more subtlety keeps the loop honest. Fork execs never delete the
`((fork ...) ...)` facts they process, so next cycle's fork execs re-match the same
facts and re-write the same outputs. This would be an error in most languages;
here it is a no-op, because writing an already-present element is idempotent
(Part IV). Each cycle recomputes everything computable and the space simply stops
growing — the loop is a **fixed-point iteration**, with progress measured by new
elements and convergence detected by TERM. The whole architecture leans on union's
two properties from Part I: monotonicity makes re-running safe in principle,
idempotence makes it free in practice.

Running it:

```sh
./mork run Going_Wide_02.mm2
```
```
(OUTPUT 1)
```

which is correct: the inner `(or 1 0)` is 1, `(and 1 1)` is 1, `(not 1)` is 0,
`(or 1 0)` is 1 for the condition; the consequent `(or 0 1)` is 1, `(and 1 1)` is 1;
and `(if 1 1)` is 1.

*(A cosmetic note if you inspect intermediate states: the space stores variables in
a canonical form, so `$ctx` in your source prints back as `$a` — variable names
carry no identity beyond their pattern.)*

---

## Part VII — The three concepts, side by side

| | union | join (relational) | fork / join (process) |
|---|---|---|---|
| tradition | set theory | databases, logic | parallel computation |
| in MORK/MM2 it is | the storage layer's behavior: every write, every file load | the query layer's behavior: every multi-pattern source list | a programming convention: `fork`/`join` are ordinary symbols in ordinary data |
| built-in? | yes, ambient | yes, it is what `(, ...)` means | no — `Going_Wide_02.mm2` defines it in ~40 lines |
| combines | two sets into one, by accumulation | several patterns into bindings, by shared-variable constraint | split-off subtasks into a result, by waiting for completeness |
| character | monotonic, idempotent, unordered | read-only; produces bindings, not data | built from the other two, plus deletion for termination |
| failure mode at the empty set | A ∪ ∅ = A | one empty pattern ⇒ zero bindings ⇒ nothing happens | a missing child result ⇒ that node silently not joined this pass |

And the relationships between them, which are the real content of this tutorial:

1. **Every exec is a join followed by a union.** Sources perform a relational join
   over the space; sinks union the instantiated templates back in. Set operations
   are not features of MM2 — they are its execution model.
2. **The process-level join is implemented by the relational join.** The
   "wait for all children" barrier is nothing but the requirement that four patterns
   match simultaneously on a shared path variable `$ctx`. Synchronization by
   conjunctive query, not by any waiting primitive.
3. **The process-level fork is enabled by union's idempotence and the disjointness
   of paths.** Forked subtasks write to disjoint paths, so bulk processing is safe;
   re-forking already-forked work rewrites existing elements, so re-running to a
   fixed point is free.
4. **The vocabulary does not travel between traditions — check the level before
   trusting the word.** Lattice theory calls union "join". MORK's own fringe
   benchmarks (`exponential_fringe` and neighbors in `MORK/kernel/src/main.rs`) name
   their splitting step `meet` and their combining step `join` — the same
   split/combine discipline `Going_Wide_02.mm2` names `fork` and `join`. Since
   fork/join names are program-level conventions rather than keywords, each program
   picks its own; the mechanism underneath (disjoint-path splitting, shared-variable
   joining, fixed-point iteration) is what stays constant.

## Where to go next

- `structuring_code_05_Going_Wide.md` develops `Going_Wide_02.mm2` step by step.
- `structuring_code_06_Going_Wide_Macros.md` generalizes the fork/join rules so the
  joining operation (`eval`) and a process namespace become parameters, expanded at
  startup by a macro pass — the same fork/join skeleton then drives different folds.
- `structuring_code_07/08` scale to multiple inputs, multiple concurrent instances,
  and two different programs sharing the fork/join machinery.
- The `--steps N` flag replays a program one exec at a time
  (`./mork run --steps 3 Going_Wide_02.mm2`); diffing consecutive step counts, as in
  `bits/bash_diff_util/`, is the best way to watch the cycle order and the
  fixed-point behavior with your own eyes.
