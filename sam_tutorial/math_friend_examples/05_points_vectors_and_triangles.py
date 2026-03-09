"""Basic Euclidean geometry with points, vectors, and triangles."""

import math


def dist(P, Q):
    return math.hypot(Q[0] - P[0], Q[1] - P[1])


def dot(u, v):
    return u[0] * v[0] + u[1] * v[1]


def sub(P, Q):
    # Vector from Q to P
    return (P[0] - Q[0], P[1] - Q[1])


def triangle_area(A, B, C):
    # 0.5 * |(B-A) x (C-A)| in 2D
    return abs((B[0] - A[0]) * (C[1] - A[1]) - (B[1] - A[1]) * (C[0] - A[0])) / 2


A = (0.0, 0.0)
B = (4.0, 0.0)
C = (1.0, 3.0)

AB = sub(B, A)
AC = sub(C, A)

print(f"A={A}, B={B}, C={C}")
print(f"|AB| = {dist(A, B):.4f}")
print(f"|AC| = {dist(A, C):.4f}")
print(f"AB · AC = {dot(AB, AC):.4f}")
print(f"Area(ABC) = {triangle_area(A, B, C):.4f}")
