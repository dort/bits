# Sieve of Eratosthenes in MM2, with magic sets

Finds all primes up to a query bound by forward rewriting in the MORK
space. The program is structured as a **magic-set transformation** of
the Datalog sieve: every derived fact is demanded, directly or
transitively, by the `(query N)` fact, so the naturally unsafe
bottom-up program becomes finite and goal-directed. All arithmetic is
grounded in Rust via the `pure` sink.

## Files

- `sieve.mm2` — the engine
- `example.mm2` — `(query 100)`
- `test.mm2` — symmetric-difference test against the primes up to 50
- `run.sh` — concatenates input + engine and runs `mork run`

## Usage

```
./run.sh                # primes up to 100: 25 (prime K) facts
./run.sh test.mm2       # expect (CORRECT 50), no MISTAKE
```

Input is a single `(query N)` fact, N ≥ 1 an i64 literal; output is one
`(prime K)` fact per prime K ≤ N. Verified against an independent
primality check for N = 1, 2, 3, 50, 100.

## Magic sets: the point

The natural bottom-up sieve is *unsafe*: "generate candidates" and
"generate multiples" range over all naturals, so naive saturation never
terminates. Top-down evaluation (Prolog-style) is goal-directed but MM2
only saturates bottom-up. The magic-set transformation is the standard
Datalog answer: rewrite the program so the query's bindings flow into
*demand predicates* that gate every generator. The transformed program,
which `sieve.mm2` implements rule for rule:

```
magic_upto(N)  :- query(N).                  % the demand root
cand(K)        :- magic_upto(N), 2 <= K <= N.
magic_base(B)  :- cand(B), B*B <= N.         % sieve only below sqrt(N)
reach(B, B)    :- magic_base(B).
reach(B, M)    :- reach(B,M1), reach(B,M2), M = M1+M2, M <= N.
composite(M)   :- reach(B, M), M != B.
prime(K)       :- cand(K), not composite(K).
```

Demand is visible in the space: run it and every `nat`, `cand`,
`mbase`, and `reach` fact lies inside the query's bound — delete the
`(query N)` fact and the program derives nothing at all. The base
demand (`magic_base`) is the sieve's classic optimization expressed as
demand reasoning: there is no demand to cross off multiples of B unless
B² ≤ N.

Three renderings depart from the textbook, each for an MM2 reason:

- **Doubling instead of counting.** The textbook demand chains are
  linear recursions (`K+1`, `M+B`), needing O(N) rule applications in
  sequence. Here both demanded sets are *additive closures* —
  candidates close `{1, 2}` under clamped addition, multiples of B
  close `{B}` — which materialize the same sets in O(log N) sweeps.
  Same magic set, parallel derivation.
- **All bases, not just prime bases.** Classical Eratosthenes crosses
  off multiples of primes only, but "B is prime" is not known until the
  sieve finishes; the textbook program handles that with stratified
  negation, which MM2 lacks. The demand therefore includes every
  candidate base up to √N, prime or composite. Redundant — a composite
  base's multiples were already crossed off by its own factors — but
  sound, and still bounded by the query.
- **Set-difference sinks for the final negation.** The one genuinely
  non-monotonic step of the sieve (survivors = candidates minus
  crossed-off) maps onto MM2's `+`/`-` sinks: add every candidate as
  `(prime K)`, then remove `(prime M)` for every composite. Everything
  before that step is monotonic saturation.

## Grounded arithmetic idioms

MM2 has no comparison predicates, so the two tests the sieve needs are
built from `pure` functions plus pattern matching:

- **X ≤ N:** write the raw value (`(rsm B X)`) and its clamp into
  `[1, N]` (`(rsc B X')`, via `clamp_i64`); join them with a repeated
  pattern variable. They unify exactly when clamping changed nothing.
  Out-of-range raw values survive as junk facts that never join.
- **X ≠ Y:** `ifnz` on X−Y, reified as a `(nself B M YES|NO)` fact and
  joined by pattern — the same reified-test idiom as the
  `symbolic_differentiation` simplifiers.

Numbers enter the space already clamped (the seeds are
`clamp(1, 1, N)` and `clamp(2, 1, N)`), so `(query 1)` demands nothing
beyond `(nat 1)` and yields no primes, with no special-casing.

## Scheduling

One driver instantiates the whole rule store once per entry of the
`(nextround r s)` table — a fixed sweep budget standing in for the
inexpressible "repeat until nothing changes" (MM2 has no negation, so
fixpoint detection is impossible; see the symbolic_differentiation
folder for the same pattern driven by tree depth instead). Because the
closures double their coverage each sweep, the shipped 15 rounds
support N into the thousands; each additional `(nextround ...)` line
buys another doubling.

Within a sweep, rule instances run in rule-name order, and MM2 compares
symbols length-first — so the store's dependency chain (`anat` feeds
`bcnd` feeds `ccnd`, …) uses uniform 4-character names in lexicographic
chain order. A shorter name anywhere in the chain would jump the queue
and cost a sweep of latency per stage.

Tag layout (shortlex on the exec tag):

```
(0 _) < (d0 (r k)) < (dz r) < (y1 _) < (y2 _) < (zzt _)
seeds   sweep rules  driver   add      subtract tests
```

## Limitations / possible extensions

- One `(query N)` per run: two queries' demands would merge soundly
  (each stays within its own bound) but the flat `(prime K)` output
  does not say which query a prime answers.
- The sweep budget is static. A dynamic budget would need a
  change-detection witness, which negation-free MM2 cannot express;
  sizing the `nextround` table to ⌈log₂ N⌉ + 4 is always enough.
- Primes-only sieving (the strict classical mechanism) needs
  stratified evaluation: run the difference step after each "layer" of
  bases and demand multiples only of survivors. Expressible with this
  folder's machinery plus staged tags, at the cost of the clean
  all-monotonic core.
