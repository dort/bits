"""
Example 6: Exception Handling Basics
====================================

Key concepts:
- Exceptions are Python's way of handling errors at runtime
- try/except blocks let you catch and handle errors gracefully
- Without handling, exceptions crash your program

Mathematical analogy: Exceptions are like undefined operations.
Just as you can't divide by zero or take sqrt(-1) in the reals,
Python can't perform certain operations and "raises an exception."
"""

# -----------------------------------------------------------------------------
# WHAT HAPPENS WITHOUT EXCEPTION HANDLING
# -----------------------------------------------------------------------------

print("=" * 60)
print("PART 1: Unhandled exceptions crash the program")
print("=" * 60)

# Uncomment any of these to see the crash:
# result = 1 / 0                    # ZeroDivisionError
# result = int("hello")             # ValueError
# result = [1, 2, 3][10]            # IndexError
# result = {"a": 1}["b"]            # KeyError

print("(Commented out to prevent crash - try uncommenting one!)\n")

# -----------------------------------------------------------------------------
# BASIC TRY/EXCEPT
# -----------------------------------------------------------------------------

print("=" * 60)
print("PART 2: Basic try/except")
print("=" * 60)

# The try block contains code that might fail
# The except block runs if an error occurs

def safe_divide(a, b):
    """Divide a by b, handling division by zero."""
    try:
        result = a / b
        return result
    except ZeroDivisionError:
        print(f"  Warning: Cannot divide {a} by zero!")
        return None  # or float('inf'), or raise a different error

# Test it
print(f"10 / 2 = {safe_divide(10, 2)}")
print(f"10 / 0 = {safe_divide(10, 0)}")
print(f"5 / 3 = {safe_divide(5, 3)}")

# -----------------------------------------------------------------------------
# MATHEMATICAL DOMAIN ERRORS
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 3: Mathematical domain errors")
print("=" * 60)

import math

def safe_sqrt(x):
    """Compute square root, handling negative numbers."""
    try:
        return math.sqrt(x)
    except ValueError:
        print(f"  Warning: sqrt({x}) is not real")
        return complex(0, math.sqrt(abs(x)))  # Return imaginary result

print(f"sqrt(16) = {safe_sqrt(16)}")
print(f"sqrt(-16) = {safe_sqrt(-16)}")
print(f"sqrt(2) = {safe_sqrt(2)}")

def safe_log(x):
    """Compute natural log, handling non-positive numbers."""
    try:
        return math.log(x)
    except ValueError:
        print(f"  Warning: log({x}) is undefined")
        return float('-inf') if x == 0 else float('nan')

print(f"\nlog(e) = {safe_log(math.e)}")
print(f"log(0) = {safe_log(0)}")
print(f"log(-1) = {safe_log(-1)}")

# -----------------------------------------------------------------------------
# CATCHING THE EXCEPTION OBJECT
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 4: Accessing exception details")
print("=" * 60)

# Use "as e" to capture the exception object
def analyze_error(x):
    try:
        result = math.log(math.sqrt(x))
        return result
    except ValueError as e:
        # 'e' contains information about what went wrong
        print(f"  Caught ValueError: {e}")
        print(f"  Exception type: {type(e).__name__}")
        return None

print(f"f(4) = {analyze_error(4)}")      # log(sqrt(4)) = log(2)
print(f"f(-4) = {analyze_error(-4)}")    # sqrt(-4) fails

# -----------------------------------------------------------------------------
# INDEX AND KEY ERRORS (common in numerical computing)
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 5: Index and Key errors")
print("=" * 60)

# Working with sequences (vectors, lists)
def safe_get_element(vector, index):
    """Safely get element from a vector."""
    try:
        return vector[index]
    except IndexError:
        print(f"  Warning: Index {index} out of bounds for vector of length {len(vector)}")
        return None

v = [1, 2, 3, 4, 5]  # A vector in R^5
print(f"v = {v}")
print(f"v[2] = {safe_get_element(v, 2)}")
print(f"v[10] = {safe_get_element(v, 10)}")
print(f"v[-1] = {safe_get_element(v, -1)}")  # Python supports negative indexing!

# Working with dictionaries (labeled data)
def safe_get_param(params, key):
    """Safely get a parameter from a dictionary."""
    try:
        return params[key]
    except KeyError:
        print(f"  Warning: Parameter '{key}' not found")
        return None

params = {"sigma": 10.0, "rho": 28.0, "beta": 2.667}
print(f"\nparams = {params}")
print(f"sigma = {safe_get_param(params, 'sigma')}")
print(f"gamma = {safe_get_param(params, 'gamma')}")

# -----------------------------------------------------------------------------
# TYPE ERRORS
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 6: Type errors")
print("=" * 60)

def compute_norm(vector):
    """Compute Euclidean norm of a vector."""
    try:
        squared_sum = sum(x**2 for x in vector)
        return math.sqrt(squared_sum)
    except TypeError as e:
        print(f"  TypeError: {e}")
        print(f"  Hint: Expected a sequence of numbers")
        return None

print(f"norm([3, 4]) = {compute_norm([3, 4])}")           # Should be 5
print(f"norm([1, 2, 3]) = {compute_norm([1, 2, 3])}")     # sqrt(14)
print(f"norm('hello') = {compute_norm('hello')}")         # Type error
print(f"norm(42) = {compute_norm(42)}")                   # Type error

# -----------------------------------------------------------------------------
# THE ELSE CLAUSE (runs only if NO exception occurred)
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 7: The else clause")
print("=" * 60)

def quadratic_roots(a, b, c):
    """
    Find roots of ax^2 + bx + c = 0.
    Returns (root1, root2) or None if no real roots.
    """
    try:
        discriminant = b**2 - 4*a*c
        sqrt_disc = math.sqrt(discriminant)
    except ValueError:
        # Negative discriminant - no real roots
        print(f"  No real roots (discriminant = {b**2 - 4*a*c})")
        return None
    else:
        # This runs only if try block succeeded (discriminant >= 0)
        root1 = (-b + sqrt_disc) / (2*a)
        root2 = (-b - sqrt_disc) / (2*a)
        print(f"  Found real roots!")
        return (root1, root2)

print("x^2 - 5x + 6 = 0:")
print(f"  Roots: {quadratic_roots(1, -5, 6)}")  # (3, 2)

print("\nx^2 + 1 = 0:")
print(f"  Roots: {quadratic_roots(1, 0, 1)}")   # No real roots

print("\nx^2 - 2x + 1 = 0:")
print(f"  Roots: {quadratic_roots(1, -2, 1)}")  # (1, 1) - repeated root

# -----------------------------------------------------------------------------
# SUMMARY
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("SUMMARY: Basic Exception Handling Pattern")
print("=" * 60)
print("""
try:
    # Code that might fail
    result = risky_operation()
except SomeError as e:
    # Handle the error
    print(f"Error occurred: {e}")
    result = fallback_value
else:
    # Runs only if no exception (optional)
    print("Success!")

Common mathematical exceptions:
- ZeroDivisionError: division by zero
- ValueError: math domain error (sqrt(-1), log(0))
- IndexError: vector index out of bounds
- TypeError: wrong type (string instead of number)
""")
