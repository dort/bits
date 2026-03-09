# Python Code Documentation for `sam_tutorial/`

This document covers all Python files currently located under `sam_tutorial/`.

## Files Covered

1. `math_friend_examples/01_functions_and_numbers.py`
2. `math_friend_examples/02_sequences_and_series.py`
3. `math_friend_examples/03_matrices_as_lists.py`
4. `math_friend_examples/04_newton_method.py`
5. `math_friend_examples/05_points_vectors_and_triangles.py`
6. `math_friend_examples/06_transformations_in_plane.py`
7. `math_friend_examples/07_polygon_shoelace.py`
8. `math_friend_examples/fourier_utils.py`
9. `math_friend_examples/08_fourier_ratio_basics.py`
10. `math_friend_examples/09_bi_fourier_ratio_subgroup.py`
11. `math_friend_examples/10_uncertainty_support_demo.py`
12. `math_friend_examples/11_sparse_spectrum_approximation.py`

## Environment and Execution

1. Python version: Python 3.10+ is recommended.
2. Dependencies: standard library only (`math`, `cmath`). No external packages required.
3. Run command format:

```bash
python3 sam_tutorial/math_friend_examples/<filename.py>
```

4. Import note: scripts `08` to `11` import `fourier_utils.py`, so run them by file path exactly as above or from inside `sam_tutorial/math_friend_examples/`.

## Shared Design Principles

1. Keep code short and inspectable.
2. Prefer explicit loops and simple data structures (lists, tuples, sets).
3. Use deterministic examples with fixed constants for reproducible output.
4. Emphasize mathematical interpretation alongside coding patterns.

## 1) `01_functions_and_numbers.py`

### Purpose
Introduces basic Python function definitions, arithmetic expressions, loops, and string formatting.

### Main Ideas
1. Function definition with `def`.
2. Polynomial evaluation.
3. Computational verification of algebraic identity.

### Key Code Components
1. `f(x)` computes `x**2 + 2*x + 1`.
2. First loop prints `f(x)` over sample integer inputs.
3. Second loop checks `x^2 + 2x + 1 == (x+1)^2` for `x in [-5, ..., 5]`.

### Mathematical Context
This script demonstrates the expanded and factored forms of a perfect square, linking symbolic algebra to programmatic evaluation.

### Suggested Extensions
1. Replace `f` by a cubic and inspect finite differences.
2. Compare `f(x)` and `(x+1)**2` on random integers.
3. Add checks for other identities such as `(x-y)^2`.

## 2) `02_sequences_and_series.py`

### Purpose
Demonstrates iterative sequence generation and partial sums.

### Main Ideas
1. Harmonic numbers `H_n = sum_{k=1}^n 1/k`.
2. Fibonacci recurrence.

### Key Code Components
1. `harmonic_partial_sum(n)` uses a `for` loop accumulator.
2. `fibonacci(m)` grows a list using the last two terms.

### Mathematical Context
1. Harmonic sums are a canonical slowly diverging series.
2. Fibonacci numbers are a standard linear recurrence example.

### Suggested Extensions
1. Plot `H_n - log(n)` for larger `n`.
2. Implement closed-form Binet approximation and compare errors.
3. Add Lucas sequence with same recurrence and different seeds.

## 3) `03_matrices_as_lists.py`

### Purpose
Implements matrix addition and multiplication from scratch using nested lists.

### Main Ideas
1. Matrix as list-of-lists.
2. Index-based dimension handling.
3. Triple-index structure in matrix multiplication.

### Key Code Components
1. `mat_add(X, Y)` uses list comprehensions for elementwise sum.
2. `mat_mul(X, Y)` computes each output entry as a dot product.

### Mathematical Context
Shows the row-by-column rule explicitly without linear algebra libraries.

### Limitations
1. No shape validation is performed.
2. Intended for teaching and small matrices only.

### Suggested Extensions
1. Add shape checks and clear error messages.
2. Implement matrix-vector multiplication.
3. Add determinant for `2x2` and `3x3` cases.

## 4) `04_newton_method.py`

### Purpose
Shows Newton's method for numerically approximating `sqrt(2)`.

### Main Ideas
1. Root finding for `g(x) = x^2 - 2`.
2. Update rule `x <- x - g(x)/g'(x)`.
3. Rapid convergence near the root.

### Key Code Components
1. `newton_sqrt2(x0, steps)` runs fixed-count iterations.
2. Per-step printing illustrates convergence trajectory.

### Mathematical Context
For `g(x)=x^2-2`, the update simplifies to `(x + 2/x)/2`, converging quadratically for reasonable starting values.

### Suggested Extensions
1. Add stopping criterion based on tolerance.
2. Guard against division by zero.
3. Generalize to Newton solver for arbitrary `g` and `g'`.

## 5) `05_points_vectors_and_triangles.py`

### Purpose
Introduces 2D Euclidean geometry primitives using tuples.

### Main Ideas
1. Distance between two points.
2. Dot product of vectors.
3. Triangle area from 2D cross-product magnitude.

### Key Code Components
1. `dist(P, Q)` uses `math.hypot`.
2. `dot(u, v)` computes scalar product.
3. `sub(P, Q)` forms vector `P - Q`.
4. `triangle_area(A, B, C)` uses determinant-based area formula.

### Mathematical Context
Area formula is `0.5 * |det(B-A, C-A)|`, invariant under translation.

### Suggested Extensions
1. Compute triangle angles via dot products.
2. Add orientation test via signed determinant.
3. Detect collinearity when area is near zero.

## 6) `06_transformations_in_plane.py`

### Purpose
Demonstrates basic plane transformations (isometries) on triangle vertices.

### Main Ideas
1. Translation by vector addition.
2. Rotation around origin by angle `theta`.
3. Reflection across x-axis.

### Key Code Components
1. `translate(P, v)`.
2. `rotate(P, theta)` with rotation matrix.
3. `reflect_x_axis(P)`.
4. `fmt(P)` for rounded coordinate printing.

### Mathematical Context
1. Translations and rotations preserve distances.
2. Reflection preserves distances but reverses orientation.

### Suggested Extensions
1. Compose transformations and verify non-commutativity.
2. Rotate around an arbitrary center.
3. Track signed area before and after reflection.

## 7) `07_polygon_shoelace.py`

### Purpose
Computes polygon signed area and orientation using the shoelace formula.

### Main Ideas
1. Signed area from cyclic vertex pairs.
2. Orientation from sign of signed area.

### Key Code Components
1. `signed_area(poly)` loops over edges `(i, i+1 mod n)`.
2. `orientation(poly)` returns `counterclockwise`, `clockwise`, or `degenerate`.

### Mathematical Context
Signed area equals half the sum of wedge products `x_i y_{i+1} - y_i x_{i+1}`.

### Suggested Extensions
1. Reorder vertices and observe orientation change.
2. Add convexity check using edge cross-product signs.
3. Compute centroid for simple polygons.

## 8) `fourier_utils.py`

### Purpose
Provides reusable Fourier-analysis helpers used by scripts `08` to `11`.

### Main Ideas
1. Unitary DFT and inverse DFT on `Z_N`.
2. Basic norms and support counting.
3. Hard-threshold sparse approximation in frequency.

### API Reference
1. `dft_unitary(f)`
Computes
`F[m] = (1/sqrt(N)) * sum_x f[x] * exp(-2*pi*i*m*x/N)`.

2. `idft_unitary(F)`
Computes
`f[x] = (1/sqrt(N)) * sum_m F[m] * exp(+2*pi*i*m*x/N)`.

3. `l1_norm(v)`
Returns `sum(abs(v_i))`.

4. `l2_norm(v)`
Returns `sqrt(sum(abs(v_i)^2))`.

5. `fourier_ratio_from_signal(f)`
Returns `||f_hat||_1 / ||f_hat||_2`.

6. `support_size(v, tol=1e-9)`
Counts entries with magnitude greater than `tol`.

7. `top_k_approx_from_fourier(F, k)`
Keeps only the `k` largest Fourier coefficients by magnitude.

### Complexity Notes
1. `dft_unitary` and `idft_unitary` are `O(N^2)` (naive DFT), chosen for transparency.
2. FFT is not used to keep formulas explicit.

## 9) `08_fourier_ratio_basics.py`

### Purpose
Introduces Fourier ratio and numerically checks canonical bounds.

### Main Ideas
1. `FR(f) = ||f_hat||_1 / ||f_hat||_2`.
2. Basic bound `1 <= FR(f) <= sqrt(N)`.
3. Comparison across three signal types.

### Key Code Components
1. Constant signal example (`FR` near lower bound).
2. Delta signal example (`FR` near upper bound).
3. Short trigonometric sum with few dominant frequencies.
4. Prints non-negligible Fourier coefficients for interpretability.

### Interpretation
Smaller `FR` indicates stronger Fourier concentration; larger `FR` indicates more spread spectrum.

### Suggested Extensions
1. Sweep over random signals and histogram `FR` values.
2. Compare real-valued versus complex-valued constructions.
3. Increase `N` and inspect scaling trends.

## 10) `09_bi_fourier_ratio_subgroup.py`

### Purpose
Demonstrates the paper’s bi-Fourier-ratio idea on a subgroup-like indicator in `Z_{pq}`.

### Main Ideas
1. Build indicator of embedded `Z_p` inside `Z_{pq}`.
2. Compute `FR(f)`, `FR(f_hat)`, and `FR_bi(f)=min(FR(f), FR(f_hat))`.
3. Compare with scales `sqrt(N/p)=sqrt(q)` and `sqrt(N/q)=sqrt(p)`.

### Key Code Components
1. `p=3`, `q=11`, `N=33`.
2. Support set `E={0,q,2q,...,(p-1)q}`.
3. Prints all ratios and reference scales.

### Interpretation
Shows how `FR_bi` can better capture complexity when `f` and `f_hat` are both computationally accessible.

### Suggested Extensions
1. Try multiple prime pairs `(p,q)`.
2. Swap roles of `p` and `q` and compare asymmetry.
3. Build similar examples with unions of cosets.

## 11) `10_uncertainty_support_demo.py`

### Purpose
Provides a finite-group support-size experiment related to uncertainty phenomena.

### Main Ideas
1. Build indicator signals of different support patterns.
2. Measure support size in time and frequency domains.
3. Compare support product `|supp(f)| * |supp(f_hat)|`.

### Key Code Components
1. `indicator_signal(N, support)` helper.
2. Three examples: delta, two points, periodic subgroup-like support.
3. Uses tolerance-based support count in Fourier domain.

### Interpretation
Illustrates that shrinking support in one domain typically enlarges support in the other domain.

### Suggested Extensions
1. Randomly sample supports of fixed size and compare products.
2. Track how the product behaves for arithmetic progressions.
3. Test sensitivity to the `tol` threshold.

## 12) `11_sparse_spectrum_approximation.py`

### Purpose
Demonstrates sparse Fourier approximation quality as a function of retained coefficient count `k`.

### Main Ideas
1. Construct signal from exactly sparse spectrum.
2. Keep top-`k` Fourier coefficients.
3. Measure relative `L2` reconstruction error.

### Key Code Components
1. `F_true` has only three nonzero modes.
2. `f = idft_unitary(F_true)` builds time-domain signal.
3. Loop over `k in [1,2,3,5,8]` computes approximation errors.

### Interpretation
Error drops to zero once `k` reaches the true spectral sparsity level.

### Suggested Extensions
1. Add noise in frequency or time domain and re-evaluate.
2. Replace hard thresholding with soft thresholding.
3. Use less sparse spectra and compare decay curves.

## How to Use This Set for Teaching

1. Start with files `01` to `04` for core Python syntax and numerical thinking.
2. Use `05` to `07` for geometric intuition in Euclidean plane.
3. Move to `08` to `11` for discrete Fourier ideas connected to complexity and structure.
4. Encourage modifications of constants and input sets to build intuition by experimentation.

## Known Limitations and Scope

1. Scripts are educational and not optimized for large-scale numerical workloads.
2. No command-line argument parsing is included.
3. Naive DFT implementation is intentionally explicit, not FFT-accelerated.
4. Most files are script-style examples rather than reusable modules.

