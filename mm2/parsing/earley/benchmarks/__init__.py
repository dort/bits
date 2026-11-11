"""Reproducible parser scale measurements over synthetic version-2 bundles.

`cases` defines the grammars, lazy unit-text generators, and the deterministic
case registry; `parser` is the runnable harness (`python -m benchmarks.parser`
from `earley/` with the sibling `lexer/` on `PYTHONPATH`). Results stream to
the ignored `output/` directory; the compact reproducible report lives in
`benchmarks/REPORT.md`.
"""
