"""Newton's method for solving x^2 - 2 = 0 (approximate sqrt(2))."""


def newton_sqrt2(x0, steps):
    x = x0
    for i in range(steps):
        x = x - (x**2 - 2) / (2 * x)
        print(f"step {i+1}: x = {x:.12f}")
    return x


approx = newton_sqrt2(x0=1.0, steps=6)
print(f"\nFinal approximation of sqrt(2): {approx:.12f}")
