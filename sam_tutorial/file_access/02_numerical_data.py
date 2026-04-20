"""
Example 2: Reading and Writing Numerical Data
==============================================

Key concepts:
- Converting between strings and numbers (int, float)
- Formatting numbers for output
- Storing computation results

Critical insight: Files store TEXT (strings), not numbers directly.
When you write 3.14159, it becomes the characters '3', '.', '1', '4', '1', '5', '9'.
When reading, you must convert back: float("3.14159") -> 3.14159
"""

import math

# -----------------------------------------------------------------------------
# WRITING NUMERICAL RESULTS
# -----------------------------------------------------------------------------

# Let's compute and store the first 20 terms of e^x Taylor series at x=1
# e^x = sum_{n=0}^{infinity} x^n / n!

def factorial(n):
    """Compute n! recursively (not efficient, but mathematically clear)"""
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def taylor_term(x, n):
    """Compute the nth term of e^x Taylor series: x^n / n!"""
    return (x ** n) / factorial(n)

x = 1.0
terms = 20

with open("taylor_series.txt", "w") as f:
    # Write a header
    f.write(f"Taylor series approximation of e^{x}\n")
    f.write(f"{'n':>4} {'term':>20} {'partial_sum':>20} {'error':>20}\n")
    f.write("-" * 66 + "\n")

    partial_sum = 0.0
    true_value = math.e ** x

    for n in range(terms):
        term = taylor_term(x, n)
        partial_sum += term
        error = abs(true_value - partial_sum)

        # Format numbers with consistent precision
        # :>20 means right-align in 20 characters
        # :.15f means 15 decimal places
        f.write(f"{n:>4} {term:>20.15f} {partial_sum:>20.15f} {error:>20.2e}\n")

print("Taylor series results written to 'taylor_series.txt'")

# -----------------------------------------------------------------------------
# READING NUMERICAL DATA
# -----------------------------------------------------------------------------

print("\n--- Reading back the numerical data ---")

with open("taylor_series.txt", "r") as f:
    # Skip the header lines
    header1 = f.readline()
    header2 = f.readline()
    separator = f.readline()

    print(f"Header: {header1.strip()}")
    print()

    # Read and parse the data lines
    for line in f:
        parts = line.split()  # Split on whitespace
        if len(parts) == 4:
            n = int(parts[0])           # Convert string to integer
            term = float(parts[1])       # Convert string to float
            partial_sum = float(parts[2])
            error = float(parts[3])

            # Now we have actual numbers we can compute with!
            if n % 5 == 0:  # Print every 5th term
                print(f"n={n}: partial_sum = {partial_sum:.10f}, error = {error:.2e}")

# -----------------------------------------------------------------------------
# WRITING A SIMPLE DATA FILE (one number per line)
# -----------------------------------------------------------------------------

# Generate first 50 prime numbers and save them
def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True

primes = []
candidate = 2
while len(primes) < 50:
    if is_prime(candidate):
        primes.append(candidate)
    candidate += 1

with open("primes.txt", "w") as f:
    for p in primes:
        f.write(f"{p}\n")  # One number per line

print(f"\nFirst 50 primes written to 'primes.txt'")

# Reading them back into a list
with open("primes.txt", "r") as f:
    primes_from_file = [int(line.strip()) for line in f]
    # This is a "list comprehension" - a concise way to build lists

print(f"Read back {len(primes_from_file)} primes: {primes_from_file[:10]}...")

# Verify: sum of first 50 primes
print(f"Sum of first 50 primes: {sum(primes_from_file)}")

# -----------------------------------------------------------------------------
# WRITING MULTIPLE VALUES PER LINE
# -----------------------------------------------------------------------------

# Store (x, sin(x), cos(x)) for x in [0, 2*pi] with 100 points
import math

with open("trig_table.txt", "w") as f:
    f.write("# x, sin(x), cos(x)\n")  # Comment line (we'll skip lines starting with #)

    for i in range(101):
        x = 2 * math.pi * i / 100
        f.write(f"{x:.6f},{math.sin(x):.6f},{math.cos(x):.6f}\n")

print("\nTrig table written to 'trig_table.txt'")

# Reading comma-separated values
with open("trig_table.txt", "r") as f:
    x_vals, sin_vals, cos_vals = [], [], []

    for line in f:
        if line.startswith("#"):  # Skip comment lines
            continue
        parts = line.strip().split(",")  # Split on comma
        x_vals.append(float(parts[0]))
        sin_vals.append(float(parts[1]))
        cos_vals.append(float(parts[2]))

# Verify the Pythagorean identity: sin^2(x) + cos^2(x) = 1
max_deviation = max(abs(s**2 + c**2 - 1) for s, c in zip(sin_vals, cos_vals))
print(f"Max deviation from sin²(x) + cos²(x) = 1: {max_deviation:.2e}")
