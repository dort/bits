"""Paper idea: FR(f) = ||f_hat||_1 / ||f_hat||_2, with 1 <= FR(f) <= sqrt(N)."""

import math

from fourier_utils import dft_unitary, fourier_ratio_from_signal


N = 16

# Example 1: constant signal
f_const = [1.0] * N
fr_const = fourier_ratio_from_signal(f_const)

# Example 2: delta signal at x=0
delta = [1.0] + [0.0] * (N - 1)
fr_delta = fourier_ratio_from_signal(delta)

# Example 3: short trigonometric sum (few frequencies)
f_trig = [
    math.cos(2 * math.pi * x / N) + 0.5 * math.sin(4 * math.pi * x / N)
    for x in range(N)
]
fr_trig = fourier_ratio_from_signal(f_trig)

print(f"N = {N}")
print(f"Lower/upper bound from paper: 1 <= FR(f) <= sqrt(N) = {math.sqrt(N):.4f}")
print(f"FR(constant) = {fr_const:.4f}")
print(f"FR(delta)    = {fr_delta:.4f}")
print(f"FR(trig sum) = {fr_trig:.4f}")

# Optional: inspect where Fourier mass lives for trig sum
F = dft_unitary(f_trig)
large = [(m, abs(Fm)) for m, Fm in enumerate(F) if abs(Fm) > 1e-6]
print("\nNon-negligible Fourier coefficients (index, magnitude):")
for m, mag in large:
    print(m, f"{mag:.4f}")
