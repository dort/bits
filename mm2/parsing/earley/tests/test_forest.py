"""Tests for production-aware forest traversal and bounded enumeration.

The forests come from real forest-engine dumps over the engine fixtures; the
grammars are compiled from JSON mirrors of those fixtures so `Forest` sees
exactly what the production pipeline will hand it.
"""

import json

from tests.support import EngineCase, FOREST, fixture
from grammarc import Forest, Runner, compile_grammar, load_grammar
from tests.support import FIXTURES, PROJECT
from tests.test_runner import build_bundle, RunnerCase


def grammar_of(start, *productions):
    return compile_grammar({"version": 1, "start": start, "productions": list(productions)})


def production(name, lhs, *rhs):
    return {"name": name, "lhs": lhs,
            "rhs": [{"nt": symbol} if symbol.islower() else {"t": symbol}
                    for symbol in rhs]}


def labels(tree):
    """A tree as nested (production, children) labels, spans dropped."""
    if "t" in tree:
        return tree["t"]
    return (tree["production"], tuple(labels(child) for child in tree["children"]))


class ForestCase(EngineCase):
    def forest(self, grammar, grammar_id, grammar_fixture, tokens_fixture,
               namespace, stream, rounds=16):
        pieces = [fixture(grammar_fixture), fixture(tokens_fixture),
                  f"(parse {namespace} {stream} {grammar_id})"]
        key = (namespace, stream, grammar_id)
        facts = self.converged(FOREST, pieces, rounds, [key], self.FOREST_HEADS)
        return Forest(grammar, facts, *key)


class TraversalTests(ForestCase):
    def test_expression_demo_has_exactly_its_one_tree(self):
        grammar = load_grammar(FIXTURES / "grammar_expr_demo.json")
        forest = self.forest(grammar, "gexp", "grammar_expr_demo.mm2",
                             "tokens_x_plus_12.mm2", "demo", "s0")
        trees, complete = forest.enumerate(10, 10)
        self.assertTrue(complete)
        self.assertEqual([labels(tree) for tree in trees],
                         [("sum", (("lift", (("ref", ("IDENT",)),)), "PLUS",
                                   ("num", ("INT",))))])

    def test_remy_expression_yields_the_precedence_oracle(self):
        grammar = grammar_of(
            "expr",
            production("sum", "expr", "expr", "PLUS", "term"),
            production("lift", "expr", "term"),
            production("mul", "term", "term", "STAR", "atom"),
            production("lifa", "term", "atom"),
            production("int", "atom", "INT"))
        forest = self.forest(grammar, "gpre", "grammar_precedence.mm2",
                             "tokens_remy_expression.mm2", "remy", "e0", rounds=32)
        trees, complete = forest.enumerate(10, 20)
        self.assertTrue(complete)
        integer = ("lifa", (("int", ("INT",)),))
        product = ("mul", (integer, "STAR", ("int", ("INT",))))
        # (+ (+ 4 (* 57 6)) 7)
        oracle = ("sum", (("sum", (("lift", (integer,)), "PLUS", product)),
                          "PLUS", integer))
        self.assertEqual([labels(tree) for tree in trees], [oracle])

    def test_concatenation_has_exactly_two_trees(self):
        grammar = grammar_of("expr",
                             production("cat", "expr", "expr", "expr"),
                             production("int", "expr", "INT"))
        forest = self.forest(grammar, "gcat", "grammar_concat.mm2",
                             "tokens_ints.mm2", "ints", "n3")
        trees, complete = forest.enumerate(10, 10)
        self.assertTrue(complete)
        leaf = ("int", ("INT",))
        self.assertEqual({labels(tree) for tree in trees},
                         {("cat", (("cat", (leaf, leaf)), leaf)),
                          ("cat", (leaf, ("cat", (leaf, leaf))))})
        self.assertEqual(len(trees), 2)

    def test_sibling_productions_enumerate_two_and_four_distinct_trees(self):
        siblings = grammar_of("sss",
                              production("root", "sss", "atom"),
                              production("aone", "atom", "INT"),
                              production("atwo", "atom", "INT"))
        forest = self.forest(siblings, "gsib", "grammar_alternatives.mm2",
                             "tokens_ints.mm2", "ints", "n1")
        trees, complete = forest.enumerate(10, 10)
        self.assertTrue(complete)
        rendered = {labels(tree) for tree in trees}
        self.assertEqual(len(trees), 2, "duplicate emissions mean the symbol "
                                        "node was expanded instead of the "
                                        "committed child production")
        self.assertEqual(rendered, {("root", (("aone", ("INT",)),)),
                                    ("root", (("atwo", ("INT",)),))})
        pair = grammar_of("ppp",
                          production("pair", "ppp", "atom", "atom"),
                          production("pone", "atom", "INT"),
                          production("ptwo", "atom", "INT"))
        forest = self.forest(pair, "gpar", "grammar_alternatives.mm2",
                             "tokens_ints.mm2", "ints", "n2")
        trees, complete = forest.enumerate(10, 10)
        self.assertTrue(complete)
        self.assertEqual(len(trees), 4)
        self.assertEqual(len({json.dumps(tree, sort_keys=True) for tree in trees}), 4)

    def test_merged_start_root_keeps_both_accepting_alternatives(self):
        grammar = grammar_of("tts",
                             production("frst", "tts", "INT"),
                             production("scnd", "tts", "INT"))
        forest = self.forest(grammar, "gsta", "grammar_alternatives.mm2",
                             "tokens_ints.mm2", "ints", "n1")
        self.assertEqual(forest.roots, [("tts", "0", "1")])
        trees, complete = forest.enumerate(10, 10)
        self.assertTrue(complete)
        self.assertEqual({labels(tree) for tree in trees},
                         {("frst", ("INT",)), ("scnd", ("INT",))})

    def test_unit_cycles_truncate_explicitly(self):
        direct = grammar_of("expr",
                            production("loop", "expr", "expr"),
                            production("inte", "expr", "INT"))
        forest = self.forest(direct, "gcyd", "grammar_cycles.mm2",
                             "tokens_ints.mm2", "ints", "n1")
        trees, complete = forest.enumerate(100, 5)
        self.assertFalse(complete, "a unit cycle has unboundedly many trees")
        rendered = {labels(tree) for tree in trees}
        self.assertIn(("inte", ("INT",)), rendered)
        self.assertIn(("loop", (("inte", ("INT",)),)), rendered)
        self.assertEqual(len(rendered), len(trees))
        indirect = grammar_of("aaa",
                              production("fwd", "aaa", "bbb"),
                              production("base", "aaa", "INT"),
                              production("bwd", "bbb", "aaa"))
        forest = self.forest(indirect, "gcyi", "grammar_cycles.mm2",
                             "tokens_ints.mm2", "ints", "n1")
        trees, complete = forest.enumerate(100, 6)
        self.assertFalse(complete)
        self.assertIn(("fwd", (("bwd", (("base", ("INT",)),)),)),
                      {labels(tree) for tree in trees})

    def test_count_limit_reports_partial_enumeration(self):
        grammar = grammar_of("expr",
                             production("cat", "expr", "expr", "expr"),
                             production("int", "expr", "INT"))
        forest = self.forest(grammar, "gcat", "grammar_concat.mm2",
                             "tokens_ints.mm2", "ints", "n8", rounds=32)
        trees, complete = forest.enumerate(3, 50)
        self.assertEqual(len(trees), 3)
        self.assertFalse(complete)

    def test_graph_json_round_trip_preserves_every_alternative(self):
        grammar = grammar_of("sss",
                             production("root", "sss", "atom"),
                             production("aone", "atom", "INT"),
                             production("atwo", "atom", "INT"))
        forest = self.forest(grammar, "gsib", "grammar_alternatives.mm2",
                             "tokens_ints.mm2", "ints", "n1")
        graph = json.loads(json.dumps(forest.graph()))
        self.assertEqual(graph, forest.graph())
        root_alternatives = [part for part in graph["parts"] if part[0] == "root"]
        self.assertEqual(root_alternatives,
                         [["root", 1, 0, 0, 1, ["nt", "atom", "aone"]],
                          ["root", 1, 0, 0, 1, ["nt", "atom", "atwo"]]])


class RunnerEnumerationTests(RunnerCase):
    def test_runner_enumerates_when_requested(self):
        runner = Runner(self.gexp, "gexp", engine="forest", max_trees=10, max_depth=20)
        results = list(runner.run_bundle(self.mixed))
        accepted = results[0]
        self.assertEqual(accepted.recognition, "accepted")
        self.assertTrue(accepted.enumeration_complete)
        self.assertEqual(len(accepted.trees), 1)
        self.assertEqual(accepted.trees[0]["production"], "sum")
        rejected = results[2]
        self.assertTrue(rejected.enumeration_complete)
        self.assertEqual(rejected.trees, ())

    def test_enumeration_requires_the_forest_engine(self):
        from tokenizer.model import ConfigurationError
        with self.assertRaises(ConfigurationError):
            Runner(self.gexp, "gexp", max_trees=10, max_depth=20)
        with self.assertRaises(ConfigurationError):
            Runner(self.gexp, "gexp", engine="forest", max_trees=10)
