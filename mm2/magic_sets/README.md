# Magic sets in MM2

A reusable magic-sets transformer and evaluator for finite, positive Datalog.
The input contains predicate declarations, facts, rules, and named queries.
MM2 infers binding patterns, rewrites the reachable rule variants, and evaluates
the generated program. No rules or predicate names are hard-coded for reachability.

`magic_engine.mm2` performs the transformation. `common.mm2` supplies list and
binding operations, a rule interpreter, and an incremental fixed-point scheduler.
`builtins.mm2` implements grounded signed-integer body literals with checked
arithmetic through the MORK `pure` sink.
`plain_engine.mm2` uses the same interpreter to compute full Datalog closure
without magic restrictions. `run.py` validates the input, invokes MORK, and
selects output records; it does not transform rules or evaluate Datalog.

## Run

From this directory:

```bash
./run.sh                              # reachability query, magic evaluation
./run.sh --engine plain               # same query, full-closure evaluation
./run.sh --show rules                 # inspect generated clauses
./run.sh --show magic                 # inspect accumulated demand facts
./run.sh --show derived --stats        # derived tuples and MORK counters
./run.sh example_joins.mm2             # bindings through joins and recursion
python3 -B test.py                    # semantic regression suite
```

By default the runner uses `../../../MORK/target/release/mork`, resolved relative
to this directory. Set `MORK=/absolute/path/to/mork` to use another binary.
The only runner dependency is Python 3.8 or later; no packages are required.
Input paths explicitly supplied on the command line are relative to the current
working directory. Omitting the input always selects the bundled example.

The MM2 files can also be run directly:

```bash
../../../MORK/target/release/mork run example.mm2 \
  --aux-path magic_engine.mm2 --aux-path common.mm2 --aux-path builtins.mm2
```

Direct invocation bypasses input validation and prints the entire MORK space,
including internal state. `./run.sh --show all` exposes that state with validation.
The runner's default 60-second timeout aborts with an error; it never returns a
partial answer as complete. Change it with `--timeout SECONDS` when needed.

## Example and its transformation

`example.mm2` defines these two rules. Here `x` is a path's starting node,
`y` is its destination, and `z` is the node reached by its first edge:

```text
path(x, y) :- edge(x, y).
path(x, y) :- edge(x, z), path(z, y).
query: path(a, destination)
```

The query binds the first argument to `a` and leaves the second free. Its
adornment is therefore `bf`, represented by `(cons b (cons f nil))`.
In the following readable Datalog notation, `path_bf` is that adorned relation
and `magic_path_bf` stores the starting nodes currently demanded:

```text
magic_path_bf(a).
magic_path_bf(z) :- magic_path_bf(x), edge(x, z).
path_bf(x, y) :- magic_path_bf(x), edge(x, y).
path_bf(x, y) :- magic_path_bf(x), edge(x, z), path_bf(z, y).
```

The actual generated MM2 clauses are available through `--show rules`.
The input includes a cycle between `b` and `c`, an edge from `c` to `d`, and a
disconnected chain from `u` through `v` to `w`. The query returns:

```scheme
(result from-a (atom path (cons a (cons b nil))))
(result from-a (atom path (cons a (cons c nil))))
(result from-a (atom path (cons a (cons d nil))))
```

The magic run derives **9 path tuples**, compared with **12** in full closure,
and derives none in the disconnected component. Both return the same three
query answers. Supporting tuples such as `path(b,d)` are still needed for the
recursive rule; magic sets do not restrict every derived tuple to the query's
literal starting node.

`example_joins.mm2` asks which city makes Alice eligible through a flight path
to a hub. The `resident` relation binds a city before the recursive `connected`
call. The generated demand rule includes that preceding join, so the query
produces `eligible(alice,boston)` without deriving Bob's disconnected routes.

## Input language

The input is a typed, ground representation of Datalog. The following table
defines the fields used in the syntax:

| Form | Meaning |
| --- | --- |
| `(edb P)` | Predicate name `P` denotes an extensional relation supplied as facts. |
| `(idb P)` | Predicate name `P` denotes an intensional relation defined by rules. |
| `(fact P VALUES)` | `VALUES` is a list of ground symbols forming a tuple of `P`. |
| `(atom P TERMS)` | `TERMS` is a list of constants or named Datalog variables. |
| `(builtin OP TERMS)` | `OP` is `add_i64`, `sub_i64`, or `ge_i64`; `TERMS` gives two inputs followed by the arithmetic output, if any. |
| `(v X)` | `X` is a variable name, local to its enclosing rule or query. |
| `(c V)` | `V` is a constant symbol. |
| `(rule R HEAD BODY)` | `R` is a unique rule identifier, `HEAD` an IDB atom, and `BODY` an ordered list of positive atoms. |
| `(query Q ATOM)` | `Q` is a unique query identifier; matching ground tuples are returned for `ATOM`. |
| `(cons ITEM REST)` / `nil` | A list cell with element `ITEM` and tail `REST`, or the empty list. |

For example, this defines a nonrecursive relation with the same tuples as `edge`:

```scheme
(edb edge)
(idb path)
(fact edge (cons a (cons b nil)))
(rule direct
  (atom path (cons (v x) (cons (v y) nil)))
  (cons (atom edge (cons (v x) (cons (v y) nil))) nil))
(query from-a (atom path (cons (c a) (cons (v destination) nil))))
```

Arity is inferred from occurrences and must be consistent for each declared
predicate. Lists permit arbitrary predicate arity and body length. Nullary atoms
have `nil` argument lists. Empty-body rules are allowed if their heads are ground.
Initial IDB tuples can therefore be written as ground empty-body rules.

Each variable in a rule's head must occur in its body (range restriction).
Repeated variables enforce equality, including repeated variables in queries.
Constants can occur anywhere in heads, bodies, or queries. Multiple queries
share derived facts and demand relations; each answer retains its query ID.
An IDB declaration with no defining rules denotes an empty relation.

Names and constants are bare symbols containing letters, digits, `_`, `.`, `:`,
`/`, `+`, or `-`. Constants such as `1`, `1.0`, and `nil` are distinct lexical
values, with no implicit numeric conversion. Semicolon comments are supported.
Quoted strings, native MM2 `$variables`, function terms, negation, disjunction,
aggregates, other arithmetic operations, and arbitrary `exec` directives are outside this
input language and rejected by the runner. Predicate declarations must distinguish
EDB from IDB; facts are supplied only for EDB predicates.

### Grounded integer literals

Arithmetic literals appear in rule bodies and do not need predicate declarations:

```scheme
; Here n is an index already bound by a preceding relational literal;
; previous is the subtraction's output variable.
(builtin ge_i64 (cons (v n) (cons (c 2) nil)))
(builtin sub_i64 (cons (v n) (cons (c 1) (cons (v previous) nil))))
```

`add_i64` and `sub_i64` take two inputs and one output term. `ge_i64` takes two
inputs and succeeds when the first is greater than or equal to the second.
The validator requires every input variable to be bound by preceding positive
atoms or preceding builtin outputs. A head/query binding alone is insufficient;
this keeps the source program evaluable by the plain engine as well. An output
may be a new variable, an existing variable, or a constant; it is unified with
the computed value, so conflicting values reject that branch.

The transformer retains these literals in their original position and in
magic-rule prefixes, and makes arithmetic output variables available to later
adornment analysis. Both evaluators use the same implementation. Inputs are
parsed as signed 64-bit integers; results are canonical decimal strings.
Arithmetic widens to signed 128-bit before calculating and checks the signed
64-bit result range. Failed comparisons are ordinary unsuccessful branches;
invalid numeric inputs and overflow emit `(ERROR builtin ...)` and cause the
runner to fail rather than publish incomplete answers. The
[Fibonacci example](../fib/README.md) uses these literals with a finite domain.

## How the engine works

The sideways information-passing strategy (SIPS) is deterministic: process a
rule's body in the written order. A literal's argument is bound if it is a
constant or its variable was bound by the head's requested positions or by a
previous positive body literal. After a literal succeeds, all its variables
are bound for the following literals.

The transformation starts from query adornments. Each reached IDB predicate and
adornment requests a rule variant. For every IDB call in a variant's body,
the engine emits a demand rule whose body is the parent's magic guard followed
by the already-processed body prefix. It also emits the adorned original rule
with that same guard prepended. New body adornments request further variants.
Constants and repeated variables are retained throughout the transformation.

Internal predicate keys are structural: `(base P)` for EDB predicate `P`,
`(rel P MASK)` for its adorned IDB variant, and `(magic P MASK)` for its demand
relation. `MASK` is the list of bound/free markers. Demand tuples contain only
the bound argument values, in their original positional order.

Generated clauses are data, evaluated by the generic MM2 interpreter in
`common.mm2`. A cursor records a clause, its unprocessed body, and its current
variable bindings. The interpreter joins the next literal, extends those
bindings, and resumes the cursor. At the end it substitutes the head and emits
a tuple. The first argument, when bound, is resolved before tuple lookup so
MORK can seek its predicate-and-value prefix; other argument constraints are
checked during unification.

The scheduler bootstraps every `(step ...)` template once, then activates
specialized rule instances from newly accepted `(delta ...)` facts. MM2 itself
compiles `(wake ...)` templates for each dynamic source of a step. Matching a
delta fact binds that source before executing the other joins. Both variable-name
sources of internal disequality are watched too, so delayed bindings are not
missed. The current internal step patterns use conjunctions of one through five
sources, plus the two explicit disequality-source shapes in `common.mm2`.

Instances produce `(next ...)` proposals. Each round removes proposals already
present in accepted `(ms ...)` facts, accepts the remaining facts, and queues them
as deltas. It continues only while new facts arrive. Rewriting and evaluation
both participate in this fixed point. There is no depth budget, Peano
representation, or numeric counter. Purely relational, finite, range-restricted
inputs give finite tuple, variant, cursor, and helper-relation sets, including
for cyclic programs. Programs using arithmetic must also keep generated values
bounded; the runner's timeout remains an operational limit.

`!=` is used internally to compare reified variable-name facts during environment
lookup. It is not Datalog negation. Deletion manages `next` and `delta` work sets
and final error checks; accepted facts are monotonic. Priorities sequence delta
activation, joins, pruning, acceptance, rescheduling, and final output collection.

## Output and verification

`result` records contain complete ground tuples matched by each query. There is
no result record for a query with no answers. `generated` records expose the
rewritten clauses, `magic` records expose demand, and `derived` records expose
adorned IDB tuples. In plain mode, `closure` records expose full IDB relations.
The last argument of each tuple record is a value list, not a list of `(c ...)`
terms. Generated clauses retain `(v ...)` and `(c ...)` terms.

The test suite checks both MM2 engines against an independent Python Datalog
closure implementation. It covers all four binary binding patterns, multiple
queries, duplicates, repeated variables, constants, empty answers, cycles,
left recursion, nonlinear recursion, mutual recursion, ternary atoms, bodies
with several joins, nullary predicates, ground empty-body rules, input errors,
checked arithmetic, numeric failures, and deterministically generated graphs.
It also checks that disconnected
components are excluded from the example's derived facts and that modified
clauses have a leading magic guard.

This implementation is intended for inspecting and developing the transformation.
It memoizes structural operations and incrementally activates rules, but still
materializes interpreter state. Rewriting overhead can make magic evaluation
slower despite deriving fewer IDB tuples. The relation counts demonstrate
relevance pruning, not a general runtime speedup. Written body order
also matters: a free query or an unselective early literal can require most of
the original closure. `--stats` reports actual MORK counters for comparison.

The transformation follows the standard adornment and magic-rule construction
described in [Soufflé's magic-set documentation](https://souffle-lang.github.io/magicset).
Local MORK references for the execution model are
[MM2 semantics](../../../MORK.wiki/Minimal-MeTTa-2-\(MM2\).md),
[sources and sinks](../../../MORK.wiki/Sources-and-Sinks.md), and
[MM2 testing](../../../MORK.wiki/MM2-Example:-Testing-Your-Code.md).
