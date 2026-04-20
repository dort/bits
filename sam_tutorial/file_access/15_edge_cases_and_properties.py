"""
Example 15: Testing Edge Cases and Property-Based Testing
=========================================================

Key concepts:
- Identifying and testing edge cases
- Boundary value analysis
- Property-based testing (testing with random inputs)
- Using hypothesis library for automated property testing

Mathematical analogy: Edge cases are like boundary conditions in PDEs.
The behavior at boundaries often reveals bugs that don't appear in the interior.
Property-based testing is like testing universal statements (∀x: P(x)).
"""

import math
import random

# =============================================================================
# PART 1: EDGE CASES AND BOUNDARY VALUES
# =============================================================================

print("=" * 70)
print("PART 1: Edge Cases and Boundary Values")
print("=" * 70)

# -----------------------------------------------------------------------------
# The code we're testing
# -----------------------------------------------------------------------------

def binary_search(arr, target):
    """
    Find index of target in sorted array.
    Returns -1 if not found.
    """
    if not arr:
        return -1

    left, right = 0, len(arr) - 1

    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1

    return -1


def is_prime(n):
    """Check if n is a prime number."""
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    for i in range(3, int(n**0.5) + 1, 2):
        if n % i == 0:
            return False
    return True


def solve_quadratic(a, b, c):
    """
    Solve ax^2 + bx + c = 0.
    Returns tuple of roots, or None if no real roots.
    """
    if a == 0:
        if b == 0:
            return None  # No solution or infinite solutions
        return (-c / b,)  # Linear equation

    discriminant = b**2 - 4*a*c

    if discriminant < 0:
        return None
    elif discriminant == 0:
        return (-b / (2*a),)  # Repeated root
    else:
        sqrt_d = math.sqrt(discriminant)
        return ((-b + sqrt_d) / (2*a), (-b - sqrt_d) / (2*a))


# -----------------------------------------------------------------------------
# Testing edge cases for binary_search
# -----------------------------------------------------------------------------

print("\n--- Binary Search Edge Cases ---")

def test_binary_search_edge_cases():
    """Test boundary conditions for binary search."""

    # Edge case 1: Empty array
    assert binary_search([], 5) == -1, "Empty array should return -1"
    print("  Empty array: PASS")

    # Edge case 2: Single element - found
    assert binary_search([5], 5) == 0, "Single element found"
    print("  Single element (found): PASS")

    # Edge case 3: Single element - not found
    assert binary_search([5], 3) == -1, "Single element not found"
    print("  Single element (not found): PASS")

    # Edge case 4: Two elements
    assert binary_search([1, 3], 1) == 0, "Two elements, find first"
    assert binary_search([1, 3], 3) == 1, "Two elements, find second"
    assert binary_search([1, 3], 2) == -1, "Two elements, not found"
    print("  Two elements: PASS")

    # Edge case 5: Target at boundaries
    arr = [1, 2, 3, 4, 5]
    assert binary_search(arr, 1) == 0, "First element"
    assert binary_search(arr, 5) == 4, "Last element"
    print("  Boundary elements: PASS")

    # Edge case 6: Target just outside boundaries
    assert binary_search(arr, 0) == -1, "Below minimum"
    assert binary_search(arr, 6) == -1, "Above maximum"
    print("  Outside boundaries: PASS")

    # Edge case 7: Duplicates (finds one of them)
    arr_dup = [1, 2, 2, 2, 3]
    result = binary_search(arr_dup, 2)
    assert result in [1, 2, 3], "Should find one of the 2s"
    print("  Duplicates: PASS")

    # Edge case 8: Large array
    large_arr = list(range(10000))
    assert binary_search(large_arr, 0) == 0
    assert binary_search(large_arr, 9999) == 9999
    assert binary_search(large_arr, 5000) == 5000
    print("  Large array: PASS")

test_binary_search_edge_cases()


# -----------------------------------------------------------------------------
# Testing edge cases for is_prime
# -----------------------------------------------------------------------------

print("\n--- Prime Number Edge Cases ---")

def test_is_prime_edge_cases():
    """Test boundary conditions for prime checking."""

    # Edge case 1: Numbers less than 2
    assert not is_prime(-1), "-1 is not prime"
    assert not is_prime(0), "0 is not prime"
    assert not is_prime(1), "1 is not prime"
    print("  Numbers < 2: PASS")

    # Edge case 2: Smallest prime
    assert is_prime(2), "2 is prime"
    print("  Smallest prime (2): PASS")

    # Edge case 3: First odd prime
    assert is_prime(3), "3 is prime"
    print("  First odd prime (3): PASS")

    # Edge case 4: Even numbers > 2
    for n in [4, 6, 8, 100, 1000]:
        assert not is_prime(n), f"{n} is not prime"
    print("  Even numbers > 2: PASS")

    # Edge case 5: Perfect squares of primes
    assert not is_prime(4), "4 = 2^2 is not prime"
    assert not is_prime(9), "9 = 3^2 is not prime"
    assert not is_prime(25), "25 = 5^2 is not prime"
    print("  Perfect squares of primes: PASS")

    # Edge case 6: Numbers just below/above primes
    assert not is_prime(10), "10 is not prime"
    assert is_prime(11), "11 is prime"
    assert not is_prime(12), "12 is not prime"
    print("  Adjacent to primes: PASS")

    # Edge case 7: Carmichael numbers (pseudoprimes for some tests)
    # 561 is the smallest Carmichael number
    assert not is_prime(561), "561 is not prime (Carmichael number)"
    print("  Carmichael number: PASS")

    # Edge case 8: Large primes
    assert is_prime(104729), "104729 is the 10000th prime"
    print("  Large prime: PASS")

test_is_prime_edge_cases()


# -----------------------------------------------------------------------------
# Testing edge cases for quadratic solver
# -----------------------------------------------------------------------------

print("\n--- Quadratic Solver Edge Cases ---")

def test_quadratic_edge_cases():
    """Test boundary conditions for quadratic solver."""

    # Helper to check if roots satisfy equation
    def verify_roots(a, b, c, roots):
        if roots is None:
            return True
        for r in roots:
            value = a*r**2 + b*r + c
            if abs(value) > 1e-10:
                return False
        return True

    # Edge case 1: a = 0 (linear equation)
    result = solve_quadratic(0, 2, -4)  # 2x - 4 = 0 -> x = 2
    assert result == (2.0,), f"Linear equation: got {result}"
    print("  Linear equation (a=0): PASS")

    # Edge case 2: a = b = 0 (degenerate)
    result = solve_quadratic(0, 0, 5)
    assert result is None, "a=b=0 should return None"
    print("  Degenerate (a=b=0): PASS")

    # Edge case 3: Discriminant = 0 (repeated root)
    result = solve_quadratic(1, -2, 1)  # (x-1)^2 = 0
    assert len(result) == 1 and math.isclose(result[0], 1.0)
    print("  Repeated root: PASS")

    # Edge case 4: Negative discriminant (no real roots)
    result = solve_quadratic(1, 0, 1)  # x^2 + 1 = 0
    assert result is None
    print("  No real roots: PASS")

    # Edge case 5: Very small coefficients
    result = solve_quadratic(1e-10, 1, 0)
    assert result is not None
    assert verify_roots(1e-10, 1, 0, result)
    print("  Small coefficients: PASS")

    # Edge case 6: Very large coefficients
    result = solve_quadratic(1e10, -1e10, 0)  # 1e10 * x * (x - 1) = 0
    assert result is not None
    print("  Large coefficients: PASS")

    # Edge case 7: c = 0 (root at origin)
    result = solve_quadratic(1, -3, 0)  # x(x-3) = 0
    assert 0.0 in result and 3.0 in result
    print("  Root at origin: PASS")

test_quadratic_edge_cases()


# =============================================================================
# PART 2: PROPERTY-BASED TESTING
# =============================================================================

print("\n" + "=" * 70)
print("PART 2: Property-Based Testing")
print("=" * 70)

print("""
Instead of testing specific examples, we test PROPERTIES that should
hold for ALL valid inputs. We then generate many random inputs.

Example properties:
- Commutativity: f(a, b) == f(b, a)
- Associativity: f(f(a, b), c) == f(a, f(b, c))
- Inverse: g(f(x)) == x
- Idempotency: f(f(x)) == f(x)
- Bounds: lower <= f(x) <= upper
""")

# -----------------------------------------------------------------------------
# Manual property-based testing
# -----------------------------------------------------------------------------

print("\n--- Manual Property Testing ---")

def test_sorting_properties():
    """Test properties that any correct sorting algorithm must satisfy."""

    def is_sorted(arr):
        return all(arr[i] <= arr[i+1] for i in range(len(arr) - 1))

    def is_permutation(original, sorted_arr):
        return sorted(original) == sorted(sorted_arr)

    # Test with many random arrays
    random.seed(42)
    num_tests = 100

    for _ in range(num_tests):
        # Generate random array
        length = random.randint(0, 50)
        arr = [random.randint(-100, 100) for _ in range(length)]

        # Sort it (using Python's built-in, but this tests any sort)
        result = sorted(arr)

        # Property 1: Result is sorted
        assert is_sorted(result), f"Result not sorted: {result}"

        # Property 2: Result is permutation of input
        assert is_permutation(arr, result), "Not a permutation"

        # Property 3: Length preserved
        assert len(result) == len(arr), "Length changed"

    print(f"  Sorting properties: PASS ({num_tests} random tests)")


def test_gcd_properties():
    """Test properties of GCD."""

    random.seed(42)
    num_tests = 200

    for _ in range(num_tests):
        a = random.randint(1, 10000)
        b = random.randint(1, 10000)
        g = math.gcd(a, b)

        # Property 1: GCD divides both numbers
        assert a % g == 0, f"GCD {g} doesn't divide {a}"
        assert b % g == 0, f"GCD {g} doesn't divide {b}"

        # Property 2: Commutativity
        assert math.gcd(a, b) == math.gcd(b, a)

        # Property 3: GCD(a, 0) = a
        assert math.gcd(a, 0) == a

        # Property 4: GCD(a, a) = a
        assert math.gcd(a, a) == a

        # Property 5: If GCD(a,b) = g, then GCD(a/g, b/g) = 1
        assert math.gcd(a // g, b // g) == 1

    print(f"  GCD properties: PASS ({num_tests} random tests)")


def test_sin_cos_properties():
    """Test trigonometric identities."""

    random.seed(42)
    num_tests = 200

    for _ in range(num_tests):
        x = random.uniform(-100, 100)

        # Property 1: Pythagorean identity
        sin_x = math.sin(x)
        cos_x = math.cos(x)
        assert math.isclose(sin_x**2 + cos_x**2, 1.0, rel_tol=1e-10)

        # Property 2: Bounded
        assert -1 <= sin_x <= 1
        assert -1 <= cos_x <= 1

        # Property 3: sin is odd, cos is even
        assert math.isclose(math.sin(-x), -math.sin(x), rel_tol=1e-10)
        assert math.isclose(math.cos(-x), math.cos(x), rel_tol=1e-10)

        # Property 4: Phase shift
        assert math.isclose(math.sin(x + math.pi/2), math.cos(x), rel_tol=1e-10)

    print(f"  Trig identities: PASS ({num_tests} random tests)")


test_sorting_properties()
test_gcd_properties()
test_sin_cos_properties()


# -----------------------------------------------------------------------------
# Testing inverse functions
# -----------------------------------------------------------------------------

print("\n--- Inverse Function Testing ---")

def test_exp_log_inverse():
    """Test that exp and log are inverses."""

    random.seed(42)
    num_tests = 100

    for _ in range(num_tests):
        # log(exp(x)) = x for all x
        x = random.uniform(-100, 100)
        assert math.isclose(math.log(math.exp(x)), x, rel_tol=1e-10) or \
               abs(math.log(math.exp(x)) - x) < 1e-10

        # exp(log(x)) = x for x > 0
        x = random.uniform(0.001, 1000)
        assert math.isclose(math.exp(math.log(x)), x, rel_tol=1e-10)

    print(f"  exp/log inverse: PASS ({num_tests} random tests)")


def test_sqrt_square_inverse():
    """Test that sqrt and square are (partial) inverses."""

    random.seed(42)
    num_tests = 100

    for _ in range(num_tests):
        # sqrt(x^2) = |x|
        x = random.uniform(-100, 100)
        assert math.isclose(math.sqrt(x**2), abs(x), rel_tol=1e-10)

        # (sqrt(x))^2 = x for x >= 0
        x = random.uniform(0, 1000)
        assert math.isclose(math.sqrt(x)**2, x, rel_tol=1e-10)

    print(f"  sqrt/square inverse: PASS ({num_tests} random tests)")


test_exp_log_inverse()
test_sqrt_square_inverse()


# =============================================================================
# PART 3: INTRODUCTION TO HYPOTHESIS (property-based testing library)
# =============================================================================

print("\n" + "=" * 70)
print("PART 3: Hypothesis Library (if installed)")
print("=" * 70)

try:
    from hypothesis import given, strategies as st, settings

    print("hypothesis is installed! Running property-based tests...\n")

    # Example 1: Testing list reversal
    @given(st.lists(st.integers()))
    def test_reverse_twice_is_identity(lst):
        """Reversing a list twice gives the original list."""
        assert list(reversed(list(reversed(lst)))) == lst

    # Example 2: Testing string operations
    @given(st.text())
    def test_encode_decode_roundtrip(s):
        """Encoding then decoding UTF-8 preserves the string."""
        assert s.encode('utf-8').decode('utf-8') == s

    # Example 3: Testing mathematical properties
    @given(st.floats(min_value=-1e10, max_value=1e10, allow_nan=False))
    def test_absolute_value_non_negative(x):
        """Absolute value is always non-negative."""
        assert abs(x) >= 0

    @given(st.floats(min_value=0.001, max_value=1e10, allow_nan=False))
    def test_log_positive_is_defined(x):
        """Log is defined for all positive numbers."""
        result = math.log(x)
        assert not math.isnan(result)

    # Example 4: Testing a function we wrote
    @given(st.integers(min_value=2, max_value=10000))
    @settings(max_examples=100)
    def test_is_prime_properties(n):
        """Test properties of is_prime function."""
        result = is_prime(n)

        # If n is prime, no number from 2 to sqrt(n) divides it
        if result:
            for i in range(2, int(n**0.5) + 1):
                assert n % i != 0, f"{n} claimed prime but divisible by {i}"

    # Run the tests
    test_reverse_twice_is_identity()
    print("  Reverse twice is identity: PASS")

    test_encode_decode_roundtrip()
    print("  Encode/decode roundtrip: PASS")

    test_absolute_value_non_negative()
    print("  Absolute value non-negative: PASS")

    test_log_positive_is_defined()
    print("  Log defined for positive: PASS")

    test_is_prime_properties()
    print("  Prime properties: PASS")

except ImportError:
    print("""
hypothesis is not installed. To install it, run:
    pip install hypothesis

Hypothesis automatically generates test cases based on type specifications.
It's excellent for finding edge cases you didn't think of!

Example usage:

    from hypothesis import given, strategies as st

    @given(st.lists(st.integers()))
    def test_sum_of_list_equals_manual_sum(lst):
        assert sum(lst) == manual_sum(lst)

Running this test will try hundreds of different lists automatically!
""")


# =============================================================================
# SUMMARY
# =============================================================================

print("\n" + "=" * 70)
print("SUMMARY: Testing Best Practices")
print("=" * 70)
print("""
Edge Cases Checklist:
--------------------
- Empty inputs (empty list, empty string, zero)
- Single element inputs
- Two element inputs (minimum for relationships)
- Boundary values (min, max, first, last)
- Values just inside/outside boundaries
- Negative numbers
- Very large numbers
- Very small numbers (near zero)
- Special values (NaN, infinity, None)
- Duplicate values
- Invalid inputs (test error handling)

Property-Based Testing Strategy:
-------------------------------
1. Identify mathematical properties:
   - Identities: f(identity_element) = known_value
   - Inverses: g(f(x)) = x
   - Commutativity: f(a, b) = f(b, a)
   - Associativity: f(f(a,b), c) = f(a, f(b,c))
   - Distributivity: f(a, g(b,c)) = g(f(a,b), f(a,c))
   - Bounds: lower <= f(x) <= upper

2. Generate random inputs within valid domain
3. Check that properties hold
4. Use hypothesis for automated generation

Testing Pyramid:
---------------
1. Unit tests: Test individual functions
2. Integration tests: Test functions working together
3. Property tests: Test invariants with many inputs
4. Edge case tests: Test boundaries and special cases
""")
