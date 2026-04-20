"""
Example 14: Test-Driven Development (TDD)
=========================================

Key concepts:
- Write tests BEFORE writing code
- Red-Green-Refactor cycle
- Tests serve as specification
- Incremental development

Mathematical analogy: TDD is like constructive mathematics.
You first state what you want to prove (the test), then find
a construction (code) that satisfies it.

This file walks through building a Fraction class using TDD.
"""

import math

# =============================================================================
# TDD CYCLE: RED -> GREEN -> REFACTOR
# =============================================================================
#
# 1. RED:      Write a failing test for new functionality
# 2. GREEN:    Write minimal code to make the test pass
# 3. REFACTOR: Clean up the code while keeping tests passing
#
# Repeat for each new feature.
# =============================================================================

print("=" * 70)
print("TEST-DRIVEN DEVELOPMENT: Building a Fraction Class")
print("=" * 70)

# -----------------------------------------------------------------------------
# STEP 1: Write tests for basic creation
# -----------------------------------------------------------------------------

print("\n--- STEP 1: Fraction creation ---")

def test_fraction_creation():
    """A fraction should store numerator and denominator."""
    f = Fraction(3, 4)
    assert f.numerator == 3
    assert f.denominator == 4

def test_fraction_string():
    """A fraction should have a readable string form."""
    f = Fraction(3, 4)
    assert str(f) == "3/4"

# First, let's run these tests - they will FAIL (RED phase)
# We need to create the Fraction class.

# Minimal implementation to make tests pass (GREEN phase):

class Fraction:
    """
    A class representing rational numbers.
    Built incrementally using TDD.
    """

    def __init__(self, numerator, denominator=1):
        if denominator == 0:
            raise ValueError("Denominator cannot be zero")

        # Store in lowest terms with positive denominator
        gcd = math.gcd(abs(numerator), abs(denominator))
        sign = -1 if (numerator < 0) != (denominator < 0) else 1

        self.numerator = sign * abs(numerator) // gcd
        self.denominator = abs(denominator) // gcd

    def __str__(self):
        if self.denominator == 1:
            return str(self.numerator)
        return f"{self.numerator}/{self.denominator}"

    def __repr__(self):
        return f"Fraction({self.numerator}, {self.denominator})"

# Run tests
test_fraction_creation()
test_fraction_string()
print("  PASS: Creation tests")

# -----------------------------------------------------------------------------
# STEP 2: Write tests for normalization (reducing fractions)
# -----------------------------------------------------------------------------

print("\n--- STEP 2: Fraction normalization ---")

def test_fraction_reduces():
    """Fractions should be stored in lowest terms."""
    f = Fraction(6, 8)  # Should become 3/4
    assert f.numerator == 3
    assert f.denominator == 4

def test_fraction_negative():
    """Negative sign should be in numerator."""
    f1 = Fraction(-3, 4)
    assert f1.numerator == -3
    assert f1.denominator == 4

    f2 = Fraction(3, -4)
    assert f2.numerator == -3
    assert f2.denominator == 4

    f3 = Fraction(-3, -4)
    assert f3.numerator == 3
    assert f3.denominator == 4

def test_fraction_zero_denominator():
    """Zero denominator should raise ValueError."""
    try:
        f = Fraction(1, 0)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass  # Expected

# Run tests
test_fraction_reduces()
test_fraction_negative()
test_fraction_zero_denominator()
print("  PASS: Normalization tests")

# -----------------------------------------------------------------------------
# STEP 3: Write tests for equality
# -----------------------------------------------------------------------------

print("\n--- STEP 3: Fraction equality ---")

def test_fraction_equality():
    """Equal fractions should be equal."""
    assert Fraction(1, 2) == Fraction(1, 2)
    assert Fraction(1, 2) == Fraction(2, 4)
    assert Fraction(1, 2) == Fraction(3, 6)

def test_fraction_inequality():
    """Unequal fractions should not be equal."""
    assert Fraction(1, 2) != Fraction(1, 3)
    assert Fraction(1, 2) != Fraction(2, 3)

# Need to implement __eq__

def __eq__(self, other):
    if isinstance(other, int):
        other = Fraction(other)
    if not isinstance(other, Fraction):
        return NotImplemented
    return self.numerator == other.numerator and self.denominator == other.denominator

# Add to class
Fraction.__eq__ = __eq__

# Run tests
test_fraction_equality()
test_fraction_inequality()
print("  PASS: Equality tests")

# -----------------------------------------------------------------------------
# STEP 4: Write tests for arithmetic
# -----------------------------------------------------------------------------

print("\n--- STEP 4: Fraction arithmetic ---")

def test_fraction_addition():
    """Test fraction addition."""
    # 1/2 + 1/3 = 5/6
    assert Fraction(1, 2) + Fraction(1, 3) == Fraction(5, 6)

    # 1/4 + 1/4 = 1/2
    assert Fraction(1, 4) + Fraction(1, 4) == Fraction(1, 2)

def test_fraction_subtraction():
    """Test fraction subtraction."""
    # 3/4 - 1/4 = 1/2
    assert Fraction(3, 4) - Fraction(1, 4) == Fraction(1, 2)

    # 1/2 - 1/3 = 1/6
    assert Fraction(1, 2) - Fraction(1, 3) == Fraction(1, 6)

def test_fraction_multiplication():
    """Test fraction multiplication."""
    # 1/2 * 1/3 = 1/6
    assert Fraction(1, 2) * Fraction(1, 3) == Fraction(1, 6)

    # 2/3 * 3/4 = 1/2
    assert Fraction(2, 3) * Fraction(3, 4) == Fraction(1, 2)

def test_fraction_division():
    """Test fraction division."""
    # (1/2) / (1/3) = 3/2
    assert Fraction(1, 2) / Fraction(1, 3) == Fraction(3, 2)

# Implement arithmetic operations

def __add__(self, other):
    if isinstance(other, int):
        other = Fraction(other)
    new_num = self.numerator * other.denominator + other.numerator * self.denominator
    new_den = self.denominator * other.denominator
    return Fraction(new_num, new_den)

def __sub__(self, other):
    if isinstance(other, int):
        other = Fraction(other)
    new_num = self.numerator * other.denominator - other.numerator * self.denominator
    new_den = self.denominator * other.denominator
    return Fraction(new_num, new_den)

def __mul__(self, other):
    if isinstance(other, int):
        other = Fraction(other)
    return Fraction(self.numerator * other.numerator,
                   self.denominator * other.denominator)

def __truediv__(self, other):
    if isinstance(other, int):
        other = Fraction(other)
    if other.numerator == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return Fraction(self.numerator * other.denominator,
                   self.denominator * other.numerator)

# Add to class
Fraction.__add__ = __add__
Fraction.__sub__ = __sub__
Fraction.__mul__ = __mul__
Fraction.__truediv__ = __truediv__

# Run tests
test_fraction_addition()
test_fraction_subtraction()
test_fraction_multiplication()
test_fraction_division()
print("  PASS: Arithmetic tests")

# -----------------------------------------------------------------------------
# STEP 5: Write tests for conversion to float
# -----------------------------------------------------------------------------

print("\n--- STEP 5: Float conversion ---")

def test_fraction_to_float():
    """Test conversion to float."""
    assert float(Fraction(1, 2)) == 0.5
    assert float(Fraction(1, 4)) == 0.25
    assert abs(float(Fraction(1, 3)) - 0.333333333) < 1e-8

def __float__(self):
    return self.numerator / self.denominator

Fraction.__float__ = __float__

test_fraction_to_float()
print("  PASS: Float conversion tests")

# -----------------------------------------------------------------------------
# STEP 6: Write tests for comparison
# -----------------------------------------------------------------------------

print("\n--- STEP 6: Comparison operators ---")

def test_fraction_comparison():
    """Test comparison operators."""
    assert Fraction(1, 2) < Fraction(2, 3)
    assert Fraction(2, 3) > Fraction(1, 2)
    assert Fraction(1, 2) <= Fraction(1, 2)
    assert Fraction(1, 2) <= Fraction(2, 3)
    assert Fraction(2, 3) >= Fraction(1, 2)
    assert Fraction(2, 3) >= Fraction(2, 3)

def __lt__(self, other):
    if isinstance(other, int):
        other = Fraction(other)
    return self.numerator * other.denominator < other.numerator * self.denominator

def __le__(self, other):
    return self < other or self == other

def __gt__(self, other):
    if isinstance(other, int):
        other = Fraction(other)
    return self.numerator * other.denominator > other.numerator * self.denominator

def __ge__(self, other):
    return self > other or self == other

Fraction.__lt__ = __lt__
Fraction.__le__ = __le__
Fraction.__gt__ = __gt__
Fraction.__ge__ = __ge__

test_fraction_comparison()
print("  PASS: Comparison tests")

# -----------------------------------------------------------------------------
# STEP 7: Write tests for mathematical properties
# -----------------------------------------------------------------------------

print("\n--- STEP 7: Mathematical properties ---")

def test_additive_identity():
    """Test that f + 0 = f."""
    f = Fraction(3, 7)
    zero = Fraction(0)
    assert f + zero == f

def test_multiplicative_identity():
    """Test that f * 1 = f."""
    f = Fraction(3, 7)
    one = Fraction(1)
    assert f * one == f

def test_additive_inverse():
    """Test that f + (-f) = 0."""
    f = Fraction(3, 7)
    neg_f = Fraction(-3, 7)
    assert f + neg_f == Fraction(0)

def test_multiplicative_inverse():
    """Test that f * (1/f) = 1."""
    f = Fraction(3, 7)
    inv_f = Fraction(7, 3)
    assert f * inv_f == Fraction(1)

def test_commutativity():
    """Test that a + b = b + a and a * b = b * a."""
    a = Fraction(2, 5)
    b = Fraction(3, 7)
    assert a + b == b + a
    assert a * b == b * a

def test_associativity():
    """Test that (a + b) + c = a + (b + c)."""
    a = Fraction(1, 2)
    b = Fraction(1, 3)
    c = Fraction(1, 4)
    assert (a + b) + c == a + (b + c)
    assert (a * b) * c == a * (b * c)

def test_distributivity():
    """Test that a * (b + c) = a*b + a*c."""
    a = Fraction(2, 3)
    b = Fraction(1, 4)
    c = Fraction(1, 5)
    assert a * (b + c) == a * b + a * c

# Run property tests
test_additive_identity()
test_multiplicative_identity()
test_additive_inverse()
test_multiplicative_inverse()
test_commutativity()
test_associativity()
test_distributivity()
print("  PASS: Mathematical property tests")

# -----------------------------------------------------------------------------
# FINAL: Complete working class with all features
# -----------------------------------------------------------------------------

print("\n" + "=" * 70)
print("FINAL RESULT: Complete Fraction class")
print("=" * 70)

# Demonstration
print("\nDemonstration:")
f1 = Fraction(1, 2)
f2 = Fraction(1, 3)
print(f"  {f1} + {f2} = {f1 + f2}")
print(f"  {f1} - {f2} = {f1 - f2}")
print(f"  {f1} * {f2} = {f1 * f2}")
print(f"  {f1} / {f2} = {f1 / f2}")

# Calculate harmonic series partial sum
print("\n  Harmonic series H_10 = 1 + 1/2 + 1/3 + ... + 1/10:")
h10 = Fraction(0)
for n in range(1, 11):
    h10 = h10 + Fraction(1, n)
print(f"  H_10 = {h10} = {float(h10):.6f}")

# Calculate continued fraction for golden ratio
print("\n  Golden ratio via continued fraction [1; 1, 1, 1, ...]:")
phi = Fraction(1)
for _ in range(20):
    phi = Fraction(1) + Fraction(1, 1) / phi
print(f"  phi ≈ {phi} = {float(phi):.10f}")
print(f"  (1 + sqrt(5))/2 = {(1 + 5**0.5)/2:.10f}")

# -----------------------------------------------------------------------------
# TDD SUMMARY
# -----------------------------------------------------------------------------

print("\n" + "=" * 70)
print("TDD SUMMARY")
print("=" * 70)
print("""
Test-Driven Development Workflow:

1. WRITE A TEST
   - Think about what you want the code to do
   - Write a test that would pass if the code worked
   - Run the test - it should FAIL (Red)

2. WRITE MINIMAL CODE
   - Write just enough code to make the test pass
   - Don't worry about elegance yet
   - Run the test - it should PASS (Green)

3. REFACTOR
   - Clean up the code
   - Remove duplication
   - Improve naming
   - Run tests - they should still PASS

4. REPEAT
   - Add the next feature
   - Go back to step 1

Benefits of TDD:
- Tests serve as documentation
- Forces you to think about API design first
- Catches bugs immediately
- Safe refactoring (tests catch regressions)
- Results in testable code
- Builds confidence in code correctness

For mathematical code specifically:
- Test known values (factorial(5) == 120)
- Test mathematical properties (commutativity, associativity)
- Test edge cases (zero, negative, very large)
- Test against reference implementations
""")
