# Optimality Check — Fourier Ratio

Algorithm for checking the labeling strategies (see setup.md) for optimality
and comparing them with each other. Definitions accumulate as they are
provided; open questions are tracked at the bottom.

## Definitions

Let N = m + n, the total number of labels. A labeling partitions
{0, .., N-1} into the m-set's labels A and the n-set's labels B.

### Edge indicator function f

For a given labeling, define f on pairs of labels x, y ∈ {0, .., N-1}:

- f(x, y) = 1 if x and y lie in opposite sets of the partition
  (x ∈ A and y ∈ B, or x ∈ B and y ∈ A)
- f(x, y) = 0 otherwise

f is the adjacency matrix of the complete bipartite graph between the two
label sets, indexed by label value. It is symmetric and has exactly 2mn
entries equal to 1.

### Fourier transform F

F is the **unitary Fourier transform of f over the group (Z_N)²**:

F(u, v) = (1/N) · Σ_{x=0}^{N-1} Σ_{y=0}^{N-1} f(x, y) · e^{-2πi(ux + vy)/N}

The 1/N factor (i.e. 1/√N per axis) makes the transform unitary, so
‖F‖₂ = ‖f‖₂.

### Fourier ratio FR(f)

FR(f) = ‖F‖₁ / ‖F‖₂

where ‖F‖₁ = Σ_{u,v} |F(u, v)| and ‖F‖₂ = √(Σ_{u,v} |F(u, v)|²).

By unitarity, ‖F‖₂ = ‖f‖₂ = √(2mn) regardless of which labeling is chosen,
so comparing FR across labelings of the same (m, n) compares ‖F‖₁ alone.
FR measures how spread out the spectrum is: it is minimized (value 1) when F
is supported on a single point and grows as the mass of F spreads over more
frequencies.

## Computation algorithm

For each (m, n) pair and each strategy:

1. Build the labeling's label sets A (m-set) and B (n-set).
2. Build the N×N matrix f with f[x, y] = 1 iff x, y are in opposite sets.
3. Compute the 2D FFT of f and divide by N to get the unitary transform F.
4. FR = (Σ |F|) / √(Σ |F|²).
5. Compare FR across the three strategies for that (m, n): **smaller FR is
   optimal**. The strategy (or strategies, on a tie) with the lowest FR of
   the three wins.

## Fast evaluation (closed form)

Let 1_A be the indicator vector of the m-set's labels A, Â(u) its
unnormalized 1D DFT (so Â(0) = m), and S = Σ_{u=1}^{N-1} |Â(u)| the total
spectral mass of 1_A off the zero frequency. Since 1_B = 1 − 1_A, the DFT of
1_B is B̂(u) = N·δ_{u0} − Â(u), and substituting into
F(u, v) = (Â(u)B̂(v) + B̂(u)Â(v)) / N gives, entry by entry:

- u = v = 0: |F| = 2mn/N
- u ≠ 0, v = 0 (and symmetrically u = 0, v ≠ 0): |F| = (n−m)|Â(u)|/N
- u ≠ 0, v ≠ 0: |F| = 2|Â(u)||Â(v)|/N, which sums to 2S²/N

Therefore

‖F‖₁ = (2mn + 2(n−m)·S + 2S²) / N,  ‖F‖₂ = √(2mn)

and FR needs only one length-N FFT per labeling instead of an N×N transform.
Verified: at MAXIMUM = 100 this reproduces the direct 2D computation's
results exactly.

## Findings: when is parity tail the sole winner?

Empirical analysis of the MAXIMUM = 1000 run (248,502 pairs; 30,884 sole
parity-tail wins). Write N = m+n, q = floor(N/m) (parity tail's stride), and
r = N mod m, so N = qm + r.

### Necessary condition: gcd(q, r) > 1

Let d = gcd(q, r), which equals gcd(q, N) since gcd(q, qm + r) = gcd(q, r).
**Every sole parity-tail win has d > 1** — zero exceptions among the 30,884
sole wins, and none of the 142,002 pairs with d = 1 (and r ≠ 0) is one.

Mechanism: parity tail's labels 0, q, 2q, .., (m−1)q are all multiples of q,
hence of d, so the m-set lies inside the subgroup dZ_N of multiples of d.
For a set confined to that subgroup, the DFT Â(u) is periodic in u with
period N/d — the spectrum collapses onto d identical copies of a length-N/d
spectrum — and within the subgroup the labels form again a near-subgroup
arithmetic progression (step q/d, deficit r/d). This alignment concentrates
spectral mass, which shrinks ‖F‖₁ and hence FR. The balanced strategy
spreads its labels maximally evenly for every (m, n) alike, so it cannot
exploit the arithmetic coincidence; when d > 1, parity tail's spectrum is
strictly more concentrated and it can win outright.

### Not sufficient: win rate grows with d, prime d strongest

| d = gcd(q, r) | sole-win rate among eligible pairs |
|---|---|
| 1 | 0% (never) |
| 2 | 23% |
| 3 | 34% |
| 4 | 36% |
| 5 | 52% |
| 6 | 40% |
| 7 | 67% |
| 8 | 55% |
| 9 | 61% |
| 11 | 76% |

### Corollaries

- r = 1 never yields a sole win: gcd(q, 1) = 1 forces d = 1.
- r = 0 cannot either: balanced and parity tail coincide there (tie).
- Prime r is rare among sole wins because d > 1 with r prime requires r | q.
- d > 1 is the gate, not the whole law: residual dependence on m remains
  (m = 3, 4, and 5 never produce sole wins even when d > 1).

## Output format

One row per (m, n) pair, with three columns — one per strategy (interval,
balanced, parity tail) — containing:

- `y` if that strategy achieves the lowest FR among the three
- `n` otherwise

Ties are possible (e.g. balanced and parity tail coincide whenever m divides
m+n), in which case multiple columns show `y`.
