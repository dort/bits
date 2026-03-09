"""Simple matrix operations using plain Python lists."""

A = [
    [1, 2],
    [3, 4],
]

B = [
    [5, 6],
    [7, 8],
]


def mat_add(X, Y):
    rows = len(X)
    cols = len(X[0])
    return [[X[i][j] + Y[i][j] for j in range(cols)] for i in range(rows)]


def mat_mul(X, Y):
    rows = len(X)
    cols = len(Y[0])
    inner = len(Y)
    out = [[0 for _ in range(cols)] for _ in range(rows)]

    for i in range(rows):
        for j in range(cols):
            out[i][j] = sum(X[i][k] * Y[k][j] for k in range(inner))
    return out


print("A + B =")
print(mat_add(A, B))

print("\nA * B =")
print(mat_mul(A, B))
