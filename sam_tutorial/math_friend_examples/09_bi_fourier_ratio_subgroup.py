"""Paper idea: bi-Fourier ratio FR_bi(f) = min(FR(f), FR(f_hat))."""

import math

from fourier_utils import dft_unitary, fourier_ratio_from_signal


# Work on Z_N with N = p*q
p = 3
q = 11
N = p * q

# Embed Z_p inside Z_{pq} as E = {0, q, 2q, ..., (p-1)q}
E = {k * q for k in range(p)}
f = [1.0 if x in E else 0.0 for x in range(N)]

F = dft_unitary(f)
fr_f = fourier_ratio_from_signal(f)
fr_F = fourier_ratio_from_signal(F)  # FR(f_hat)
fr_bi = min(fr_f, fr_F)

print(f"N = {N}, p = {p}, q = {q}")
print(f"|E| = {len(E)}")
print(f"FR(f)       = {fr_f:.4f}")
print(f"FR(f_hat)   = {fr_F:.4f}")
print(f"FR_bi(f)    = {fr_bi:.4f}")

# Heuristic comparisons discussed in the paper's subgroup example
print("\nReference scales:")
print(f"sqrt(N/p) = sqrt(q) = {math.sqrt(q):.4f}")
print(f"sqrt(N/q) = sqrt(p) = {math.sqrt(p):.4f}")
