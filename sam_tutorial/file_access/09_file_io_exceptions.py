"""
Example 9: Exception Handling in File I/O
=========================================

Key concepts:
- File-related exceptions: FileNotFoundError, PermissionError, etc.
- Graceful degradation when files are missing or corrupt
- Validating file contents
- Combining file I/O with data validation

This connects file I/O (Examples 1-5) with exception handling (Examples 6-8).
"""

import os
import json
import csv
import math

# -----------------------------------------------------------------------------
# BASIC FILE EXCEPTIONS
# -----------------------------------------------------------------------------

print("=" * 60)
print("PART 1: Common file exceptions")
print("=" * 60)

# FileNotFoundError
print("\n1. FileNotFoundError:")
try:
    with open("nonexistent_file.txt", "r") as f:
        content = f.read()
except FileNotFoundError as e:
    print(f"   {e}")

# PermissionError (may not trigger on all systems)
print("\n2. PermissionError:")
try:
    # Try to write to a system directory
    with open("/root/test.txt", "w") as f:
        f.write("test")
except PermissionError as e:
    print(f"   Cannot write to protected location")
except FileNotFoundError as e:
    print(f"   Directory doesn't exist (different error)")

# IsADirectoryError
print("\n3. IsADirectoryError:")
try:
    with open(".", "r") as f:  # "." is the current directory
        content = f.read()
except IsADirectoryError as e:
    print(f"   Cannot read a directory as a file")

# -----------------------------------------------------------------------------
# ROBUST FILE READING
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 2: Robust file reading with defaults")
print("=" * 60)

def load_config(filename, defaults=None):
    """
    Load JSON configuration, returning defaults if file is missing or invalid.
    """
    if defaults is None:
        defaults = {}

    try:
        with open(filename, "r") as f:
            config = json.load(f)
        print(f"   Loaded config from '{filename}'")
        return config

    except FileNotFoundError:
        print(f"   Config file '{filename}' not found, using defaults")
        return defaults

    except json.JSONDecodeError as e:
        print(f"   Config file '{filename}' is not valid JSON: {e}")
        return defaults

    except PermissionError:
        print(f"   Cannot read '{filename}' (permission denied), using defaults")
        return defaults

# Test with various scenarios
default_params = {"sigma": 10.0, "rho": 28.0, "beta": 2.667}

print("\nCase 1: File doesn't exist")
config = load_config("missing_config.json", default_params)
print(f"   Result: {config}")

print("\nCase 2: Create an invalid JSON file")
with open("bad_config.json", "w") as f:
    f.write("{ this is not valid json }")
config = load_config("bad_config.json", default_params)
print(f"   Result: {config}")

print("\nCase 3: Valid file (from example 05)")
config = load_config("lorenz_config.json", default_params)
print(f"   Result keys: {list(config.keys())}")

# Cleanup
os.remove("bad_config.json")

# -----------------------------------------------------------------------------
# VALIDATING FILE CONTENTS
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 3: Validating numerical data from files")
print("=" * 60)

class DataValidationError(Exception):
    """Raised when file data doesn't meet requirements."""
    pass

def load_matrix_from_csv(filename):
    """
    Load a numeric matrix from CSV with validation.
    Raises DataValidationError if data is invalid.
    """
    try:
        with open(filename, "r", newline="") as f:
            reader = csv.reader(f)

            # Skip header if present
            first_row = next(reader)
            try:
                # Try to parse as numbers
                matrix = [[float(x) for x in first_row]]
            except ValueError:
                # First row was a header, skip it
                matrix = []

            # Read remaining rows
            expected_cols = len(matrix[0]) if matrix else None

            for line_num, row in enumerate(reader, start=2):
                if not row:  # Skip empty rows
                    continue

                # Validate row length
                if expected_cols is not None and len(row) != expected_cols:
                    raise DataValidationError(
                        f"Line {line_num}: expected {expected_cols} columns, got {len(row)}"
                    )

                # Convert to floats
                try:
                    numeric_row = [float(x) for x in row]
                except ValueError as e:
                    raise DataValidationError(
                        f"Line {line_num}: non-numeric value: {e}"
                    )

                # Check for NaN or infinity
                for i, val in enumerate(numeric_row):
                    if math.isnan(val) or math.isinf(val):
                        raise DataValidationError(
                            f"Line {line_num}, column {i}: invalid value {val}"
                        )

                matrix.append(numeric_row)
                if expected_cols is None:
                    expected_cols = len(numeric_row)

        if not matrix:
            raise DataValidationError("File contains no numeric data")

        return matrix

    except FileNotFoundError:
        raise DataValidationError(f"File '{filename}' not found")

# Create test files
print("Creating test files...")

# Valid matrix
with open("valid_matrix.csv", "w") as f:
    f.write("1,2,3\n4,5,6\n7,8,9\n")

# Matrix with text
with open("invalid_matrix.csv", "w") as f:
    f.write("1,2,3\n4,five,6\n7,8,9\n")

# Matrix with inconsistent columns
with open("ragged_matrix.csv", "w") as f:
    f.write("1,2,3\n4,5\n7,8,9\n")

# Test loading
for filename in ["valid_matrix.csv", "invalid_matrix.csv", "ragged_matrix.csv", "missing.csv"]:
    print(f"\nLoading '{filename}':")
    try:
        matrix = load_matrix_from_csv(filename)
        print(f"   Success! Matrix shape: {len(matrix)}x{len(matrix[0])}")
    except DataValidationError as e:
        print(f"   Validation error: {e}")

# Cleanup
for f in ["valid_matrix.csv", "invalid_matrix.csv", "ragged_matrix.csv"]:
    if os.path.exists(f):
        os.remove(f)

# -----------------------------------------------------------------------------
# ATOMIC FILE WRITES (avoiding corruption)
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 4: Safe file writing")
print("=" * 60)

def safe_write_json(filename, data):
    """
    Write JSON data safely using a temporary file.
    If writing fails, the original file is preserved.
    """
    temp_filename = filename + ".tmp"

    try:
        # Write to temporary file first
        with open(temp_filename, "w") as f:
            json.dump(data, f, indent=2)

        # Only rename if write succeeded
        os.replace(temp_filename, filename)  # Atomic on most systems
        print(f"   Successfully wrote to '{filename}'")
        return True

    except (IOError, OSError, TypeError) as e:
        print(f"   Failed to write '{filename}': {e}")
        # Clean up temp file if it exists
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        return False

# Test safe writing
data = {"values": [1, 2, 3], "computed": math.pi}
safe_write_json("safe_output.json", data)

# Verify it worked
with open("safe_output.json", "r") as f:
    loaded = json.load(f)
print(f"   Verified: {loaded}")

# Cleanup
os.remove("safe_output.json")

# -----------------------------------------------------------------------------
# READING FILES WITH ENCODING ISSUES
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 5: Handling encoding issues")
print("=" * 60)

def read_text_file(filename, encodings=None):
    """
    Try to read a file with multiple encodings.
    Returns (content, encoding_used) or raises an error.
    """
    if encodings is None:
        encodings = ["utf-8", "latin-1", "cp1252"]

    last_error = None

    for encoding in encodings:
        try:
            with open(filename, "r", encoding=encoding) as f:
                content = f.read()
            return content, encoding
        except UnicodeDecodeError as e:
            last_error = e
            continue
        except FileNotFoundError:
            raise

    raise UnicodeDecodeError(
        f"none",
        b"",
        0,
        0,
        f"Could not decode with any of: {encodings}"
    )

# Create a test file with UTF-8 content
with open("unicode_test.txt", "w", encoding="utf-8") as f:
    f.write("Mathematics: ∫ f(x)dx, √2, π, ∑, ∏, ∈, ∀, ∃\n")
    f.write("Greek: α, β, γ, δ, ε, θ, λ, μ, σ, ω\n")

content, encoding = read_text_file("unicode_test.txt")
print(f"   Read with encoding: {encoding}")
print(f"   Content: {content}")

os.remove("unicode_test.txt")

# -----------------------------------------------------------------------------
# CONTEXT MANAGER PATTERN FOR CLEANUP
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("PART 6: Context managers for complex cleanup")
print("=" * 60)

class ComputationLogger:
    """
    A context manager that logs computation results to a file.
    Ensures proper cleanup even if computation fails.
    """

    def __init__(self, log_filename):
        self.log_filename = log_filename
        self.log_file = None
        self.results = []

    def __enter__(self):
        """Called when entering the 'with' block."""
        self.log_file = open(self.log_filename, "w")
        self.log_file.write("=== Computation Log ===\n")
        print(f"   Opened log file: {self.log_filename}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Called when exiting the 'with' block (even on exception)."""
        if exc_type is not None:
            self.log_file.write(f"\nERROR: {exc_type.__name__}: {exc_val}\n")
            print(f"   Exception occurred: {exc_type.__name__}")
        else:
            self.log_file.write("\nCompleted successfully.\n")

        self.log_file.write(f"Total results logged: {len(self.results)}\n")
        self.log_file.close()
        print(f"   Closed log file: {self.log_filename}")

        # Return False to propagate exception, True to suppress it
        return False

    def log_result(self, name, value):
        """Log a computation result."""
        self.results.append((name, value))
        self.log_file.write(f"{name} = {value}\n")

# Use the context manager
print("\nSuccessful computation:")
with ComputationLogger("computation.log") as logger:
    logger.log_result("sqrt(2)", math.sqrt(2))
    logger.log_result("pi", math.pi)
    logger.log_result("e", math.e)

print("\nComputation with error:")
try:
    with ComputationLogger("error_computation.log") as logger:
        logger.log_result("sqrt(2)", math.sqrt(2))
        logger.log_result("sqrt(-1)", math.sqrt(-1))  # This will fail
        logger.log_result("e", math.e)  # Never reached
except ValueError as e:
    print(f"   Caught: {e}")

# Show log contents
print("\nLog file contents (with error):")
with open("error_computation.log", "r") as f:
    print(f.read())

# Cleanup
os.remove("computation.log")
os.remove("error_computation.log")

print("""
Summary: File I/O Exception Handling Best Practices
===================================================
1. Always use 'with' for automatic file closing
2. Catch specific exceptions (FileNotFoundError, PermissionError, etc.)
3. Provide sensible defaults when files are missing
4. Validate file contents before using data
5. Use atomic writes to prevent corruption
6. Handle encoding issues explicitly
7. Use context managers for complex resource cleanup
""")
