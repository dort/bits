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

    f = 1_A (x) 1_B + 1_B (x) 1_A with 1_B = 1 - 1_A, so with A[u] the 1D DFT
    of 1_A and S = sum_{u != 0} |A[u]| (see check.md):
        ||F||_1 = (2mn + 2(n-m)*S + 2*S^2) / N
        ||F||_2 = sqrt(2mn)  (unitarity)
    """
    m, n = len(m_labels), len(n_labels)
    N = m + n
    a = np.zeros(N)
    a[m_labels] = 1.0
    S = np.abs(np.fft.fft(a)[1:]).sum()
    l1 = (2 * m * n + 2 * (n - m) * S + 2 * S * S) / N
    return l1 / np.sqrt(2 * m * n)


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
