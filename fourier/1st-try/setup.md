# Labeling System — Setup

Working notes for a labeling system over two sets. This document accumulates
requirements as they are provided; open questions are tracked at the bottom.

## Problem statement

We have two sets:

- **Set A** with cardinality **m**
- **Set B** with cardinality **n**
- Constraint: **m < n** always.

We assign integer **labels in the range `0 .. m+n-1`** across the elements of
both sets (m + n elements total, m + n labels total).

The labeling is a **bijection**: each of the m+n labels is used exactly once
across the two sets combined — no repeats between or within sets.

## Deliverable

A Python file that:

1. Implements **3 labeling strategies** (to be specified).
2. Given specific `(m, n)` values, generates the concrete labeling each
   strategy produces.
3. Covers **all possible `(m, n)` pairs** with `m < n`, up to a configurable
   maximum — the maximum is a **parameter in the Python file**.

## Requirements gathered so far

| Item | Value |
|---|---|
| Number of sets | 2 (cardinalities m and n) |
| Constraint | m < n |
| Minimum m | 2 |
| Label domain | integers 0 to m+n-1, bijection (no repeats) |
| Strategy count | 3 (1 defined, 2 pending) |
| Enumeration | all (m, n) pairs up to a maximum |
| Maximum | bounds m+n; parameter in the Python file; hard bound 1,000,000 — initial runs use 100 |
| Output format | plain text: the set of labels for the m-set and the set of labels for the n-set |

## Labeling strategies

Context: the goal is optimal strategies under constraints not yet shared.
Random labelings are excluded as unlikely to be optimal.

### 1. `interval`

- m-set gets labels `0 .. m-1`
- n-set gets labels `m .. m+n-1`

Each set's labels form one contiguous interval.

### 2. `balanced`

An alternating scheme; named "balanced" because plain alternation behaves
differently depending on whether m divides n evenly, and this formulation
spreads the m-set's labels evenly regardless.

- m-set gets labels `floor(k*(m+n)/m)` for integer `k = 0 .. m-1`
- n-set gets all remaining labels in `0 .. m+n-1`

The m labels are spaced as evenly as possible across the full range
`0 .. m+n-1` (consecutive labels differ by floor or ceil of (m+n)/m).

### 3. `parity tail`

Also inspired by alternating strategies, like `balanced`, but with a constant
stride instead of an evenly-spread one.

- m-set gets labels `k * floor((m+n)/m)` for integer `k = 0 .. m-1`
- n-set gets all remaining labels in `0 .. m+n-1`

The m-set's labels form an arithmetic progression with constant step
`floor((m+n)/m)`, so the alternation pattern is exactly periodic at the start
of the range; the labels left over accumulate as a contiguous tail at the end
of the range, which goes to the n-set. (Largest m-set label is
`(m-1)*floor((m+n)/m) <= m+n-1`, so the labeling stays in range and is a
valid bijection.)

## Implementation

`labeling.py` implements the three strategies and, when run, prints the
labeling of every valid (m, n) pair for all three strategies. `MAXIMUM`
(currently 100) is the parameter bounding m+n; `HARD_BOUND` enforces the
1,000,000 limit. A sample full run is saved in `labelings.txt`.

## Open questions (pending further instructions)

- Definitions of strategies 2 and 3.
- Context: directory is named `fourier/` — relationship to Fourier analysis,
  if any, not yet stated.
