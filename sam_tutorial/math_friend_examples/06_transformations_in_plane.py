"""Isometries in the plane: translation, rotation, and reflection."""

import math


def translate(P, v):
    return (P[0] + v[0], P[1] + v[1])


def rotate(P, theta):
    c = math.cos(theta)
    s = math.sin(theta)
    return (c * P[0] - s * P[1], s * P[0] + c * P[1])


def reflect_x_axis(P):
    return (P[0], -P[1])


def fmt(P):
    return f"({P[0]:.3f}, {P[1]:.3f})"


triangle = [(1.0, 1.0), (3.0, 1.0), (2.0, 3.0)]

print("Original triangle vertices:")
for P in triangle:
    print(fmt(P))

translated = [translate(P, (2.0, -1.0)) for P in triangle]
rotated = [rotate(P, math.pi / 2) for P in triangle]  # 90 degrees
reflected = [reflect_x_axis(P) for P in triangle]

print("\nTranslated by (2, -1):")
for P in translated:
    print(fmt(P))

print("\nRotated by pi/2 around origin:")
for P in rotated:
    print(fmt(P))

print("\nReflected across x-axis:")
for P in reflected:
    print(fmt(P))
