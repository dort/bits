"""Compare the labeling strategies by Fourier ratio FR(f).

For each (m, n) pair, computes FR(f) for the three strategies in labeling.py
and prints y in the column(s) achieving the lowest FR, n otherwise.
Smaller FR is optimal. See check.md for the definitions.
"""

import numpy as np

from labeling import MAXIMUM, STRATEGIES, all_pairs

# Relative tolerance when deciding whether two FR values tie for the minimum.
TIE_RTOL = 1e-9


def fourier_ratio(m_labels, n_labels):
    """FR(f) = ||F||_1 / ||F||_2 for the edge indicator f of the labeling.

    f = 1_A (x) 1_B + 1_B (x) 1_A, so F(u, v) = (A[u]*B[v] + B[u]*A[v]) / N
    where A, B are the 1D DFTs of the indicator vectors of the two label sets.
    """
    N = len(m_labels) + len(n_labels)
    a = np.zeros(N)
    b = np.zeros(N)
    a[m_labels] = 1.0
    b[n_labels] = 1.0
    A = np.fft.fft(a)
    B = np.fft.fft(b)
    F = (np.outer(A, B) + np.outer(B, A)) / N
    mag = np.abs(F)
    return mag.sum() / np.sqrt((mag ** 2).sum())


def main():
    names = [name for name, _ in STRATEGIES]
    print("m n " + " ".join(names))
    for m, n in all_pairs(MAXIMUM):
        ratios = [fourier_ratio(*strategy(m, n)) for _, strategy in STRATEGIES]
        best = min(ratios)
        flags = ["y" if r <= best * (1 + TIE_RTOL) else "n" for r in ratios]
        print(f"{m} {n} " + " ".join(flags))


if __name__ == "__main__":
    main()
