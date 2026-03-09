"""Paper theme: Fourier ratio controls uncertainty; support products cannot be too small."""

from fourier_utils import dft_unitary, support_size


def indicator_signal(N, support):
    S = set(support)
    return [1.0 if x in S else 0.0 for x in range(N)]


N = 24
examples = {
    "delta": indicator_signal(N, [0]),
    "two points": indicator_signal(N, [0, 1]),
    "periodic subgroup-like": indicator_signal(N, [0, 6, 12, 18]),
}

print(f"N = {N}")
for name, f in examples.items():
    F = dft_unitary(f)
    s_time = support_size(f)
    s_freq = support_size(F)
    print(f"\n{name}")
    print(f"|supp(f)| = {s_time}")
    print(f"|supp(f_hat)| = {s_freq}")
    print(f"Product = {s_time * s_freq}")
