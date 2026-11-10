"""Shared helpers for running the MM2 Earley engines under real MORK.

A test builds one input file from fixture pieces plus a generated round
table, runs ``mork run INPUT DUMP --aux-path ENGINE``, and reads the dumped
space back as parsed facts. Results come from the dump file only; stdout is
never treated as a fact stream.
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
FIXTURES = HERE / "fixtures"
OUTPUT = PROJECT / "output"

# Repository-local import setup, in this one place: grammarc lives in this
# project and imports the sibling lexer's tokenizer package.
for path in (PROJECT, PROJECT.parent / "lexer"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from grammarc.serialize import round_table_facts  # noqa: E402

RECOGNITION = PROJECT / "earley.mm2"
FOREST = PROJECT / "earley_forest.mm2"
MORK = Path(os.environ.get("MORK", "/home/ni/repos/m/MORK/target/release/mork"))


def fixture(name):
    return (FIXTURES / name).read_text()


_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^()\s]+')


def parse_facts(text):
    """Parse a dump or fixture into nested tuples; atoms stay strings.

    Each fact is one parenthesized expression; the dump writes one per line,
    but the parser only relies on balanced parentheses. Lines whose first
    nonblank character is ';' are comments (fixtures carry them, dumps do
    not) and are skipped.
    """
    text = "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith(";"))
    facts = []
    stack = []
    for match in _TOKEN.finditer(text):
        token = match.group()
        if token == "(":
            stack.append([])
        elif token == ")":
            if not stack:
                raise ValueError(f"unbalanced ')' at offset {match.start()}")
            done = tuple(stack.pop())
            if stack:
                stack[-1].append(done)
            else:
                facts.append(done)
        else:
            if not stack:
                raise ValueError(f"atom {token!r} outside a fact at offset {match.start()}")
            stack[-1].append(token)
    if stack:
        raise ValueError("unbalanced '(' at end of dump")
    return facts


def render(expr):
    if isinstance(expr, tuple):
        return "(" + " ".join(render(piece) for piece in expr) + ")"
    return expr


def run_engine(engine, pieces, rounds, *, steps=None, timeout=120):
    """Run one engine over the concatenated fixture pieces and parse the dump."""
    OUTPUT.mkdir(exist_ok=True)
    source = "".join(piece if piece.endswith("\n") else piece + "\n" for piece in pieces)
    source += round_table_facts(rounds)
    with tempfile.TemporaryDirectory(dir=OUTPUT) as directory:
        input_path = Path(directory) / "input.mm2"
        dump_path = Path(directory) / "dump.mm2"
        input_path.write_text(source)
        command = [str(MORK), "run", str(input_path), str(dump_path),
                   "--aux-path", str(engine)]
        if steps is not None:
            command += ["--steps", str(steps)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(f"mork failed ({result.returncode}): {result.stderr}")
        return parse_facts(dump_path.read_text())


def select(facts, head, *prefix):
    """Facts whose first atom is `head` and whose next atoms match `prefix`."""
    return {fact for fact in facts
            if fact and fact[0] == head and fact[1:1 + len(prefix)] == prefix}


def projection(facts, namespace, stream, grammar, heads):
    """The canonical semantic projection for one (namespace, stream, grammar)."""
    chosen = set()
    for head in heads:
        for fact in select(facts, head, namespace, stream, grammar):
            chosen.add(render(fact))
    return frozenset(chosen)


class EngineCase(unittest.TestCase):
    """Base class: every run must reach the budget marker to count."""

    RECOGNITION_HEADS = ("item", "accepted")
    FOREST_HEADS = ("item", "accepted", "node", "part")

    def run_complete(self, engine, pieces, rounds, **kwargs):
        facts = run_engine(engine, pieces, rounds, **kwargs)
        self.assertIn(("swept", f"b{rounds:03d}"), facts,
                      "the scheduled sweeps did not all run")
        return facts

    def converged(self, engine, pieces, rounds, keys, heads):
        """Run at `rounds` and 2x`rounds`; require equal projections per key.

        Equality after additional complete sweeps is the closure evidence this
        monotonic engine admits; the first run's facts are returned.
        """
        first = self.run_complete(engine, pieces, rounds)
        second = self.run_complete(engine, pieces, 2 * rounds)
        for key in keys:
            self.assertEqual(projection(first, *key, heads),
                             projection(second, *key, heads),
                             f"projection for {key} not stable at {rounds} rounds")
        return first
