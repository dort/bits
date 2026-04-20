"""
Example 10: Understanding Tracebacks and Debugging
==================================================

Key concepts:
- Reading and understanding tracebacks
- The traceback module for programmatic access
- Logging exceptions properly
- Debugging strategies

When your code crashes, Python gives you a "traceback" - a map showing
exactly where the error occurred. Learning to read it is essential.
"""

import traceback
import sys
import math

# -----------------------------------------------------------------------------
# READING A TRACEBACK
# -----------------------------------------------------------------------------

print("=" * 60)
print("PART 1: Understanding tracebacks")
print("=" * 60)

def level_3(x):
    """Deepest function - where the error actually occurs."""
    return math.sqrt(x)  # Will fail if x < 0

def level_2(x):
    """Middle function - processes and calls level_3."""
    result = level_3(x - 10)
    return result * 2

def level_1(x):
    """Top function - entry point."""
    return level_2(x * 2)

print("""
A traceback shows the call stack from bottom (most recent) to top.
Let's trigger an error by calling level_1(3):
  level_1(3) -> level_2(6) -> level_3(-4) -> sqrt(-4) -> ERROR!
""")

try:
    result = level_1(3)
except ValueError:
    print("Traceback (most recent call last):")
    traceback.print_exc()

print("""
How to read this traceback:
1. Start at the BOTTOM - that's where the error happened
2. Work your way UP to see how you got there
3. The error type and message are at the very bottom
4. Each level shows: file, line number, function name, and code
""")

# -----------------------------------------------------------------------------
# CAPTURING TRACEBACK INFORMATION
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 2: Capturing traceback programmatically")
print("=" * 60)

def risky_computation(values):
    """A function that might fail on some inputs."""
    results = []
    for v in values:
        results.append(1 / (v - 5))  # Fails when v == 5
    return results

try:
    result = risky_computation([1, 2, 5, 3])
except ZeroDivisionError:
    # Get exception info
    exc_type, exc_value, exc_tb = sys.exc_info()

    print(f"Exception Type: {exc_type.__name__}")
    print(f"Exception Message: {exc_value}")
    print(f"\nFormatted Traceback:")
    print("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))

    # Get just the traceback as a string (useful for logging)
    tb_string = traceback.format_exc()
    print(f"Traceback length: {len(tb_string)} characters")

# -----------------------------------------------------------------------------
# EXCEPTION CONTEXT IN REAL APPLICATIONS
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 3: Logging exceptions with context")
print("=" * 60)

def process_dataset(data):
    """
    Process a dataset, logging detailed error information.
    This pattern is essential for debugging batch jobs.
    """
    results = []
    errors = []

    for i, item in enumerate(data):
        try:
            # Some computation that might fail
            result = math.log(item["value"]) / item["divisor"]
            results.append({"index": i, "result": result})

        except Exception as e:
            # Capture rich error context
            error_info = {
                "index": i,
                "item": item,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc()
            }
            errors.append(error_info)

    return results, errors

# Create a dataset with some problematic entries
dataset = [
    {"value": 10, "divisor": 2},
    {"value": -5, "divisor": 1},     # log of negative
    {"value": 20, "divisor": 0},     # division by zero
    {"value": 100, "divisor": 4},
    {"value": "abc", "divisor": 1},  # type error
]

results, errors = process_dataset(dataset)

print(f"Successful: {len(results)}")
print(f"Errors: {len(errors)}")

print("\nError details:")
for error in errors:
    print(f"\n  Index {error['index']}: {error['error_type']}")
    print(f"  Item: {error['item']}")
    print(f"  Message: {error['error_message']}")

# -----------------------------------------------------------------------------
# DEBUGGING STRATEGIES
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 4: Debugging strategies")
print("=" * 60)

def numerical_integration_buggy(f, a, b, n):
    """
    Trapezoidal rule with a deliberate bug for demonstration.
    """
    h = (b - a) / n
    result = (f(a) + f(b)) / 2

    for i in range(1, n):
        x = a + i * h
        result += f(x)

    return result * h

def numerical_integration_debug(f, a, b, n, debug=False):
    """
    Same function with debug output.
    """
    h = (b - a) / n
    if debug:
        print(f"  DEBUG: h = {h}, a = {a}, b = {b}, n = {n}")

    result = (f(a) + f(b)) / 2
    if debug:
        print(f"  DEBUG: endpoints contribution = {result}")

    for i in range(1, n):
        x = a + i * h
        fx = f(x)
        if debug and i <= 3:  # Only show first few iterations
            print(f"  DEBUG: i={i}, x={x:.4f}, f(x)={fx:.4f}")
        result += fx

    final = result * h
    if debug:
        print(f"  DEBUG: final result = {final}")

    return final

# Test with a known integral: integral of x^2 from 0 to 1 = 1/3
print("Testing: integral of x^2 from 0 to 1 (exact = 0.3333...)")

for n in [10, 100, 1000]:
    result = numerical_integration_debug(lambda x: x**2, 0, 1, n, debug=(n == 10))
    error = abs(result - 1/3)
    print(f"  n={n}: result={result:.6f}, error={error:.2e}")

# -----------------------------------------------------------------------------
# ASSERTIONS FOR DEBUGGING
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 5: Using assertions for debugging")
print("=" * 60)

def matrix_is_square(M):
    """Check if a matrix is square."""
    if not M:
        return False
    return all(len(row) == len(M) for row in M)

def matrix_is_symmetric(M):
    """Check if a matrix is symmetric."""
    n = len(M)
    for i in range(n):
        for j in range(i + 1, n):
            if abs(M[i][j] - M[j][i]) > 1e-10:
                return False
    return True

def cholesky_decomposition(A):
    """
    Compute Cholesky decomposition of symmetric positive-definite matrix A.
    Returns lower triangular L such that A = L @ L^T.

    Uses assertions to catch programming errors early.
    """
    # Debug assertions - catch problems early
    assert matrix_is_square(A), "Matrix must be square"
    assert matrix_is_symmetric(A), "Matrix must be symmetric"

    n = len(A)
    L = [[0.0] * n for _ in range(n)]

    for i in range(n):
        for j in range(i + 1):
            if i == j:
                # Diagonal element
                sum_sq = sum(L[i][k] ** 2 for k in range(j))
                val = A[i][i] - sum_sq

                # This assertion catches non-positive-definite matrices
                assert val > 0, f"Matrix is not positive definite (failed at [{i}][{j}])"

                L[i][j] = math.sqrt(val)
            else:
                # Off-diagonal element
                sum_prod = sum(L[i][k] * L[j][k] for k in range(j))
                L[i][j] = (A[i][j] - sum_prod) / L[j][j]

    return L

# Test with a positive definite matrix
A = [
    [4, 2, 2],
    [2, 5, 1],
    [2, 1, 6]
]

print("Cholesky decomposition of A:")
try:
    L = cholesky_decomposition(A)
    print("  L = ")
    for row in L:
        print(f"    {[f'{x:.4f}' for x in row]}")

    # Verify: L @ L^T should equal A
    print("\n  Verification (L @ L^T):")
    for i in range(3):
        row = [sum(L[i][k] * L[j][k] for k in range(3)) for j in range(3)]
        print(f"    {[f'{x:.4f}' for x in row]}")
except AssertionError as e:
    print(f"  Assertion failed: {e}")

# Test with non-positive-definite matrix
print("\nAttempting Cholesky on non-positive-definite matrix:")
B = [
    [1, 2, 3],
    [2, 1, 4],
    [3, 4, 1]
]
try:
    L = cholesky_decomposition(B)
except AssertionError as e:
    print(f"  Assertion failed: {e}")

# -----------------------------------------------------------------------------
# SUMMARY: DEBUGGING CHECKLIST
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("DEBUGGING CHECKLIST")
print("=" * 60)
print("""
When you encounter an error:

1. READ THE TRACEBACK
   - Start from the bottom (the actual error)
   - Work upward to see the call chain
   - Note line numbers and function names

2. REPRODUCE THE ERROR
   - Find the smallest input that causes it
   - Isolate the problematic code

3. ADD DEBUG OUTPUT
   - Print intermediate values
   - Check types: print(type(x), x)
   - Verify loop indices and bounds

4. USE ASSERTIONS
   - assert condition, "message"
   - Check preconditions (function inputs)
   - Check postconditions (function outputs)
   - Check invariants (things that should stay true)

5. NARROW DOWN
   - Binary search: comment out half the code
   - Does the first half work? Then bug is in second half
   - Repeat until you find the exact line

6. CHECK COMMON ISSUES
   - Off-by-one errors in loops
   - Integer vs float division
   - Mutable default arguments
   - Variable shadowing
   - Operator precedence

7. TAKE A BREAK
   - Fresh eyes often spot the problem immediately
""")
