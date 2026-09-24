#!/usr/bin/env python3
"""Semantic tests against independent finite Datalog closure, using real MORK."""

from pathlib import Path
import random
import tempfile
import unittest

from run import HERE, items, parse, run_file, sexpr, validate


def linked(values):
    result = "nil"
    for value in reversed(list(values)):
        result = ("cons", value, result)
    return result


def var(name):
    return ("v", name)


def const(value):
    return ("c", value)


def atom(pred, *terms):
    return ("atom", pred, linked(terms))


def fact(pred, *values):
    return ("fact", pred, linked(values))


def rule(name, head, *body):
    return ("rule", name, head, linked(body))


def match(terms, values, env):
    """Ordinary Python unification, independent of the MM2 work queue."""
    env = dict(env)
    for (tag, name), value in zip(terms, values):
        if tag == "c":
            if name != value:
                return None
        elif name in env:
            if env[name] != value:
                return None
        else:
            env[name] = value
    return env


def oracle(program):
    declarations = validate(program)
    relations = {pred: set() for pred in declarations}
    rules = [expr for expr in program if expr[0] == "rule"]
    for expr in program:
        if expr[0] == "fact":
            relations[expr[1]].add(tuple(items(expr[2])))
    while True:
        added = False
        for _, _, head, body in rules:
            environments = [{}]
            for _, pred, args in items(body):
                environments = [extended for env in environments for values in relations[pred]
                                if (extended := match(items(args), values, env)) is not None]
            for env in environments:
                values = tuple(name if tag == "c" else env[name] for tag, name in items(head[2]))
                if values not in relations[head[1]]:
                    relations[head[1]].add(values)
                    added = True
        if not added:
            break
    answers = set()
    for expr in program:
        if expr[0] == "query":
            _, name, (_, pred, args) = expr
            for values in relations[pred]:
                if match(items(args), values, {}) is not None:
                    answers.add(("result", name, ("atom", pred, linked(values))))
    closure = {("closure", pred, linked(values)) for pred, tuples in relations.items()
               if declarations[pred] == "idb" for values in tuples}
    return answers, closure


X, Y, Z = var("x"), var("y"), var("z")


def paths(edges, queries, left_recursive=False):
    recursive_body = (atom("path", X, Z), atom("edge", Z, Y)) if left_recursive else (
        atom("edge", X, Z), atom("path", Z, Y))
    return [("edb", "edge"), ("idb", "path"),
            rule("base", atom("path", X, Y), atom("edge", X, Y)),
            rule("recur", atom("path", X, Y), *recursive_body),
            *[fact("edge", *edge) for edge in edges],
            *[("query", name, atom("path", *args)) for name, args in queries]]


class MagicSetsTests(unittest.TestCase):
    def run_program(self, program, engine):
        with tempfile.TemporaryDirectory(prefix="mm2-magic-test-") as directory:
            path = Path(directory) / "input.mm2"
            path.write_text("\n".join(map(sexpr, program)) + "\n")
            space, _ = run_file(path, engine)
        # A nonempty residual queue would mean the apparent answers are partial.
        self.assertFalse(any(isinstance(expr, tuple) and expr and expr[0] == "next" for expr in space))
        return set(space)

    def compare(self, program):
        answers, closure = oracle(program)
        magic = self.run_program(program, "magic")
        plain = self.run_program(program, "plain")
        for space in (magic, plain):
            self.assertEqual({expr for expr in space if expr[0] == "result"}, answers)
        self.assertEqual({expr for expr in plain if expr[0] == "closure"}, closure)
        return magic, plain

    def test_examples_and_pruning(self):
        for name in ("example.mm2", "example_joins.mm2"):
            with self.subTest(example=name):
                program = parse((HERE / name).read_text())
                magic, plain = self.compare(program)
                self.assertTrue(any(expr[0] == "result" for expr in magic))
                derived = {expr for expr in magic if expr[0] == "derived"}
                closure = {expr for expr in plain if expr[0] == "closure"}
                self.assertLess(len(derived), len(closure))
                irrelevant = {"u", "v", "w"} if name == "example.mm2" else {"denver", "miami", "bob"}
                self.assertFalse(any(irrelevant.intersection(items(expr[3])) for expr in derived))
                for expr in magic:
                    if expr[0] == "generated" and expr[1][0] == "modified":
                        self.assertEqual(items(expr[3])[0][1][0], "magic")
        magic, _ = self.compare(parse((HERE / "example.mm2").read_text()))
        self.assertEqual({items(expr[2][2])[-1] for expr in magic if expr[0] == "result"}, {"b", "c", "d"})

    def test_all_binding_patterns(self):
        edges = [("a", "b"), ("b", "c"), ("c", "b"), ("a", "b"), ("u", "v")]
        queries = [("bf", (const("a"), Y)), ("fb", (X, const("c"))),
                   ("bb", (const("a"), const("c"))), ("ff", (X, Y))]
        for name, args in queries:
            with self.subTest(mask=name):
                magic, _ = self.compare(paths(edges, [(name, args)]))
                self.assertIn(("magic", "path", linked(name),
                               linked(term[1] for term in args if term[0] == "c")), magic)

    def test_multiple_queries_repeated_variables_and_empty_answers(self):
        self.compare(paths([("a", "b"), ("b", "a"), ("c", "c"), ("u", "v")], [
            ("same", (X, X)), ("from-a", (const("a"), Y)),
            ("absent", (const("missing"), Y)), ("false", (const("u"), const("a"))),
            ("true", (const("a"), const("a")))]))

    def test_left_and_nonlinear_recursion(self):
        edges = [("a", "b"), ("b", "c"), ("c", "a"), ("u", "v")]
        self.compare(paths(edges, [("left", (const("a"), Y))], left_recursive=True))
        program = paths(edges, [("nonlinear", (const("a"), Y))])
        program[3] = rule("recur", atom("path", X, Y), atom("path", X, Z), atom("path", Z, Y))
        self.compare(program)

    def test_mutual_recursion_and_missing_base(self):
        program = [("edb", "seed"), ("idb", "p"), ("idb", "q"), ("idb", "empty"),
                   fact("seed", "a"), fact("seed", "unrelated"),
                   rule("seed", atom("p", X), atom("seed", X)),
                   rule("p-to-q", atom("q", X), atom("p", X)),
                   rule("q-to-p", atom("p", X), atom("q", X)),
                   rule("unfounded", atom("empty", X), atom("empty", X)),
                   ("query", "q", atom("q", const("a"))),
                   ("query", "empty", atom("empty", const("a")))]
        self.compare(program)

    def test_ternary_atoms_long_bodies_and_constants(self):
        program = [("edb", "triple"), ("edb", "flag"), ("idb", "middle"), ("idb", "out"),
                   fact("triple", "a", "b", "b"), fact("triple", "a", "b", "c"),
                   fact("triple", "b", "c", "c"), fact("triple", "u", "v", "v"),
                   fact("flag", "c"),
                   rule("middle", atom("middle", X, Y), atom("triple", X, Y, Y)),
                   rule("out", atom("out", const("ok"), X, Z),
                        atom("middle", X, Y), atom("middle", Y, Z), atom("flag", Z)),
                   ("query", "ok", atom("out", const("ok"), const("a"), Z)),
                   ("query", "wrong-head", atom("out", const("wrong"), const("a"), Z)),
                   ("query", "edb", atom("triple", const("a"), Y, Y))]
        magic, _ = self.compare(program)
        self.assertIn(("result", "ok", atom("out", "ok", "a", "c")), magic)

    def test_empty_bodies_nullary_and_empty_database(self):
        self.compare([("edb", "enabled"), ("idb", "yes"), ("idb", "p"),
                      fact("enabled"), rule("yes", atom("yes"), atom("enabled")),
                      rule("constant", atom("p", const("nil"))),
                      ("query", "yes", atom("yes")), ("query", "p", atom("p", X))])
        self.compare(paths([], [("none", (const("a"), Y))]))
        self.compare([("edb", "edge"), ("idb", "empty"),
                      ("query", "edb-empty", atom("edge", X, Y)),
                      ("query", "idb-empty", atom("empty", X))])
        self.compare(paths([("a", "b")], []))

    def test_seeded_random_graphs(self):
        rng = random.Random(731)
        for index in range(4):
            edges = [(x, y) for x in "abcd" for y in "abcd" if rng.random() < 0.22]
            with self.subTest(graph=index):
                self.compare(paths(edges, [("from-a", (const("a"), Y)),
                                           ("to-d", (X, const("d")))]))

    def test_input_rejections(self):
        invalid = [
            "(edb p) (idb p)",
            "(edb p) (fact p nil) (query q (atom p (cons (v x) nil)))",
            "(idb p) (rule r (atom p (cons (v x) nil)) nil)",
            "(query q (atom missing nil))",
            "(edb p) (fact p (cons $x nil))",
            "(idb p) (query q (atom p nil)) (query q (atom p nil))",
            "(idb p) (rule r (atom p nil) nil) (rule r (atom p nil) nil)",
            "(idb p) (rule r (atom p nil) (cons (not (atom p nil)) nil))",
            "(idb p) (query q (atom p (cons (c (function a)) nil)))",
            "(edb p) (rule r (atom p nil) nil)",
            "(exec 0 (,) (, bad))",
            "(edb p) (fact p (cons a wrong-tail))",
            "(edb p) (fact p (cons \"quoted\" nil))",
        ]
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate(parse(source))


if __name__ == "__main__":
    unittest.main(verbosity=2)
