"""
Example 7: Multiple Exception Types and Finally
================================================

Key concepts:
- Catching multiple exception types
- The finally clause (always runs, even after exceptions)
- Exception hierarchy
- Catching all exceptions (use sparingly!)

Mathematical analogy: Think of exceptions as a taxonomy.
Just as groups form a hierarchy (cyclic < abelian < nilpotent < solvable),
exceptions form a hierarchy (ZeroDivisionError < ArithmeticError < Exception).
"""

import math

# -----------------------------------------------------------------------------
# MULTIPLE EXCEPT BLOCKS
# -----------------------------------------------------------------------------

print("=" * 60)
print("PART 1: Multiple except blocks")
print("=" * 60)

def parse_and_compute(expression_str):
    """
    Parse a string like "sqrt(16)" or "log(e)" and compute the result.
    Demonstrates handling different error types separately.
    """
    try:
        # Parse the expression (very simple parser)
        if expression_str.startswith("sqrt("):
            arg = float(expression_str[5:-1])
            return math.sqrt(arg)
        elif expression_str.startswith("log("):
            arg_str = expression_str[4:-1]
            if arg_str == "e":
                arg = math.e
            else:
                arg = float(arg_str)
            return math.log(arg)
        else:
            raise ValueError(f"Unknown function in: {expression_str}")

    except ValueError as e:
        # Could be: float conversion failed, sqrt of negative, unknown function
        print(f"  ValueError: {e}")
        return None

    except ZeroDivisionError:
        # Shouldn't happen here, but demonstrates multiple except
        print(f"  ZeroDivisionError")
        return None

    except SyntaxError:
        print(f"  SyntaxError: Malformed expression")
        return None

# Test various inputs
test_cases = ["sqrt(16)", "sqrt(-4)", "log(e)", "log(0)", "sin(0)", "sqrt(abc)"]
for expr in test_cases:
    result = parse_and_compute(expr)
    print(f"  {expr} -> {result}")

# -----------------------------------------------------------------------------
# CATCHING MULTIPLE EXCEPTIONS IN ONE BLOCK
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 2: Catching multiple exceptions together")
print("=" * 60)

def safe_matrix_element(matrix, i, j):
    """
    Safely access matrix[i][j], handling various index problems.
    """
    try:
        return matrix[i][j]
    except (IndexError, TypeError) as e:
        # Tuple of exception types - catches either
        print(f"  Cannot access [{i}][{j}]: {type(e).__name__}")
        return None

# A 3x3 matrix
M = [
    [1, 2, 3],
    [4, 5, 6],
    [7, 8, 9]
]

print(f"M[1][1] = {safe_matrix_element(M, 1, 1)}")   # 5
print(f"M[5][0] = {safe_matrix_element(M, 5, 0)}")   # IndexError
print(f"M['a'][0] = {safe_matrix_element(M, 'a', 0)}")  # TypeError

# -----------------------------------------------------------------------------
# THE FINALLY CLAUSE
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 3: The finally clause (always executes)")
print("=" * 60)

def compute_with_logging(x):
    """
    Demonstrate that finally always runs.
    Think of finally as "cleanup code" - it runs no matter what.
    """
    print(f"  Starting computation for x={x}")
    try:
        result = 1 / x
        print(f"  Computed 1/x = {result}")
        return result
    except ZeroDivisionError:
        print(f"  Caught division by zero!")
        return float('inf')
    finally:
        # This ALWAYS runs, even if we return early or raise an exception
        print(f"  [finally] Cleanup for x={x}")

print("\nCase 1: Normal execution")
result = compute_with_logging(2)
print(f"  Returned: {result}\n")

print("Case 2: Exception handled")
result = compute_with_logging(0)
print(f"  Returned: {result}\n")

# -----------------------------------------------------------------------------
# FINALLY WITH RESOURCE MANAGEMENT
# -----------------------------------------------------------------------------

print("=" * 60)
print("PART 4: Finally for resource cleanup")
print("=" * 60)

class ExpensiveResource:
    """Simulates a resource that must be cleaned up (like a file or connection)."""

    def __init__(self, name):
        self.name = name
        print(f"  [Resource '{name}' acquired]")

    def use(self, value):
        if value < 0:
            raise ValueError(f"Negative value not allowed: {value}")
        return value ** 2

    def release(self):
        print(f"  [Resource '{self.name}' released]")

def process_values(values):
    """Process values using an expensive resource."""
    resource = ExpensiveResource("GPU")
    try:
        results = []
        for v in values:
            results.append(resource.use(v))
        return results
    except ValueError as e:
        print(f"  Error: {e}")
        return None
    finally:
        # Resource is ALWAYS released, even on error
        resource.release()

print("\nProcessing [1, 2, 3]:")
print(f"  Results: {process_values([1, 2, 3])}")

print("\nProcessing [1, -2, 3]:")
print(f"  Results: {process_values([1, -2, 3])}")

# -----------------------------------------------------------------------------
# EXCEPTION HIERARCHY
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 5: Exception hierarchy")
print("=" * 60)

# Python exceptions form a hierarchy. Catching a parent catches all children.
#
# BaseException
# └── Exception
#     ├── ArithmeticError
#     │   ├── ZeroDivisionError
#     │   ├── OverflowError
#     │   └── FloatingPointError
#     ├── LookupError
#     │   ├── IndexError
#     │   └── KeyError
#     ├── ValueError
#     ├── TypeError
#     └── ... many others

def demonstrate_hierarchy(operation, x):
    """Show how exception hierarchy works."""
    try:
        return operation(x)
    except ArithmeticError as e:
        # Catches ZeroDivisionError, OverflowError, etc.
        print(f"  ArithmeticError caught: {type(e).__name__}: {e}")
        return None

# ZeroDivisionError is a subclass of ArithmeticError
print("1/0:")
demonstrate_hierarchy(lambda x: 1/x, 0)

# OverflowError is also a subclass of ArithmeticError
print("\nmath.exp(1000):")
demonstrate_hierarchy(lambda x: math.exp(x), 1000)

# ValueError is NOT a subclass of ArithmeticError - won't be caught!
print("\nmath.sqrt(-1):")
try:
    demonstrate_hierarchy(lambda x: math.sqrt(x), -1)
except ValueError as e:
    print(f"  ValueError escaped! Caught in outer handler: {e}")

# -----------------------------------------------------------------------------
# CATCHING ALL EXCEPTIONS (use carefully!)
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 6: Catching all exceptions")
print("=" * 60)

def risky_operation(x):
    """An operation that could fail in many ways."""
    if x == 0:
        raise ZeroDivisionError("x is zero")
    if x < 0:
        raise ValueError("x is negative")
    if x > 100:
        raise OverflowError("x is too large")
    return math.sqrt(x)

def ultra_safe_compute(x):
    """
    Catch ANY exception. Use sparingly - you might hide bugs!
    """
    try:
        return risky_operation(x)
    except Exception as e:
        # Exception catches almost everything
        # (but not KeyboardInterrupt or SystemExit)
        print(f"  Caught {type(e).__name__}: {e}")
        return None

for x in [4, 0, -1, 200]:
    print(f"ultra_safe_compute({x}) = {ultra_safe_compute(x)}")

print("""
WARNING: Catching all exceptions can hide bugs!
Prefer catching specific exceptions when possible.
Use "except Exception" only when you truly want to catch anything.
""")

# -----------------------------------------------------------------------------
# COMPLETE TRY/EXCEPT/ELSE/FINALLY PATTERN
# -----------------------------------------------------------------------------

print("=" * 60)
print("PART 7: Complete pattern")
print("=" * 60)

def complete_example(a, b):
    """Demonstrate all four clauses together."""
    print(f"\n  Computing {a} / {b}...")
    try:
        result = a / b
    except ZeroDivisionError:
        print("  [except] Division by zero!")
        result = float('inf')
    except TypeError:
        print("  [except] Invalid types!")
        result = None
    else:
        # Runs ONLY if no exception occurred
        print(f"  [else] Success! Result = {result}")
    finally:
        # ALWAYS runs
        print("  [finally] Cleanup complete")

    return result

complete_example(10, 2)    # Normal case
complete_example(10, 0)    # ZeroDivisionError
complete_example("a", 2)   # TypeError

print("""
Order of execution:
1. try block runs
2. If exception: matching except block runs
   If no exception: else block runs
3. finally block ALWAYS runs
4. Function returns (or exception propagates if not caught)
""")
