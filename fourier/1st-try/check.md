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

## Output format

One row per (m, n) pair, with three columns — one per strategy (interval,
balanced, parity tail) — containing:

- `y` if that strategy achieves the lowest FR among the three
- `n` otherwise

Ties are possible (e.g. balanced and parity tail coincide whenever m divides
m+n), in which case multiple columns show `y`.
