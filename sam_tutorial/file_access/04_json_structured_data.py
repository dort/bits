"""
Example 4: JSON for Structured Mathematical Data
================================================

Key concepts:
- JSON (JavaScript Object Notation) stores hierarchical/nested data
- Perfect for mathematical objects with multiple attributes
- The json module converts between Python dicts/lists and JSON strings

JSON is ideal when your data has structure beyond a simple table.
Think: a polynomial (coefficients + degree + roots), a graph (vertices + edges),
or experiment results (parameters + measurements + metadata).
"""

import json
import math

# -----------------------------------------------------------------------------
# BASIC JSON: Writing and Reading
# -----------------------------------------------------------------------------

# A polynomial can be represented as a dictionary
polynomial = {
    "name": "Chebyshev T_4",
    "degree": 4,
    "coefficients": [1, 0, -8, 0, 8],  # 1 - 8x^2 + 8x^4 (ascending powers)
    "roots": [
        math.cos(math.pi * (2*k - 1) / 8) for k in range(1, 5)
    ],
    "properties": {
        "orthogonal": True,
        "interval": [-1, 1],
        "weight_function": "1/sqrt(1-x^2)"
    }
}

# Write to JSON file
with open("polynomial.json", "w") as f:
    json.dump(polynomial, f, indent=2)  # indent makes it human-readable

print("Polynomial written to 'polynomial.json'")
print("\nJSON content:")
with open("polynomial.json", "r") as f:
    print(f.read())

# Read from JSON file
with open("polynomial.json", "r") as f:
    loaded_poly = json.load(f)

# Now it's a Python dictionary - we can compute with it!
print(f"\nLoaded polynomial: {loaded_poly['name']}")
print(f"Degree: {loaded_poly['degree']}")
print(f"Roots: {[f'{r:.6f}' for r in loaded_poly['roots']]}")

# Verify: evaluate polynomial at its roots (should be ~0)
def evaluate_polynomial(coeffs, x):
    """Evaluate polynomial with coefficients [a_0, a_1, ..., a_n] at x."""
    return sum(c * (x ** i) for i, c in enumerate(coeffs))

print("\nVerification (polynomial at roots):")
for root in loaded_poly["roots"]:
    value = evaluate_polynomial(loaded_poly["coefficients"], root)
    print(f"  T_4({root:.6f}) = {value:.2e}")

# -----------------------------------------------------------------------------
# STORING COMPLEX MATHEMATICAL STRUCTURES
# -----------------------------------------------------------------------------

# Store a graph (vertices and edges) - useful in combinatorics, topology
petersen_graph = {
    "name": "Petersen Graph",
    "description": "A famous graph in graph theory, counterexample to many conjectures",
    "vertices": list(range(10)),
    "edges": [
        # Outer pentagon
        [0, 1], [1, 2], [2, 3], [3, 4], [4, 0],
        # Inner pentagram
        [5, 7], [7, 9], [9, 6], [6, 8], [8, 5],
        # Spokes
        [0, 5], [1, 6], [2, 7], [3, 8], [4, 9]
    ],
    "properties": {
        "num_vertices": 10,
        "num_edges": 15,
        "regular": True,
        "degree": 3,
        "chromatic_number": 3,
        "is_planar": False,
        "is_hamiltonian": False
    }
}

with open("petersen_graph.json", "w") as f:
    json.dump(petersen_graph, f, indent=2)

print("\nPetersen graph saved to 'petersen_graph.json'")

# -----------------------------------------------------------------------------
# STORING COMPUTATION RESULTS WITH METADATA
# -----------------------------------------------------------------------------

# Numerical integration results
def simpsons_rule(f, a, b, n):
    """Approximate integral of f from a to b using Simpson's rule with n intervals."""
    if n % 2 == 1:
        n += 1  # Simpson's rule requires even number of intervals
    h = (b - a) / n
    result = f(a) + f(b)

    for i in range(1, n):
        x = a + i * h
        if i % 2 == 0:
            result += 2 * f(x)
        else:
            result += 4 * f(x)

    return result * h / 3

# Compute integral of sin(x) from 0 to pi (exact value = 2)
results = {
    "integral": {
        "function": "sin(x)",
        "lower_bound": 0,
        "upper_bound": "pi",
        "exact_value": 2.0
    },
    "method": "Simpson's Rule",
    "experiments": []
}

for n in [4, 8, 16, 32, 64, 128, 256]:
    approximation = simpsons_rule(math.sin, 0, math.pi, n)
    error = abs(approximation - 2.0)

    results["experiments"].append({
        "n_intervals": n,
        "approximation": approximation,
        "absolute_error": error,
        "relative_error": error / 2.0
    })

with open("integration_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("Integration results saved to 'integration_results.json'")

# Read and analyze
with open("integration_results.json", "r") as f:
    data = json.load(f)

print(f"\nConvergence analysis for integral of {data['integral']['function']}:")
print(f"{'n':>6} {'approx':>15} {'error':>12} {'ratio':>8}")
print("-" * 45)

prev_error = None
for exp in data["experiments"]:
    n = exp["n_intervals"]
    approx = exp["approximation"]
    error = exp["absolute_error"]

    ratio_str = ""
    if prev_error is not None and error > 0:
        ratio = prev_error / error
        ratio_str = f"{ratio:.2f}"  # Should be ~16 for Simpson's (4th order)

    print(f"{n:>6} {approx:>15.12f} {error:>12.2e} {ratio_str:>8}")
    prev_error = error

# -----------------------------------------------------------------------------
# JSON LIMITATIONS AND WORKAROUNDS
# -----------------------------------------------------------------------------

"""
JSON cannot directly store:
1. Complex numbers (use: {"real": 1.0, "imag": 2.0} or "1+2j")
2. numpy arrays (use: .tolist() to convert to list)
3. Infinity/NaN (use: "Infinity", "-Infinity", "NaN" as strings)
4. Tuples (stored as lists - you lose the distinction)
5. Sets (convert to list first)

Example: storing complex eigenvalues
"""

complex_data = {
    "matrix": [[0, -1], [1, 0]],  # 90-degree rotation
    "eigenvalues": [
        {"real": 0, "imag": 1},   # i
        {"real": 0, "imag": -1}   # -i
    ],
    "note": "Eigenvalues stored as {real, imag} pairs since JSON has no complex type"
}

with open("complex_eigenvalues.json", "w") as f:
    json.dump(complex_data, f, indent=2)

# Reading back and reconstructing complex numbers
with open("complex_eigenvalues.json", "r") as f:
    data = json.load(f)

eigenvalues = [complex(e["real"], e["imag"]) for e in data["eigenvalues"]]
print(f"\nReconstructed complex eigenvalues: {eigenvalues}")

# -----------------------------------------------------------------------------
# PRETTY PRINTING FOR DEBUGGING
# -----------------------------------------------------------------------------

# json.dumps() returns a string (instead of writing to file)
# Useful for debugging or logging
print("\nPretty-printed JSON string:")
print(json.dumps(complex_data, indent=4))
