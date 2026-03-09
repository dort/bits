"""Basic functions, arithmetic, and a tiny proof-by-computation style check."""


def f(x):
    # f(x) = x^2 + 2x + 1
    return x**2 + 2 * x + 1


# Evaluate f at a few values
for x in [-2, -1, 0, 1, 2, 3]:
    print(f"x={x:2d}  f(x)={f(x):2d}")

print("\nIdentity check: x^2 + 2x + 1 == (x + 1)^2")
for x in range(-5, 6):
    left = x**2 + 2 * x + 1
    right = (x + 1) ** 2
    print(f"x={x:2d}: {left == right}")
