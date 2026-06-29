#!/usr/bin/env python3
"""Visualize Lorenz attractor trajectory from CSV data."""

import csv
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

def load_trajectory(filename):
    """Load trajectory data from CSV file."""
    t, x, y, z = [], [], [], []
    with open(filename, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            t.append(float(row['t']))
            x.append(float(row['x']))
            y.append(float(row['y']))
            z.append(float(row['z']))
    return t, x, y, z

def main():
    # Load data
    t, x, y, z = load_trajectory('lorenz_trajectory.csv')

    # Create figure with two subplots
    fig = plt.figure(figsize=(14, 6))

    # 3D trajectory plot
    ax1 = fig.add_subplot(121, projection='3d')
    ax1.plot(x, y, z, lw=0.5, color='blue')
    ax1.set_xlabel('X')
    ax1.set_ylabel('Y')
    ax1.set_zlabel('Z')
    ax1.set_title('Lorenz Attractor - 3D Trajectory')

    # Time series plot
    ax2 = fig.add_subplot(122)
    ax2.plot(t, x, label='x(t)', alpha=0.8)
    ax2.plot(t, y, label='y(t)', alpha=0.8)
    ax2.plot(t, z, label='z(t)', alpha=0.8)
    ax2.set_xlabel('Time')
    ax2.set_ylabel('Value')
    ax2.set_title('Lorenz System - Time Series')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('lorenz_visualization.png', dpi=150)
    plt.show()

if __name__ == '__main__':
    main()
