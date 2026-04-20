"""
Example 3: CSV Files and Matrix Operations
==========================================

Key concepts:
- The csv module for reading/writing CSV (Comma-Separated Values) files
- Storing matrices as 2D arrays
- Reading data into usable mathematical structures

CSV is the "lingua franca" of data exchange - nearly every tool can read/write it.
"""

import csv
import math

# -----------------------------------------------------------------------------
# WRITING A MATRIX TO CSV (manual approach first, to understand the format)
# -----------------------------------------------------------------------------

# Define a 3x3 rotation matrix (rotate by theta in 2D, embedded in 3D)
theta = math.pi / 4  # 45 degrees

rotation_matrix = [
    [math.cos(theta), -math.sin(theta), 0],
    [math.sin(theta),  math.cos(theta), 0],
    [0,                0,               1]
]

# Manual approach (for understanding)
with open("rotation_matrix_manual.csv", "w") as f:
    for row in rotation_matrix:
        # Join numbers with commas
        line = ",".join(str(x) for x in row)
        f.write(line + "\n")

print("Manual CSV written to 'rotation_matrix_manual.csv'")

# -----------------------------------------------------------------------------
# WRITING WITH THE CSV MODULE (recommended approach)
# -----------------------------------------------------------------------------

# The csv module handles edge cases (commas in data, quotes, etc.)
with open("rotation_matrix.csv", "w", newline="") as f:
    writer = csv.writer(f)

    # Write a header row (optional but helpful)
    writer.writerow(["col_0", "col_1", "col_2"])

    # Write data rows
    for row in rotation_matrix:
        writer.writerow(row)

print("CSV module version written to 'rotation_matrix.csv'")

# -----------------------------------------------------------------------------
# READING A MATRIX FROM CSV
# -----------------------------------------------------------------------------

def read_matrix_from_csv(filename, has_header=True):
    """Read a CSV file into a 2D list of floats (a matrix)."""
    matrix = []
    with open(filename, "r", newline="") as f:
        reader = csv.reader(f)

        if has_header:
            header = next(reader)  # Skip the header row
            print(f"Header: {header}")

        for row in reader:
            # Convert each element from string to float
            numeric_row = [float(x) for x in row]
            matrix.append(numeric_row)

    return matrix

R = read_matrix_from_csv("rotation_matrix.csv")
print(f"\nMatrix R (read from file):")
for row in R:
    print([f"{x:8.5f}" for x in row])

# -----------------------------------------------------------------------------
# MATRIX OPERATIONS (to verify the data is correct)
# -----------------------------------------------------------------------------

def matrix_multiply(A, B):
    """Multiply two matrices A and B. Returns AB."""
    rows_A, cols_A = len(A), len(A[0])
    rows_B, cols_B = len(B), len(B[0])

    if cols_A != rows_B:
        raise ValueError(f"Cannot multiply {rows_A}x{cols_A} by {rows_B}x{cols_B}")

    # Initialize result matrix with zeros
    result = [[0.0 for _ in range(cols_B)] for _ in range(rows_A)]

    for i in range(rows_A):
        for j in range(cols_B):
            for k in range(cols_A):
                result[i][j] += A[i][k] * B[k][j]

    return result

def transpose(M):
    """Transpose a matrix."""
    rows, cols = len(M), len(M[0])
    return [[M[i][j] for i in range(rows)] for j in range(cols)]

# For a rotation matrix R, R^T * R = I (orthogonality)
R_transpose = transpose(R)
should_be_identity = matrix_multiply(R_transpose, R)

print("\nR^T * R (should be identity):")
for row in should_be_identity:
    print([f"{x:8.5f}" for x in row])

# -----------------------------------------------------------------------------
# STORING A DATASET WITH HEADERS
# -----------------------------------------------------------------------------

# Generate eigenvalue data: for A = [[a, b], [c, d]], eigenvalues are
# lambda = (a+d)/2 +/- sqrt((a+d)^2/4 - (ad-bc))

import random
random.seed(42)  # For reproducibility

# Generate random 2x2 matrices and compute their eigenvalues
dataset = []
for i in range(100):
    a, b = random.uniform(-5, 5), random.uniform(-5, 5)
    c, d = random.uniform(-5, 5), random.uniform(-5, 5)

    trace = a + d
    det = a * d - b * c
    discriminant = (trace / 2) ** 2 - det

    if discriminant >= 0:
        lambda1 = trace / 2 + math.sqrt(discriminant)
        lambda2 = trace / 2 - math.sqrt(discriminant)
        eigenvalue_type = "real"
    else:
        lambda1 = trace / 2  # Real part
        lambda2 = math.sqrt(-discriminant)  # Imaginary part magnitude
        eigenvalue_type = "complex"

    dataset.append({
        "a": a, "b": b, "c": c, "d": d,
        "trace": trace, "det": det,
        "lambda1": lambda1, "lambda2": lambda2,
        "type": eigenvalue_type
    })

# Write to CSV with DictWriter (handles dictionaries)
with open("eigenvalue_dataset.csv", "w", newline="") as f:
    fieldnames = ["a", "b", "c", "d", "trace", "det", "lambda1", "lambda2", "type"]
    writer = csv.DictWriter(f, fieldnames=fieldnames)

    writer.writeheader()  # Write the column names
    for row in dataset:
        writer.writerow(row)

print(f"\nWrote {len(dataset)} matrices with eigenvalues to 'eigenvalue_dataset.csv'")

# -----------------------------------------------------------------------------
# READING WITH DictReader (access columns by name)
# -----------------------------------------------------------------------------

with open("eigenvalue_dataset.csv", "r", newline="") as f:
    reader = csv.DictReader(f)

    real_count = 0
    complex_count = 0
    positive_definite_count = 0

    for row in reader:
        # DictReader gives you dictionaries with column names as keys
        # Note: values are still strings, must convert!
        if row["type"] == "real":
            real_count += 1
            lambda1 = float(row["lambda1"])
            lambda2 = float(row["lambda2"])
            if lambda1 > 0 and lambda2 > 0:
                positive_definite_count += 1
        else:
            complex_count += 1

print(f"\nDataset analysis:")
print(f"  Matrices with real eigenvalues: {real_count}")
print(f"  Matrices with complex eigenvalues: {complex_count}")
print(f"  Positive definite matrices: {positive_definite_count}")
