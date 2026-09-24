# Magic sets in MM2

A reusable magic-sets transformer and evaluator for finite, positive Datalog.
The input contains predicate declarations, facts, rules, and named queries.
MM2 infers binding patterns, rewrites the reachable rule variants, and evaluates
the generated program. No rules or predicate names are hard-coded for reachability.

`magic_engine.mm2` performs the transformation. `common.mm2` supplies list and
binding operations, a rule interpreter, and a fixed-point scheduler.
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
  --aux-path magic_engine.mm2 --aux-path common.mm2
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
aggregates, arithmetic builtins, and arbitrary `exec` directives are outside this
input language and rejected by the runner. Predicate declarations must distinguish
EDB from IDB; facts are supplied only for EDB predicates.

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

The scheduler evaluates all `(step ...)` templates against accepted `(ms ...)`
facts, producing `(next ...)` proposals. After a sweep, it removes proposals
already present in `ms`, accepts the remaining facts, and starts another sweep
only if there were new facts. Rewriting and evaluation both participate in this
fixed point. The scheduler has no depth budget, Peano representation, or numeric
counter. Finite inputs and range-restricted, function-free rules give finite
tuple, variant, cursor, and helper-relation sets, including for cyclic programs.

`!=` is used internally to compare reified variable-name facts during environment
lookup. It is not Datalog negation. Deletion is confined to staging the `next`
work set; accepted facts are monotonic. Priorities put all sweep steps before
pruning, acceptance, rescheduling, and final output collection.

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
and deterministically generated graphs. It also checks that disconnected
components are excluded from the example's derived facts and that modified
clauses have a leading magic guard.

This implementation is intended for inspecting and developing the transformation.
It memoizes structural operations but still sweeps its rules and materializes
interpreter state. On the small bundled examples, rewriting overhead makes
magic evaluation slower despite deriving fewer IDB tuples. The relation counts
demonstrate relevance pruning, not a general runtime speedup. Written body order
also matters: a free query or an unselective early literal can require most of
the original closure. `--stats` reports actual MORK counters for comparison.

The transformation follows the standard adornment and magic-rule construction
described in [Soufflé's magic-set documentation](https://souffle-lang.github.io/magicset).
Local MORK references for the execution model are
[MM2 semantics](../../../MORK.wiki/Minimal-MeTTa-2-\(MM2\).md),
[sources and sinks](../../../MORK.wiki/Sources-and-Sinks.md), and
[MM2 testing](../../../MORK.wiki/MM2-Example:-Testing-Your-Code.md).
