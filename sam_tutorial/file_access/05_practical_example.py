"""
Example 5: Practical Workflow - ODE Solver with Logging
=======================================================

This example combines multiple file I/O concepts in a realistic scenario:
- Configuration from JSON
- Results to CSV
- Human-readable log file
- Error handling

We'll solve the Lorenz system (famous chaotic attractor) and save the trajectory.
"""

import json
import csv
import os
from datetime import datetime

# -----------------------------------------------------------------------------
# CONFIGURATION: Read parameters from JSON
# -----------------------------------------------------------------------------

# First, create a default config file
default_config = {
    "system": "lorenz",
    "parameters": {
        "sigma": 10.0,
        "rho": 28.0,
        "beta": 8.0 / 3.0
    },
    "initial_conditions": [1.0, 1.0, 1.0],
    "simulation": {
        "t_start": 0.0,
        "t_end": 50.0,
        "dt": 0.01
    },
    "output": {
        "save_every": 10,
        "csv_file": "lorenz_trajectory.csv",
        "log_file": "simulation.log"
    }
}

# Save default config if it doesn't exist
config_file = "lorenz_config.json"
if not os.path.exists(config_file):
    with open(config_file, "w") as f:
        json.dump(default_config, f, indent=2)
    print(f"Created default config: {config_file}")
else:
    print(f"Using existing config: {config_file}")

# Load configuration
with open(config_file, "r") as f:
    config = json.load(f)

# Extract parameters
sigma = config["parameters"]["sigma"]
rho = config["parameters"]["rho"]
beta = config["parameters"]["beta"]
x0, y0, z0 = config["initial_conditions"]
t_start = config["simulation"]["t_start"]
t_end = config["simulation"]["t_end"]
dt = config["simulation"]["dt"]
save_every = config["output"]["save_every"]

# -----------------------------------------------------------------------------
# LOGGING: Track what the simulation does
# -----------------------------------------------------------------------------

class Logger:
    """Simple logger that writes to both console and file."""

    def __init__(self, filename):
        self.filename = filename
        # 'w' mode overwrites; use 'a' to append to existing log
        self.file = open(filename, "w")
        self.log(f"=== Simulation Log Started: {datetime.now()} ===")

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] [{level}] {message}"
        print(formatted)
        self.file.write(formatted + "\n")
        self.file.flush()  # Ensure it's written immediately

    def close(self):
        self.log("=== Simulation Log Ended ===")
        self.file.close()

logger = Logger(config["output"]["log_file"])

# -----------------------------------------------------------------------------
# THE LORENZ SYSTEM
# -----------------------------------------------------------------------------

def lorenz_derivatives(state, sigma, rho, beta):
    """
    Compute derivatives for the Lorenz system:
        dx/dt = sigma * (y - x)
        dy/dt = x * (rho - z) - y
        dz/dt = x * y - beta * z
    """
    x, y, z = state
    dx = sigma * (y - x)
    dy = x * (rho - z) - y
    dz = x * y - beta * z
    return [dx, dy, dz]

def rk4_step(state, dt, sigma, rho, beta):
    """
    Fourth-order Runge-Kutta integration step.
    This is the workhorse of numerical ODE solving.
    """
    k1 = lorenz_derivatives(state, sigma, rho, beta)

    state2 = [s + 0.5 * dt * k for s, k in zip(state, k1)]
    k2 = lorenz_derivatives(state2, sigma, rho, beta)

    state3 = [s + 0.5 * dt * k for s, k in zip(state, k2)]
    k3 = lorenz_derivatives(state3, sigma, rho, beta)

    state4 = [s + dt * k for s, k in zip(state, k3)]
    k4 = lorenz_derivatives(state4, sigma, rho, beta)

    new_state = [
        s + (dt / 6) * (k1i + 2*k2i + 2*k3i + k4i)
        for s, k1i, k2i, k3i, k4i in zip(state, k1, k2, k3, k4)
    ]

    return new_state

# -----------------------------------------------------------------------------
# RUN SIMULATION AND SAVE RESULTS
# -----------------------------------------------------------------------------

logger.log(f"Lorenz system with sigma={sigma}, rho={rho}, beta={beta:.4f}")
logger.log(f"Initial conditions: ({x0}, {y0}, {z0})")
logger.log(f"Time span: [{t_start}, {t_end}], dt={dt}")

# Open CSV file for writing trajectory
csv_filename = config["output"]["csv_file"]
with open(csv_filename, "w", newline="") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["t", "x", "y", "z"])  # Header

    # Initialize
    state = [x0, y0, z0]
    t = t_start
    step = 0
    saved_points = 0

    # Save initial condition
    writer.writerow([t, state[0], state[1], state[2]])
    saved_points += 1

    # Integration loop
    n_steps = int((t_end - t_start) / dt)
    logger.log(f"Starting integration: {n_steps} steps")

    while t < t_end:
        # RK4 step
        state = rk4_step(state, dt, sigma, rho, beta)
        t += dt
        step += 1

        # Save every N steps to keep file size manageable
        if step % save_every == 0:
            writer.writerow([t, state[0], state[1], state[2]])
            saved_points += 1

        # Progress logging
        if step % (n_steps // 10) == 0:
            progress = 100 * step / n_steps
            logger.log(f"Progress: {progress:.0f}% (t={t:.2f})")

logger.log(f"Simulation complete. Saved {saved_points} points to {csv_filename}")

# -----------------------------------------------------------------------------
# ANALYSIS: Read back and compute statistics
# -----------------------------------------------------------------------------

logger.log("Analyzing results...")

# Read trajectory from CSV
trajectory = {"t": [], "x": [], "y": [], "z": []}

with open(csv_filename, "r", newline="") as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        trajectory["t"].append(float(row["t"]))
        trajectory["x"].append(float(row["x"]))
        trajectory["y"].append(float(row["y"]))
        trajectory["z"].append(float(row["z"]))

# Compute statistics
def stats(values):
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean)**2 for v in values) / n
    return {
        "min": min(values),
        "max": max(values),
        "mean": mean,
        "std": variance ** 0.5
    }

x_stats = stats(trajectory["x"])
y_stats = stats(trajectory["y"])
z_stats = stats(trajectory["z"])

# Save analysis results
analysis = {
    "trajectory_file": csv_filename,
    "num_points": len(trajectory["t"]),
    "time_span": [trajectory["t"][0], trajectory["t"][-1]],
    "statistics": {
        "x": x_stats,
        "y": y_stats,
        "z": z_stats
    },
    "notes": "The Lorenz attractor has two 'wings' - the trajectory switches chaotically between them"
}

with open("analysis_results.json", "w") as f:
    json.dump(analysis, f, indent=2)

logger.log("Analysis saved to 'analysis_results.json'")

# Print summary
print("\n" + "=" * 60)
print("SIMULATION SUMMARY")
print("=" * 60)
print(f"Variable    Min         Max         Mean        Std")
print("-" * 60)
for var, stat in [("x", x_stats), ("y", y_stats), ("z", z_stats)]:
    print(f"{var:8} {stat['min']:11.4f} {stat['max']:11.4f} {stat['mean']:11.4f} {stat['std']:11.4f}")

logger.close()

# -----------------------------------------------------------------------------
# ERROR HANDLING EXAMPLE
# -----------------------------------------------------------------------------

print("\n" + "=" * 60)
print("ERROR HANDLING DEMO")
print("=" * 60)

def safe_read_config(filename):
    """Demonstrate proper error handling for file operations."""
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Config file '{filename}' not found")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{filename}': {e}")
        return None
    except PermissionError:
        print(f"Error: Permission denied reading '{filename}'")
        return None

# Test error handling
result = safe_read_config("nonexistent_file.json")
print(f"Result of reading missing file: {result}")

result = safe_read_config("lorenz_config.json")
print(f"Result of reading valid file: {type(result).__name__} with {len(result)} keys")

print("\nAll examples complete! Check the generated files:")
print("  - lorenz_config.json (configuration)")
print("  - lorenz_trajectory.csv (simulation data)")
print("  - simulation.log (execution log)")
print("  - analysis_results.json (statistics)")
