"""
Example 11: Testing Basics - Why and How to Test
=================================================

Key concepts:
- Why testing matters (especially in mathematical/scientific code)
- Manual testing with assert statements
- Comparing floating-point numbers safely
- Organizing simple tests

Mathematical analogy: Testing is like proof verification.
Just as a proof needs to be checked for errors, code needs to be
tested to verify it computes what we intend.
"""

import math

# -----------------------------------------------------------------------------
# THE CODE WE WANT TO TEST
# -----------------------------------------------------------------------------

def factorial(n):
    """Compute n! for non-negative integers."""
    if n < 0:
        raise ValueError("factorial not defined for negative numbers")
    if n == 0 or n == 1:
        return 1
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result

def binomial(n, k):
    """Compute binomial coefficient C(n,k) = n! / (k! * (n-k)!)."""
    if k < 0 or k > n:
        return 0
    return factorial(n) // (factorial(k) * factorial(n - k))

def quadratic_roots(a, b, c):
    """
    Find roots of ax^2 + bx + c = 0.
    Returns tuple of (root1, root2) for real roots.
    Raises ValueError for complex roots.
    """
    if a == 0:
        raise ValueError("Coefficient 'a' cannot be zero (not quadratic)")

    discriminant = b**2 - 4*a*c

    if discriminant < 0:
        raise ValueError("No real roots (complex roots not supported)")

    sqrt_disc = math.sqrt(discriminant)
    root1 = (-b + sqrt_disc) / (2*a)
    root2 = (-b - sqrt_disc) / (2*a)

    return (root1, root2)

# -----------------------------------------------------------------------------
# BASIC TESTING WITH ASSERT
# -----------------------------------------------------------------------------

print("=" * 60)
print("PART 1: Basic testing with assert")
print("=" * 60)

# The simplest form of testing: assert that something is true
# If the assertion fails, Python raises AssertionError

print("\nTesting factorial():")

# Test known values
assert factorial(0) == 1, "0! should be 1"
assert factorial(1) == 1, "1! should be 1"
assert factorial(5) == 120, "5! should be 120"
assert factorial(10) == 3628800, "10! should be 3628800"

print("  All factorial tests passed!")

print("\nTesting binomial():")

# Pascal's triangle values
assert binomial(5, 0) == 1
assert binomial(5, 1) == 5
assert binomial(5, 2) == 10
assert binomial(5, 3) == 10
assert binomial(5, 4) == 5
assert binomial(5, 5) == 1

# Edge cases
assert binomial(5, 6) == 0  # k > n
assert binomial(5, -1) == 0  # k < 0

# Mathematical identity: C(n,k) = C(n, n-k)
for n in range(10):
    for k in range(n + 1):
        assert binomial(n, k) == binomial(n, n - k), f"Symmetry failed for ({n},{k})"

print("  All binomial tests passed!")

# -----------------------------------------------------------------------------
# TESTING FLOATING-POINT RESULTS
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 2: Testing floating-point numbers")
print("=" * 60)

print("""
CRITICAL: Never use == for floating-point comparisons!

Example of the problem:
  0.1 + 0.2 = 0.30000000000000004  (not exactly 0.3)

Instead, check if values are "close enough" using a tolerance.
""")

def is_close(a, b, rel_tol=1e-9, abs_tol=1e-12):
    """
    Check if two floating-point numbers are approximately equal.

    rel_tol: relative tolerance (for large numbers)
    abs_tol: absolute tolerance (for numbers near zero)
    """
    return abs(a - b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)

# Demonstrate the problem
print(f"0.1 + 0.2 == 0.3? {0.1 + 0.2 == 0.3}")  # False!
print(f"is_close(0.1 + 0.2, 0.3)? {is_close(0.1 + 0.2, 0.3)}")  # True

# Python's built-in (Python 3.5+)
print(f"math.isclose(0.1 + 0.2, 0.3)? {math.isclose(0.1 + 0.2, 0.3)}")

print("\nTesting quadratic_roots():")

# Test: x^2 - 5x + 6 = 0 has roots 3 and 2
roots = quadratic_roots(1, -5, 6)
assert math.isclose(roots[0], 3.0) and math.isclose(roots[1], 2.0), \
    f"Expected (3, 2), got {roots}"

# Test: x^2 - 2 = 0 has roots sqrt(2) and -sqrt(2)
roots = quadratic_roots(1, 0, -2)
assert math.isclose(roots[0], math.sqrt(2)), f"Expected sqrt(2), got {roots[0]}"
assert math.isclose(roots[1], -math.sqrt(2)), f"Expected -sqrt(2), got {roots[1]}"

# Test: Verify roots actually satisfy the equation
a, b, c = 3, -7, 2
roots = quadratic_roots(a, b, c)
for r in roots:
    value = a*r**2 + b*r + c
    assert math.isclose(value, 0, abs_tol=1e-10), \
        f"Root {r} doesn't satisfy equation: f({r}) = {value}"

print("  All quadratic_roots tests passed!")

# -----------------------------------------------------------------------------
# TESTING EXCEPTIONS
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 3: Testing that exceptions are raised")
print("=" * 60)

def expect_exception(func, exception_type, *args, **kwargs):
    """
    Test that calling func(*args, **kwargs) raises exception_type.
    Returns True if the expected exception was raised.
    """
    try:
        func(*args, **kwargs)
        return False  # No exception raised - test failed
    except exception_type:
        return True  # Expected exception raised - test passed
    except Exception as e:
        print(f"  Wrong exception type: expected {exception_type.__name__}, "
              f"got {type(e).__name__}")
        return False

print("\nTesting exception handling:")

# factorial should raise ValueError for negative input
assert expect_exception(factorial, ValueError, -1), \
    "factorial(-1) should raise ValueError"

# quadratic_roots should raise ValueError for complex roots
assert expect_exception(quadratic_roots, ValueError, 1, 0, 1), \
    "x^2 + 1 = 0 should raise ValueError (no real roots)"

# quadratic_roots should raise ValueError for a=0
assert expect_exception(quadratic_roots, ValueError, 0, 1, 1), \
    "a=0 should raise ValueError (not quadratic)"

print("  All exception tests passed!")

# -----------------------------------------------------------------------------
# ORGANIZING TESTS INTO FUNCTIONS
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 4: Organizing tests into functions")
print("=" * 60)

def test_factorial_known_values():
    """Test factorial against known values."""
    known_values = [
        (0, 1), (1, 1), (2, 2), (3, 6), (4, 24),
        (5, 120), (6, 720), (7, 5040), (10, 3628800)
    ]
    for n, expected in known_values:
        result = factorial(n)
        assert result == expected, f"factorial({n}) = {result}, expected {expected}"
    return True

def test_factorial_recurrence():
    """Test that n! = n * (n-1)! for n > 0."""
    for n in range(1, 20):
        assert factorial(n) == n * factorial(n - 1), \
            f"Recurrence failed at n={n}"
    return True

def test_binomial_pascals_identity():
    """Test Pascal's identity: C(n,k) = C(n-1,k-1) + C(n-1,k)."""
    for n in range(2, 15):
        for k in range(1, n):
            left = binomial(n, k)
            right = binomial(n-1, k-1) + binomial(n-1, k)
            assert left == right, \
                f"Pascal's identity failed: C({n},{k})={left} != {right}"
    return True

def test_binomial_sum():
    """Test that sum of row n in Pascal's triangle is 2^n."""
    for n in range(15):
        row_sum = sum(binomial(n, k) for k in range(n + 1))
        assert row_sum == 2**n, f"Row {n} sum = {row_sum}, expected {2**n}"
    return True

def run_all_tests():
    """Run all test functions and report results."""
    tests = [
        test_factorial_known_values,
        test_factorial_recurrence,
        test_binomial_pascals_identity,
        test_binomial_sum,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        test_name = test_func.__name__
        try:
            test_func()
            print(f"  PASS: {test_name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {test_name}")
            print(f"        {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {test_name}")
            print(f"         {type(e).__name__}: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0

print("\nRunning organized tests:")
all_passed = run_all_tests()

# -----------------------------------------------------------------------------
# MATHEMATICAL PROPERTIES AS TESTS
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 5: Testing mathematical properties")
print("=" * 60)

print("""
For mathematical code, properties make excellent tests:
- Identities: f(special_input) = known_value
- Symmetries: f(x, y) = f(y, x)
- Inverses: g(f(x)) = x
- Bounds: lower <= f(x) <= upper
- Recurrences: f(n) = g(f(n-1), ...)
""")

def sin_taylor(x, terms=10):
    """Compute sin(x) using Taylor series."""
    result = 0
    for n in range(terms):
        sign = (-1) ** n
        result += sign * (x ** (2*n + 1)) / factorial(2*n + 1)
    return result

def test_sin_taylor():
    """Test our Taylor series implementation of sin."""
    print("\nTesting sin_taylor():")

    # Test 1: sin(0) = 0
    assert math.isclose(sin_taylor(0), 0, abs_tol=1e-15), "sin(0) should be 0"
    print("  sin(0) = 0: PASS")

    # Test 2: sin(pi) = 0
    assert math.isclose(sin_taylor(math.pi, terms=20), 0, abs_tol=1e-10), \
        "sin(pi) should be 0"
    print("  sin(pi) = 0: PASS")

    # Test 3: sin(pi/2) = 1
    assert math.isclose(sin_taylor(math.pi/2, terms=15), 1, abs_tol=1e-10), \
        "sin(pi/2) should be 1"
    print("  sin(pi/2) = 1: PASS")

    # Test 4: Odd function: sin(-x) = -sin(x)
    for x in [0.5, 1.0, 1.5, 2.0]:
        assert math.isclose(sin_taylor(-x), -sin_taylor(x), abs_tol=1e-12), \
            f"sin(-{x}) should equal -sin({x})"
    print("  sin(-x) = -sin(x): PASS")

    # Test 5: Bounded: -1 <= sin(x) <= 1
    import random
    random.seed(42)
    for _ in range(100):
        x = random.uniform(-10, 10)
        s = sin_taylor(x, terms=25)
        assert -1.0001 <= s <= 1.0001, f"sin({x}) = {s} out of bounds"
    print("  -1 <= sin(x) <= 1: PASS")

    # Test 6: Compare with math.sin
    for x in [0.1, 0.5, 1.0, 2.0, 3.0]:
        our_result = sin_taylor(x, terms=20)
        expected = math.sin(x)
        assert math.isclose(our_result, expected, rel_tol=1e-10), \
            f"sin({x}): got {our_result}, expected {expected}"
    print("  Matches math.sin(): PASS")

test_sin_taylor()

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print("""
Basic testing principles:
1. Use assert to verify expected behavior
2. Use math.isclose() for floating-point comparisons
3. Test normal cases, edge cases, and error cases
4. Organize tests into named functions
5. Use mathematical properties as test cases
6. Run tests frequently during development

Next: Learn about unittest (built-in) and pytest (popular third-party)
""")
