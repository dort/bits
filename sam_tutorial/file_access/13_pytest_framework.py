"""
Example 13: pytest - Modern Python Testing
==========================================

Key concepts:
- pytest is simpler and more powerful than unittest
- Uses plain assert statements (no special methods needed)
- Fixtures for setup/teardown
- Parametrized tests for testing many inputs
- Better error messages

Installation: pip install pytest
Run tests:    pytest 13_pytest_framework.py -v

Mathematical analogy: pytest is like a more elegant proof assistant -
less boilerplate, more focus on the actual assertions.
"""

import math
import pytest  # You may need to: pip install pytest

# -----------------------------------------------------------------------------
# THE CODE WE'RE TESTING
# -----------------------------------------------------------------------------

class Polynomial:
    """
    A polynomial represented by its coefficients.
    coeffs = [a_0, a_1, ..., a_n] represents a_0 + a_1*x + ... + a_n*x^n
    """

    def __init__(self, coeffs):
        # Remove trailing zeros (normalize)
        while len(coeffs) > 1 and coeffs[-1] == 0:
            coeffs = coeffs[:-1]
        self.coeffs = list(coeffs)

    @property
    def degree(self):
        """Return the degree of the polynomial."""
        if self.coeffs == [0]:
            return -1  # Convention: zero polynomial has degree -1
        return len(self.coeffs) - 1

    def __repr__(self):
        return f"Polynomial({self.coeffs})"

    def __eq__(self, other):
        if isinstance(other, (int, float)):
            return self.coeffs == [other]
        return self.coeffs == other.coeffs

    def __call__(self, x):
        """Evaluate polynomial at x using Horner's method."""
        result = 0
        for coeff in reversed(self.coeffs):
            result = result * x + coeff
        return result

    def __add__(self, other):
        if isinstance(other, (int, float)):
            other = Polynomial([other])

        # Pad shorter polynomial with zeros
        len1, len2 = len(self.coeffs), len(other.coeffs)
        max_len = max(len1, len2)
        c1 = self.coeffs + [0] * (max_len - len1)
        c2 = other.coeffs + [0] * (max_len - len2)

        return Polynomial([a + b for a, b in zip(c1, c2)])

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            return Polynomial([c * other for c in self.coeffs])

        # Polynomial multiplication (convolution of coefficients)
        result = [0] * (len(self.coeffs) + len(other.coeffs) - 1)
        for i, a in enumerate(self.coeffs):
            for j, b in enumerate(other.coeffs):
                result[i + j] += a * b
        return Polynomial(result)

    def derivative(self):
        """Return the derivative of this polynomial."""
        if self.degree <= 0:
            return Polynomial([0])
        new_coeffs = [i * self.coeffs[i] for i in range(1, len(self.coeffs))]
        return Polynomial(new_coeffs)


# -----------------------------------------------------------------------------
# BASIC PYTEST TESTS (just use assert!)
# -----------------------------------------------------------------------------

def test_polynomial_creation():
    """Test that polynomials are created correctly."""
    p = Polynomial([1, 2, 3])  # 1 + 2x + 3x^2
    assert p.coeffs == [1, 2, 3]
    assert p.degree == 2


def test_polynomial_normalization():
    """Test that trailing zeros are removed."""
    p = Polynomial([1, 2, 0, 0, 0])
    assert p.coeffs == [1, 2]
    assert p.degree == 1


def test_polynomial_evaluation():
    """Test polynomial evaluation."""
    p = Polynomial([1, 2, 3])  # 1 + 2x + 3x^2

    # At x=0: should be 1
    assert p(0) == 1

    # At x=1: 1 + 2 + 3 = 6
    assert p(1) == 6

    # At x=2: 1 + 4 + 12 = 17
    assert p(2) == 17


def test_polynomial_addition():
    """Test polynomial addition."""
    p1 = Polynomial([1, 2, 3])      # 1 + 2x + 3x^2
    p2 = Polynomial([4, 5])          # 4 + 5x

    result = p1 + p2
    expected = Polynomial([5, 7, 3])  # 5 + 7x + 3x^2

    assert result == expected


def test_polynomial_scalar_multiplication():
    """Test multiplication by scalar."""
    p = Polynomial([1, 2, 3])
    result = p * 2
    assert result == Polynomial([2, 4, 6])


# -----------------------------------------------------------------------------
# TESTING FLOATING POINT WITH pytest.approx
# -----------------------------------------------------------------------------

def test_polynomial_float_evaluation():
    """Test evaluation with floating-point comparison."""
    p = Polynomial([1, 1])  # 1 + x

    # Use pytest.approx for floating-point comparisons
    assert p(0.1) == pytest.approx(1.1)
    assert p(math.pi) == pytest.approx(1 + math.pi)


def test_derivative_at_point():
    """Test derivative evaluation."""
    p = Polynomial([0, 0, 1])  # x^2
    dp = p.derivative()        # 2x

    # Derivative of x^2 at x=3 should be 6
    assert dp(3) == pytest.approx(6.0)


# -----------------------------------------------------------------------------
# TESTING EXCEPTIONS WITH pytest.raises
# -----------------------------------------------------------------------------

def test_zero_polynomial_degree():
    """Test that zero polynomial has degree -1."""
    p = Polynomial([0])
    assert p.degree == -1


# If we had a function that should raise an exception:
def divide_polynomials(p1, p2):
    """Placeholder - polynomial division."""
    if p2 == Polynomial([0]):
        raise ZeroDivisionError("Cannot divide by zero polynomial")
    # ... actual implementation would go here
    return p1  # Stub


def test_division_by_zero_polynomial():
    """Test that dividing by zero polynomial raises error."""
    p = Polynomial([1, 2, 3])
    zero = Polynomial([0])

    with pytest.raises(ZeroDivisionError):
        divide_polynomials(p, zero)


# -----------------------------------------------------------------------------
# PARAMETRIZED TESTS (test many inputs at once)
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("coeffs,x,expected", [
    ([1], 5, 1),              # Constant polynomial
    ([0, 1], 3, 3),           # x at x=3
    ([0, 0, 1], 2, 4),        # x^2 at x=2
    ([1, 1, 1], 1, 3),        # 1+x+x^2 at x=1
    ([1, -1], 1, 0),          # 1-x at x=1
    ([1, 2, 1], -1, 0),       # (1+x)^2 at x=-1
])
def test_polynomial_evaluation_parametrized(coeffs, x, expected):
    """Test polynomial evaluation with many inputs."""
    p = Polynomial(coeffs)
    assert p(x) == expected


@pytest.mark.parametrize("n", [0, 1, 2, 3, 4, 5, 10])
def test_derivative_of_x_to_n(n):
    """Test that derivative of x^n is n*x^(n-1)."""
    # Create x^n: coefficients are [0, 0, ..., 0, 1] with n zeros
    coeffs = [0] * n + [1]
    p = Polynomial(coeffs)
    dp = p.derivative()

    if n == 0:
        # Derivative of constant is 0
        assert dp == Polynomial([0])
    else:
        # Derivative of x^n is n*x^(n-1)
        expected_coeffs = [0] * (n-1) + [n]
        assert dp == Polynomial(expected_coeffs)


# -----------------------------------------------------------------------------
# FIXTURES (setup code that can be shared between tests)
# -----------------------------------------------------------------------------

@pytest.fixture
def standard_polynomials():
    """Provide commonly used polynomials for testing."""
    return {
        'zero': Polynomial([0]),
        'one': Polynomial([1]),
        'x': Polynomial([0, 1]),
        'x_squared': Polynomial([0, 0, 1]),
        'quadratic': Polynomial([1, 2, 1]),  # (1+x)^2
    }


def test_zero_polynomial_is_additive_identity(standard_polynomials):
    """Test that p + 0 = p."""
    zero = standard_polynomials['zero']
    for name, p in standard_polynomials.items():
        result = p + zero
        assert result == p, f"Failed for {name}"


def test_one_polynomial_is_multiplicative_identity(standard_polynomials):
    """Test that p * 1 = p."""
    one = standard_polynomials['one']
    for name, p in standard_polynomials.items():
        result = p * one
        assert result == p, f"Failed for {name}"


@pytest.fixture
def sample_matrix():
    """Provide a sample matrix for testing."""
    return [[1, 2], [3, 4]]


# -----------------------------------------------------------------------------
# TESTING MATHEMATICAL PROPERTIES
# -----------------------------------------------------------------------------

def test_product_rule():
    """Test the product rule: (fg)' = f'g + fg'."""
    f = Polynomial([1, 2, 3])    # 1 + 2x + 3x^2
    g = Polynomial([2, -1, 1])   # 2 - x + x^2

    # Compute (fg)'
    fg = f * g
    fg_prime = fg.derivative()

    # Compute f'g + fg'
    f_prime = f.derivative()
    g_prime = g.derivative()
    product_rule_result = f_prime * g + f * g_prime

    # They should be equal
    assert fg_prime == product_rule_result


def test_chain_rule_for_linear():
    """Test chain rule for composition with linear function."""
    # If g(x) = ax + b, then (f∘g)'(x) = a * f'(g(x))
    f = Polynomial([1, 0, 1])  # 1 + x^2
    # We'll verify numerically at a point

    a, b = 2, 3  # g(x) = 2x + 3
    x = 1.5

    # f(g(x)) derivative via chain rule: a * f'(g(x))
    f_prime = f.derivative()
    gx = a * x + b
    chain_rule_result = a * f_prime(gx)

    # Numerical derivative of f(g(x))
    h = 1e-8
    numerical_derivative = (f(a*(x+h) + b) - f(a*x + b)) / h

    assert chain_rule_result == pytest.approx(numerical_derivative, rel=1e-5)


@pytest.mark.parametrize("n", range(1, 8))
def test_sum_of_geometric_series(n):
    """
    Test that (1-x)(1 + x + x^2 + ... + x^(n-1)) = 1 - x^n.
    """
    # 1 - x
    factor = Polynomial([1, -1])

    # 1 + x + x^2 + ... + x^(n-1)
    geometric = Polynomial([1] * n)

    # Product should be 1 - x^n
    product = factor * geometric
    expected = Polynomial([1] + [0]*(n-1) + [-1])

    assert product == expected


# -----------------------------------------------------------------------------
# RUNNING TESTS
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("pytest examples")
    print("=" * 60)
    print("""
To run these tests, use pytest from command line:

    pytest 13_pytest_framework.py -v

Options:
    -v              Verbose output
    -x              Stop on first failure
    -k "pattern"    Run tests matching pattern
    --tb=short      Shorter tracebacks

Examples:
    pytest 13_pytest_framework.py -v -k "derivative"
    pytest 13_pytest_framework.py -v -k "parametrized"
    pytest 13_pytest_framework.py -v --tb=short

Note: pytest can also run unittest-style tests!
""")

    # Run pytest programmatically
    pytest.main([__file__, "-v"])
