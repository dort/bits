"""
Example 8: Raising Exceptions and Custom Exception Classes
==========================================================

Key concepts:
- raise statement to throw exceptions
- Creating custom exception classes
- When and why to raise exceptions
- Exception chaining

Mathematical analogy: Raising an exception is like asserting a contradiction.
When you raise ValueError("Matrix is singular"), you're saying
"the computation cannot proceed because a necessary condition is violated."
"""

import math

# -----------------------------------------------------------------------------
# RAISING BUILT-IN EXCEPTIONS
# -----------------------------------------------------------------------------

print("=" * 60)
print("PART 1: Raising built-in exceptions")
print("=" * 60)

def factorial(n):
    """
    Compute n! with input validation.
    Raises ValueError for invalid input.
    """
    # Validate input BEFORE computing
    if not isinstance(n, int):
        raise TypeError(f"factorial requires an integer, got {type(n).__name__}")
    if n < 0:
        raise ValueError(f"factorial is not defined for negative numbers: {n}")

    # Now we know n is a non-negative integer
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result

# Test valid inputs
print(f"5! = {factorial(5)}")
print(f"0! = {factorial(0)}")

# Test invalid inputs (wrapped in try/except)
for bad_input in [-1, 3.5, "five"]:
    try:
        result = factorial(bad_input)
    except (ValueError, TypeError) as e:
        print(f"factorial({bad_input!r}) raised {type(e).__name__}: {e}")

# -----------------------------------------------------------------------------
# WHEN TO RAISE EXCEPTIONS
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 2: When to raise exceptions")
print("=" * 60)

def solve_linear_system(A, b):
    """
    Solve Ax = b for a 2x2 system using Cramer's rule.

    Raises exceptions when the problem is ill-defined.
    """
    # Validate dimensions
    if len(A) != 2 or len(A[0]) != 2:
        raise ValueError(f"A must be 2x2, got {len(A)}x{len(A[0]) if A else 0}")

    if len(b) != 2:
        raise ValueError(f"b must have 2 elements, got {len(b)}")

    # Check for singular matrix
    det_A = A[0][0] * A[1][1] - A[0][1] * A[1][0]
    if abs(det_A) < 1e-10:
        raise ValueError("Matrix is singular (det ≈ 0), system has no unique solution")

    # Cramer's rule
    x = (b[0] * A[1][1] - b[1] * A[0][1]) / det_A
    y = (A[0][0] * b[1] - A[1][0] * b[0]) / det_A

    return [x, y]

# Valid system
A = [[2, 1], [1, 3]]
b = [5, 5]
print(f"System: {A}x = {b}")
print(f"Solution: {solve_linear_system(A, b)}")

# Singular system
print("\nSingular system:")
try:
    A_singular = [[1, 2], [2, 4]]  # Row 2 = 2 * Row 1
    solve_linear_system(A_singular, [1, 2])
except ValueError as e:
    print(f"  Caught: {e}")

# Wrong dimensions
print("\nWrong dimensions:")
try:
    solve_linear_system([[1, 2, 3], [4, 5, 6]], [1, 2])
except ValueError as e:
    print(f"  Caught: {e}")

# -----------------------------------------------------------------------------
# CUSTOM EXCEPTION CLASSES
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 3: Custom exception classes")
print("=" * 60)

# Custom exceptions should inherit from Exception (or a subclass)

class MathematicalError(Exception):
    """Base class for mathematical exceptions in our library."""
    pass

class ConvergenceError(MathematicalError):
    """Raised when an iterative algorithm fails to converge."""

    def __init__(self, message, iterations, last_value):
        super().__init__(message)
        self.iterations = iterations
        self.last_value = last_value

class DomainError(MathematicalError):
    """Raised when input is outside the valid domain."""

    def __init__(self, message, value, valid_domain):
        super().__init__(message)
        self.value = value
        self.valid_domain = valid_domain

def newton_sqrt(x, tolerance=1e-10, max_iterations=100):
    """
    Compute sqrt(x) using Newton's method.
    Raises custom exceptions for invalid input or non-convergence.
    """
    if x < 0:
        raise DomainError(
            f"sqrt is not defined for negative numbers in reals",
            value=x,
            valid_domain="[0, ∞)"
        )

    if x == 0:
        return 0.0

    # Newton's method: x_{n+1} = (x_n + a/x_n) / 2
    guess = x / 2  # Initial guess
    for i in range(max_iterations):
        new_guess = (guess + x / guess) / 2
        if abs(new_guess - guess) < tolerance:
            return new_guess
        guess = new_guess

    # If we get here, we didn't converge
    raise ConvergenceError(
        f"Newton's method did not converge after {max_iterations} iterations",
        iterations=max_iterations,
        last_value=guess
    )

# Test successful computation
print(f"newton_sqrt(2) = {newton_sqrt(2)}")
print(f"Verification: {newton_sqrt(2)**2}")

# Test domain error
print("\nTesting domain error:")
try:
    newton_sqrt(-4)
except DomainError as e:
    print(f"  DomainError: {e}")
    print(f"  Input value: {e.value}")
    print(f"  Valid domain: {e.valid_domain}")

# Test convergence error (artificially)
print("\nTesting convergence error:")
try:
    # Very few iterations to force non-convergence
    newton_sqrt(2, max_iterations=2)
except ConvergenceError as e:
    print(f"  ConvergenceError: {e}")
    print(f"  Iterations attempted: {e.iterations}")
    print(f"  Last value: {e.last_value}")

# -----------------------------------------------------------------------------
# EXCEPTION CHAINING
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 4: Exception chaining (raise from)")
print("=" * 60)

class MatrixError(Exception):
    """Error in matrix operations."""
    pass

def invert_2x2(matrix):
    """Invert a 2x2 matrix, with exception chaining."""
    try:
        a, b = matrix[0]
        c, d = matrix[1]
        det = a*d - b*c

        if det == 0:
            raise ZeroDivisionError("Determinant is zero")

        return [[d/det, -b/det], [-c/det, a/det]]

    except (IndexError, TypeError) as e:
        # Chain the original exception for debugging
        raise MatrixError("Invalid matrix format") from e

    except ZeroDivisionError as e:
        raise MatrixError("Matrix is not invertible") from e

# Valid matrix
print("Inverting [[1, 2], [3, 4]]:")
inv = invert_2x2([[1, 2], [3, 4]])
print(f"  Result: {inv}")

# Invalid format
print("\nInverting 'not a matrix':")
try:
    invert_2x2("not a matrix")
except MatrixError as e:
    print(f"  MatrixError: {e}")
    print(f"  Caused by: {e.__cause__}")

# Singular matrix
print("\nInverting [[1, 2], [2, 4]]:")
try:
    invert_2x2([[1, 2], [2, 4]])
except MatrixError as e:
    print(f"  MatrixError: {e}")
    print(f"  Caused by: {e.__cause__}")

# -----------------------------------------------------------------------------
# RE-RAISING EXCEPTIONS
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 5: Re-raising exceptions")
print("=" * 60)

def process_data(data):
    """Process data, logging errors before re-raising."""
    try:
        result = sum(data) / len(data)
        return result
    except Exception as e:
        # Log the error (in real code, use proper logging)
        print(f"  [LOG] Error processing data: {type(e).__name__}: {e}")
        # Re-raise the same exception
        raise  # bare 'raise' re-raises the current exception

print("Processing [1, 2, 3]:")
print(f"  Result: {process_data([1, 2, 3])}")

print("\nProcessing [] (will re-raise):")
try:
    process_data([])
except ZeroDivisionError as e:
    print(f"  Caught in outer handler: {e}")

# -----------------------------------------------------------------------------
# ASSERTIONS (for debugging and invariants)
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 6: Assertions")
print("=" * 60)

def matrix_multiply(A, B):
    """
    Multiply matrices A and B.
    Uses assertions to check invariants.
    """
    # Assertions are for catching programmer errors, not user input errors
    assert len(A) > 0 and len(A[0]) > 0, "A must be non-empty"
    assert len(B) > 0 and len(B[0]) > 0, "B must be non-empty"
    assert len(A[0]) == len(B), f"Incompatible dimensions: {len(A[0])} vs {len(B)}"

    rows_A, cols_A = len(A), len(A[0])
    rows_B, cols_B = len(B), len(B[0])

    result = [[0] * cols_B for _ in range(rows_A)]
    for i in range(rows_A):
        for j in range(cols_B):
            for k in range(cols_A):
                result[i][j] += A[i][k] * B[k][j]

    return result

A = [[1, 2], [3, 4]]
B = [[5, 6], [7, 8]]
print(f"A × B = {matrix_multiply(A, B)}")

# Incompatible dimensions
print("\nIncompatible dimensions:")
try:
    matrix_multiply([[1, 2, 3]], [[1], [2]])  # 1x3 times 2x1
except AssertionError as e:
    print(f"  AssertionError: {e}")

print("""
Note on assertions:
- Use assertions for internal consistency checks ("this should never happen")
- Use exceptions for external error handling ("user gave bad input")
- Assertions can be disabled with 'python -O' (optimized mode)
- Never use assertions to validate user input!
""")
