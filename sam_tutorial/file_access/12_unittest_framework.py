"""
Example 12: The unittest Framework
==================================

Key concepts:
- unittest is Python's built-in testing framework
- Test classes inherit from unittest.TestCase
- Special assertion methods: assertEqual, assertAlmostEqual, assertRaises
- Test discovery and running

Mathematical analogy: unittest provides a structured framework for proofs,
like how a formal proof system provides rules for derivation.

Run this file with: python 12_unittest_framework.py
Or with more detail: python -m unittest 12_unittest_framework -v
"""

import unittest
import math

# -----------------------------------------------------------------------------
# THE CODE WE'RE TESTING (normally this would be in a separate file)
# -----------------------------------------------------------------------------

class Vector:
    """A simple 2D or 3D vector class."""

    def __init__(self, *components):
        self.components = tuple(components)
        self.dimension = len(components)

    def __repr__(self):
        return f"Vector{self.components}"

    def __eq__(self, other):
        if not isinstance(other, Vector):
            return False
        return self.components == other.components

    def __add__(self, other):
        if self.dimension != other.dimension:
            raise ValueError(f"Cannot add vectors of dimension {self.dimension} and {other.dimension}")
        return Vector(*(a + b for a, b in zip(self.components, other.components)))

    def __sub__(self, other):
        if self.dimension != other.dimension:
            raise ValueError(f"Cannot subtract vectors of dimension {self.dimension} and {other.dimension}")
        return Vector(*(a - b for a, b in zip(self.components, other.components)))

    def __mul__(self, scalar):
        return Vector(*(scalar * c for c in self.components))

    def __rmul__(self, scalar):
        return self * scalar

    def dot(self, other):
        """Compute dot product."""
        if self.dimension != other.dimension:
            raise ValueError("Dot product requires same dimension")
        return sum(a * b for a, b in zip(self.components, other.components))

    def norm(self):
        """Compute Euclidean norm."""
        return math.sqrt(self.dot(self))

    def normalize(self):
        """Return unit vector in same direction."""
        n = self.norm()
        if n == 0:
            raise ValueError("Cannot normalize zero vector")
        return (1/n) * self

    @staticmethod
    def cross(v1, v2):
        """Compute cross product of 3D vectors."""
        if v1.dimension != 3 or v2.dimension != 3:
            raise ValueError("Cross product only defined for 3D vectors")
        a1, a2, a3 = v1.components
        b1, b2, b3 = v2.components
        return Vector(
            a2*b3 - a3*b2,
            a3*b1 - a1*b3,
            a1*b2 - a2*b1
        )


# -----------------------------------------------------------------------------
# TEST CLASS USING UNITTEST
# -----------------------------------------------------------------------------

class TestVector(unittest.TestCase):
    """
    Test suite for the Vector class.

    Each method starting with 'test_' is a test case.
    """

    # -------------------------------------------------------------------------
    # Setup and teardown (optional)
    # -------------------------------------------------------------------------

    def setUp(self):
        """
        Called before each test method.
        Use this to create objects needed for tests.
        """
        self.v1 = Vector(1, 2, 3)
        self.v2 = Vector(4, 5, 6)
        self.zero = Vector(0, 0, 0)

    def tearDown(self):
        """
        Called after each test method.
        Use this to clean up resources (rarely needed).
        """
        pass  # Nothing to clean up in this case

    # -------------------------------------------------------------------------
    # Basic tests
    # -------------------------------------------------------------------------

    def test_creation(self):
        """Test that vectors are created correctly."""
        v = Vector(1, 2, 3)
        self.assertEqual(v.components, (1, 2, 3))
        self.assertEqual(v.dimension, 3)

    def test_equality(self):
        """Test vector equality."""
        v1 = Vector(1, 2, 3)
        v2 = Vector(1, 2, 3)
        v3 = Vector(1, 2, 4)

        self.assertEqual(v1, v2)      # Same components
        self.assertNotEqual(v1, v3)   # Different components

    # -------------------------------------------------------------------------
    # Testing arithmetic operations
    # -------------------------------------------------------------------------

    def test_addition(self):
        """Test vector addition."""
        result = self.v1 + self.v2
        expected = Vector(5, 7, 9)
        self.assertEqual(result, expected)

    def test_subtraction(self):
        """Test vector subtraction."""
        result = self.v2 - self.v1
        expected = Vector(3, 3, 3)
        self.assertEqual(result, expected)

    def test_scalar_multiplication(self):
        """Test multiplication by scalar."""
        result = 2 * self.v1
        expected = Vector(2, 4, 6)
        self.assertEqual(result, expected)

        # Also test v * scalar
        result2 = self.v1 * 3
        expected2 = Vector(3, 6, 9)
        self.assertEqual(result2, expected2)

    def test_addition_with_zero(self):
        """Test that v + 0 = v (identity)."""
        result = self.v1 + self.zero
        self.assertEqual(result, self.v1)

    # -------------------------------------------------------------------------
    # Testing floating-point results
    # -------------------------------------------------------------------------

    def test_norm(self):
        """Test Euclidean norm calculation."""
        v = Vector(3, 4)  # 3-4-5 right triangle
        self.assertEqual(v.norm(), 5.0)  # Exact in this case

        # For non-exact cases, use assertAlmostEqual
        v2 = Vector(1, 1, 1)
        self.assertAlmostEqual(v2.norm(), math.sqrt(3), places=10)

    def test_dot_product(self):
        """Test dot product."""
        result = self.v1.dot(self.v2)
        # 1*4 + 2*5 + 3*6 = 4 + 10 + 18 = 32
        self.assertEqual(result, 32)

    def test_normalize(self):
        """Test that normalize() returns unit vector."""
        v = Vector(3, 4)
        unit = v.normalize()

        # Unit vector should have norm 1
        self.assertAlmostEqual(unit.norm(), 1.0, places=10)

        # Should point in same direction (parallel to original)
        # Check by comparing ratios
        ratio = unit.components[0] / (v.components[0] / v.norm())
        self.assertAlmostEqual(ratio, 1.0, places=10)

    # -------------------------------------------------------------------------
    # Testing exceptions
    # -------------------------------------------------------------------------

    def test_dimension_mismatch_addition(self):
        """Test that adding vectors of different dimensions raises ValueError."""
        v2d = Vector(1, 2)
        v3d = Vector(1, 2, 3)

        # assertRaises checks that the exception is raised
        with self.assertRaises(ValueError):
            v2d + v3d

    def test_dimension_mismatch_dot(self):
        """Test that dot product of different dimensions raises ValueError."""
        v2d = Vector(1, 2)
        v3d = Vector(1, 2, 3)

        with self.assertRaises(ValueError):
            v2d.dot(v3d)

    def test_normalize_zero_vector(self):
        """Test that normalizing zero vector raises ValueError."""
        with self.assertRaises(ValueError):
            self.zero.normalize()

    def test_cross_product_dimension(self):
        """Test that cross product requires 3D vectors."""
        v2d = Vector(1, 2)

        with self.assertRaises(ValueError):
            Vector.cross(v2d, self.v1)

    # -------------------------------------------------------------------------
    # Testing mathematical properties
    # -------------------------------------------------------------------------

    def test_dot_product_commutative(self):
        """Test that dot product is commutative: u·v = v·u."""
        self.assertEqual(self.v1.dot(self.v2), self.v2.dot(self.v1))

    def test_cross_product_anticommutative(self):
        """Test that cross product is anticommutative: u×v = -(v×u)."""
        cross1 = Vector.cross(self.v1, self.v2)
        cross2 = Vector.cross(self.v2, self.v1)
        negated = (-1) * cross2

        self.assertEqual(cross1, negated)

    def test_cross_product_orthogonal(self):
        """Test that u×v is orthogonal to both u and v."""
        cross = Vector.cross(self.v1, self.v2)

        # Orthogonal means dot product is zero
        self.assertAlmostEqual(cross.dot(self.v1), 0, places=10)
        self.assertAlmostEqual(cross.dot(self.v2), 0, places=10)

    def test_pythagorean_identity(self):
        """Test that |u|^2 + |v|^2 = |u+v|^2 when u·v = 0."""
        # Create orthogonal vectors
        u = Vector(1, 0, 0)
        v = Vector(0, 1, 0)

        # Verify orthogonality
        self.assertEqual(u.dot(v), 0)

        # Check Pythagorean theorem
        lhs = u.norm()**2 + v.norm()**2
        rhs = (u + v).norm()**2
        self.assertAlmostEqual(lhs, rhs, places=10)


# -----------------------------------------------------------------------------
# ADDITIONAL TEST CLASS FOR MATRICES
# -----------------------------------------------------------------------------

class Matrix:
    """A simple matrix class for demonstration."""

    def __init__(self, rows):
        self.rows = [list(row) for row in rows]
        self.num_rows = len(rows)
        self.num_cols = len(rows[0]) if rows else 0

    def __eq__(self, other):
        return self.rows == other.rows

    def transpose(self):
        transposed = [[self.rows[i][j] for i in range(self.num_rows)]
                      for j in range(self.num_cols)]
        return Matrix(transposed)

    def trace(self):
        if self.num_rows != self.num_cols:
            raise ValueError("Trace only defined for square matrices")
        return sum(self.rows[i][i] for i in range(self.num_rows))


class TestMatrix(unittest.TestCase):
    """Test suite for Matrix class."""

    def test_transpose_twice_is_identity(self):
        """Test that (A^T)^T = A."""
        A = Matrix([[1, 2, 3], [4, 5, 6]])
        self.assertEqual(A.transpose().transpose(), A)

    def test_trace_of_identity(self):
        """Test that trace of n×n identity matrix is n."""
        for n in [1, 2, 3, 5, 10]:
            I = Matrix([[1 if i == j else 0 for j in range(n)] for i in range(n)])
            self.assertEqual(I.trace(), n)

    def test_trace_requires_square(self):
        """Test that trace raises error for non-square matrices."""
        A = Matrix([[1, 2, 3], [4, 5, 6]])  # 2x3 matrix
        with self.assertRaises(ValueError):
            A.trace()


# -----------------------------------------------------------------------------
# RUNNING TESTS
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Running unittest tests")
    print("=" * 60)
    print("""
To run with more detail, use:
    python -m unittest 12_unittest_framework -v

To run specific test class:
    python -m unittest 12_unittest_framework.TestVector

To run specific test:
    python -m unittest 12_unittest_framework.TestVector.test_norm
""")

    # Run all tests
    unittest.main(verbosity=2)
