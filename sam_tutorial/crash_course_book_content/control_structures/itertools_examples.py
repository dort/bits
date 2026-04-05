"""
itertools module examples for mathematicians

itertools provides memory-efficient iterators for:
- Combinatorics (permutations, combinations, products)
- Infinite sequences
- Grouping and filtering
"""

import itertools
from math import factorial

# =============================================================================
# COMBINATORICS
# =============================================================================

print("=" * 60)
print("COMBINATORICS")
print("=" * 60)

# --- Permutations ---
# All orderings of elements (n! for full permutations)
print("\n--- Permutations ---")
items = ['a', 'b', 'c']
perms = list(itertools.permutations(items))
print(f"P(3,3) = {len(perms)} permutations of {items}:")
for p in perms:
    print(f"  {p}")

# Partial permutations: P(n,r) = n! / (n-r)!
perms_2 = list(itertools.permutations(items, 2))
print(f"\nP(3,2) = {len(perms_2)} permutations of length 2:")
print(f"  {perms_2}")

# --- Combinations ---
# Subsets of size r: C(n,r) = n! / (r!(n-r)!)
print("\n--- Combinations (without replacement) ---")
items = [1, 2, 3, 4]
combs = list(itertools.combinations(items, 2))
print(f"C(4,2) = {len(combs)} combinations of {items} taken 2 at a time:")
for c in combs:
    print(f"  {c}")

# --- Combinations with replacement ---
# Like combinations, but elements can repeat
# Formula: C(n+r-1, r) = (n+r-1)! / (r!(n-1)!)
print("\n--- Combinations with replacement ---")
items = ['x', 'y']
combs_rep = list(itertools.combinations_with_replacement(items, 3))
print(f"Combinations of {items} with replacement, r=3:")
for c in combs_rep:
    print(f"  {c}")

# --- Cartesian Product ---
# |A × B| = |A| * |B|
print("\n--- Cartesian Product ---")
A = {1, 2}
B = {'a', 'b', 'c'}
product = list(itertools.product(A, B))
print(f"A = {A}, B = {B}")
print(f"|A × B| = {len(product)}")
for pair in product:
    print(f"  {pair}")

# Product with repeat: A^n (n-fold Cartesian product)
print("\nBinary strings of length 3 (as {0,1}^3):")
binary_3 = list(itertools.product([0, 1], repeat=3))
for b in binary_3:
    print(f"  {b}")


# =============================================================================
# INFINITE ITERATORS
# =============================================================================

print("\n" + "=" * 60)
print("INFINITE ITERATORS")
print("=" * 60)

# --- count: arithmetic sequence ---
# a_n = start + n*step
print("\n--- count(start, step) ---")
counter = itertools.count(start=0, step=2)
evens = [next(counter) for _ in range(10)]
print(f"First 10 even numbers: {evens}")

# --- cycle: periodic sequence ---
print("\n--- cycle(iterable) ---")
cycler = itertools.cycle(['A', 'B', 'C'])
period = [next(cycler) for _ in range(9)]
print(f"Cycling through ['A','B','C'] 3 times: {period}")

# --- repeat: constant sequence ---
print("\n--- repeat(value, times) ---")
zeros = list(itertools.repeat(0, 5))
print(f"5 zeros: {zeros}")

# Useful for map operations
squares = list(map(pow, range(10), itertools.repeat(2)))
print(f"Squares using repeat: {squares}")


# =============================================================================
# ACCUMULATION AND REDUCTION
# =============================================================================

print("\n" + "=" * 60)
print("ACCUMULATION")
print("=" * 60)

# --- accumulate: running totals / scans ---
# Like reduce, but yields intermediate values
print("\n--- accumulate ---")
import operator

nums = [1, 2, 3, 4, 5]
partial_sums = list(itertools.accumulate(nums))
print(f"Partial sums of {nums}: {partial_sums}")

partial_products = list(itertools.accumulate(nums, operator.mul))
print(f"Partial products: {partial_products}")

# Running maximum
data = [3, 1, 4, 1, 5, 9, 2, 6]
running_max = list(itertools.accumulate(data, max))
print(f"Running max of {data}: {running_max}")


# =============================================================================
# FILTERING AND SELECTING
# =============================================================================

print("\n" + "=" * 60)
print("FILTERING AND SELECTING")
print("=" * 60)

# --- takewhile / dropwhile ---
print("\n--- takewhile / dropwhile ---")
nums = [2, 4, 6, 7, 8, 10, 12]
print(f"nums = {nums}")

taken = list(itertools.takewhile(lambda x: x % 2 == 0, nums))
print(f"takewhile(even): {taken}")  # stops at first odd

dropped = list(itertools.dropwhile(lambda x: x % 2 == 0, nums))
print(f"dropwhile(even): {dropped}")  # starts at first odd

# --- filterfalse: complement of filter ---
print("\n--- filterfalse ---")
nums = range(10)
odds = list(itertools.filterfalse(lambda x: x % 2 == 0, nums))
print(f"filterfalse(even) on 0-9: {odds}")

# --- compress: selection by boolean mask ---
print("\n--- compress ---")
data = ['a', 'b', 'c', 'd', 'e']
mask = [1, 0, 1, 0, 1]
selected = list(itertools.compress(data, mask))
print(f"compress({data}, {mask}): {selected}")

# --- islice: lazy slicing ---
print("\n--- islice ---")
fib = itertools.accumulate(
    itertools.repeat(1),
    lambda a, _: a + (fib_prev := getattr(fib, 'prev', 1)) or setattr(fib, 'prev', a) or fib_prev
)
# Simpler Fibonacci demo:
def fibonacci():
    a, b = 0, 1
    while True:
        yield a
        a, b = b, a + b

first_10_fib = list(itertools.islice(fibonacci(), 10))
print(f"First 10 Fibonacci: {first_10_fib}")


# =============================================================================
# GROUPING AND CHAINING
# =============================================================================

print("\n" + "=" * 60)
print("GROUPING AND CHAINING")
print("=" * 60)

# --- groupby: group consecutive elements ---
# NOTE: data must be sorted by key first!
print("\n--- groupby ---")
data = [('Alice', 'Math'), ('Bob', 'Math'), ('Carol', 'Physics'),
        ('Dave', 'Physics'), ('Eve', 'Math')]
sorted_data = sorted(data, key=lambda x: x[1])  # sort by department

print("Students grouped by department:")
for dept, students in itertools.groupby(sorted_data, key=lambda x: x[1]):
    names = [s[0] for s in students]
    print(f"  {dept}: {names}")

# --- chain: concatenate iterables ---
print("\n--- chain ---")
list1 = [1, 2, 3]
list2 = [4, 5, 6]
list3 = [7, 8, 9]
chained = list(itertools.chain(list1, list2, list3))
print(f"chain({list1}, {list2}, {list3}): {chained}")

# chain.from_iterable: flatten one level
nested = [[1, 2], [3, 4], [5, 6]]
flattened = list(itertools.chain.from_iterable(nested))
print(f"chain.from_iterable({nested}): {flattened}")

# --- zip_longest: zip with padding ---
print("\n--- zip_longest ---")
short = [1, 2]
long = ['a', 'b', 'c', 'd']
zipped = list(itertools.zip_longest(short, long, fillvalue='?'))
print(f"zip_longest({short}, {long}, fillvalue='?'): {zipped}")


# =============================================================================
# MATHEMATICAL APPLICATIONS
# =============================================================================

print("\n" + "=" * 60)
print("MATHEMATICAL APPLICATIONS")
print("=" * 60)

# --- Power set ---
print("\n--- Power set (all subsets) ---")
def powerset(iterable):
    """P(S) = union of C(S,r) for r in 0..n"""
    s = list(iterable)
    return itertools.chain.from_iterable(
        itertools.combinations(s, r) for r in range(len(s) + 1)
    )

S = {1, 2, 3}
ps = list(powerset(S))
print(f"Power set of {S}:")
print(f"  |P(S)| = 2^{len(S)} = {len(ps)}")
for subset in ps:
    print(f"  {set(subset)}")

# --- Partitions / Stirling-like patterns ---
print("\n--- All ways to partition indices into pairs ---")
def pairings(items):
    """Generate all perfect matchings (for even-length lists)"""
    if len(items) < 2:
        yield []
        return
    first = items[0]
    for i, second in enumerate(items[1:], 1):
        pair = (first, second)
        rest = items[1:i] + items[i+1:]
        for pairings_rest in pairings(rest):
            yield [pair] + pairings_rest

items = ['a', 'b', 'c', 'd']
print(f"Perfect matchings of {items}:")
for p in pairings(items):
    print(f"  {p}")

# --- Generate prime numbers (Sieve with itertools) ---
print("\n--- Prime sieve using itertools ---")
def primes():
    """Infinite prime generator using itertools"""
    yield 2
    composites = {}
    for n in itertools.count(3, 2):  # odd numbers starting at 3
        if n not in composites:
            yield n
            composites[n * n] = [n]  # mark n^2 as composite
        else:
            for p in composites[n]:
                composites.setdefault(n + 2*p, []).append(p)
            del composites[n]

first_20_primes = list(itertools.islice(primes(), 20))
print(f"First 20 primes: {first_20_primes}")

# --- Dot product ---
print("\n--- Dot product ---")
def dot_product(v1, v2):
    return sum(itertools.starmap(operator.mul, zip(v1, v2)))

a = [1, 2, 3]
b = [4, 5, 6]
print(f"a = {a}, b = {b}")
print(f"a · b = {dot_product(a, b)}")

# --- Polynomial evaluation (Horner's method) ---
print("\n--- Polynomial evaluation ---")
def horner(coeffs, x):
    """Evaluate polynomial with coefficients [a_n, a_{n-1}, ..., a_1, a_0] at x"""
    return list(itertools.accumulate(coeffs, lambda acc, c: acc * x + c))[-1]

# p(x) = 2x^3 + 3x^2 - x + 5 = [2, 3, -1, 5]
coeffs = [2, 3, -1, 5]
x = 2
print(f"p(x) = 2x³ + 3x² - x + 5")
print(f"p({x}) = {horner(coeffs, x)}")  # 2(8) + 3(4) - 2 + 5 = 16 + 12 - 2 + 5 = 31


print("\n" + "=" * 60)
print("END OF EXAMPLES")
print("=" * 60)
