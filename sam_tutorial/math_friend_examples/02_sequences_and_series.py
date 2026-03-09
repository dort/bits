"""Generate a sequence and compute partial sums."""


def harmonic_partial_sum(n):
    s = 0.0
    for k in range(1, n + 1):
        s += 1 / k
    return s


print("n   H_n")
for n in [1, 2, 3, 5, 10, 20]:
    print(f"{n:2d}  {harmonic_partial_sum(n):.6f}")


# Fibonacci sequence (first m terms)
def fibonacci(m):
    seq = [0, 1]
    while len(seq) < m:
        seq.append(seq[-1] + seq[-2])
    return seq[:m]


print("\nFirst 12 Fibonacci numbers:")
print(fibonacci(12))
