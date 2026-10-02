#!/usr/bin/env python3
"""Fibonacci answers, query restriction, and numeric boundaries on real MORK."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from fib import HERE, run_fibonacci
from run import items, run_file


def fibonacci(index):
    current, following = 0, 1
    for _ in range(index):
        current, following = following, current + following
    return current


def records(space, tag):
    return {expr for expr in space if isinstance(expr, tuple) and expr and expr[0] == tag}


class FibonacciTests(unittest.TestCase):
    def test_values_and_i64_boundary(self):
        indices = [0, 1, 2, 3, 10, 20, 50, 92]
        space, _ = run_fibonacci(indices)
        answers = {int(items(expr[2][2])[0]): int(items(expr[2][2])[1])
                   for expr in records(space, "result")}
        self.assertEqual(answers, {index: fibonacci(index) for index in indices})
        self.assertEqual(answers[92], 7540113804746346429)
        self.assertFalse(records(space, "next") | records(space, "delta") | records(space, "exec"))

    def test_magic_restriction_and_shared_subproblems(self):
        space, _ = run_fibonacci([10, 5, 10])
        self.assertEqual(len(records(space, "result")), 2)
        demands = records(space, "magic")
        derived = records(space, "derived")
        self.assertEqual(len(demands), 11)
        self.assertEqual(len(derived), 11)
        self.assertEqual({int(items(expr[3])[0]) for expr in demands}, set(range(11)))
        self.assertEqual({tuple(map(int, items(expr[3]))) for expr in derived},
                         {(index, fibonacci(index)) for index in range(11)})
        # Arithmetic in the body prefix must also appear in generated demand
        # rules, so predecessor calls are guarded and receive computed indices.
        demand_rules = [expr for expr in records(space, "generated") if expr[1][0] == "demand"]
        self.assertEqual(len(demand_rules), 2)
        for expr in demand_rules:
            body = items(expr[3])
            self.assertEqual(body[0][1][0], "magic")
            self.assertTrue(any(literal[:2] == ("builtin", "sub_i64") for literal in body))

    def test_only_requested_base_cases(self):
        for index in (0, 1):
            with self.subTest(index=index):
                space, _ = run_fibonacci([index])
                self.assertEqual({tuple(items(expr[3])) for expr in records(space, "derived")},
                                 {(str(index), str(index))})
                self.assertEqual({tuple(items(expr[3])) for expr in records(space, "magic")},
                                 {(str(index),)})

    def test_no_queries_no_computation(self):
        space, _ = run_fibonacci([])
        self.assertFalse(records(space, "result") | records(space, "magic") | records(space, "derived"))

    def test_full_closure_agrees(self):
        # The same finite source program is evaluated without the transformation.
        with tempfile.TemporaryDirectory(prefix="mm2-fib-plain-") as directory:
            path = Path(directory) / "input.mm2"
            path.write_text((HERE / "fib.mm2").read_text() + "\n" + (HERE / "example.mm2").read_text())
            plain, _ = run_file(path, engine="plain")
        magic, _ = run_fibonacci([10, 20])
        self.assertEqual(records(plain, "result"), records(magic, "result"))
        closure = {tuple(map(int, items(expr[2]))) for expr in records(plain, "closure")}
        self.assertEqual(closure, {(index, fibonacci(index)) for index in range(93)})
        self.assertEqual(len(records(magic, "derived")), 21)

    def test_invalid_indices_rejected(self):
        for index in (-1, 93, 1000, 1.5, "10"):
            with self.subTest(index=index), self.assertRaises(ValueError):
                run_fibonacci([index])
        for value in ("-1", "93", "2.5"):
            completed = subprocess.run([str(HERE / "run.sh"), value], text=True, capture_output=True, timeout=5)
            self.assertNotEqual(completed.returncode, 0)
            self.assertNotIn("(result ", completed.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
