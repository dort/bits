"""Paper idea: small Fourier ratio implies good low-degree/sparse Fourier approximation."""

import math

from fourier_utils import dft_unitary, idft_unitary, l2_norm, top_k_approx_from_fourier


N = 64

# Build a signal from only 3 Fourier modes (exactly sparse in frequency)
F_true = [0j] * N
F_true[3] = 2.0 + 0j
F_true[N - 3] = 2.0 + 0j
F_true[9] = -1.0j

f = idft_unitary(F_true)
F = dft_unitary(f)

print(f"N = {N}")
print("Approximating f by keeping only k largest Fourier coefficients")

for k in [1, 2, 3, 5, 8]:
    Fk = top_k_approx_from_fourier(F, k)
    fk = idft_unitary(Fk)

    err = [a - b for a, b in zip(f, fk)]
    rel_l2 = l2_norm(err) / l2_norm(f)
    print(f"k={k:2d}  relative L2 error = {rel_l2:.6f}")
