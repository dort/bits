"""Area and orientation of polygons using the shoelace formula."""


def signed_area(poly):
    # poly = [(x0,y0), (x1,y1), ..., (xn-1, yn-1)]
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - y1 * x2
    return 0.5 * s


def orientation(poly):
    a = signed_area(poly)
    if a > 0:
        return "counterclockwise"
    if a < 0:
        return "clockwise"
    return "degenerate"


pentagon = [(0, 0), (3, 0), (4, 2), (2, 4), (0, 2)]

A_signed = signed_area(pentagon)
A = abs(A_signed)

print("Polygon vertices:")
print(pentagon)
print(f"Signed area: {A_signed:.4f}")
print(f"Area: {A:.4f}")
print(f"Orientation: {orientation(pentagon)}")
