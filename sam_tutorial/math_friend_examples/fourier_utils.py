"""Small Fourier helpers on Z_N using a unitary DFT convention."""

import cmath
import math


def dft_unitary(f):
    """Return the unitary DFT of f on Z_N."""
    n = len(f)
    out = []
    scale = 1 / math.sqrt(n)
    for m in range(n):
        s = 0j
        for x, fx in enumerate(f):
            s += fx * cmath.exp(-2j * math.pi * m * x / n)
        out.append(scale * s)
    return out


def idft_unitary(F):
    """Return the inverse unitary DFT on Z_N."""
    n = len(F)
    out = []
    scale = 1 / math.sqrt(n)
    for x in range(n):
        s = 0j
        for m, Fm in enumerate(F):
            s += Fm * cmath.exp(2j * math.pi * m * x / n)
        out.append(scale * s)
    return out


def l1_norm(v):
    return sum(abs(z) for z in v)


def l2_norm(v):
    return math.sqrt(sum(abs(z) ** 2 for z in v))


def fourier_ratio_from_signal(f):
    F = dft_unitary(f)
    return l1_norm(F) / l2_norm(F)


def support_size(v, tol=1e-9):
    return sum(1 for z in v if abs(z) > tol)


def top_k_approx_from_fourier(F, k):
    """Keep only k largest Fourier coefficients by magnitude."""
    n = len(F)
    indexed = list(enumerate(F))
    indexed.sort(key=lambda t: abs(t[1]), reverse=True)
    keep = {idx for idx, _ in indexed[:k]}
    out = [0j] * n
    for idx in keep:
        out[idx] = F[idx]
    return out
