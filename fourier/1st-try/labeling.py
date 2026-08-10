"""Labeling strategies for two sets of cardinality m and n (m < n).

Assigns the integers 0 .. m+n-1 bijectively across the two sets.
See setup.md for the full specification.
"""

# Bounds m + n. Hard upper limit is 1_000_000; initial runs use 100.
MAXIMUM = 100
HARD_BOUND = 1_000_000


def interval(m, n):
    """m-set: 0 .. m-1; n-set: m .. m+n-1."""
    return list(range(m)), list(range(m, m + n))


def balanced(m, n):
    """m-set: floor(k*(m+n)/m) for k = 0 .. m-1; n-set: the rest."""
    m_labels = [k * (m + n) // m for k in range(m)]
    n_labels = sorted(set(range(m + n)) - set(m_labels))
    return m_labels, n_labels


def parity_tail(m, n):
    """m-set: k*floor((m+n)/m) for k = 0 .. m-1; n-set: the rest."""
    step = (m + n) // m
    m_labels = [k * step for k in range(m)]
    n_labels = sorted(set(range(m + n)) - set(m_labels))
    return m_labels, n_labels


STRATEGIES = [
    ("interval", interval),
    ("balanced", balanced),
    ("parity tail", parity_tail),
]


def all_pairs(maximum):
    """All (m, n) with 2 <= m < n and m + n <= maximum."""
    for m in range(2, maximum // 2 + 1):
        for n in range(m + 1, maximum - m + 1):
            yield m, n


def main():
    if MAXIMUM > HARD_BOUND:
        raise ValueError(f"MAXIMUM={MAXIMUM} exceeds hard bound {HARD_BOUND}")
    for m, n in all_pairs(MAXIMUM):
        print(f"m={m} n={n}")
        for name, strategy in STRATEGIES:
            m_labels, n_labels = strategy(m, n)
            assert sorted(m_labels + n_labels) == list(range(m + n))
            print(f"  {name}:")
            print(f"    m-set: {' '.join(map(str, m_labels))}")
            print(f"    n-set: {' '.join(map(str, n_labels))}")
        print()


if __name__ == "__main__":
    main()
