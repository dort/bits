"""Tests for the grammar specification compiler and its serialization.

Schema tests run without MORK; the final test compiles the worked-example
grammar JSON, serializes it, and recognizes the real lexer's "x + 12" bundle
with the generated facts under the actual binary.
"""

import copy
import json
import unittest

from tests.support import (EngineCase, FIXTURES, RECOGNITION, fixture,
                           parse_facts, select)
from grammarc import (compile_grammar, demand_fact, grammar_facts,
                      load_grammar, round_table_facts)
from grammarc.serialize import MAX_ROUNDS
from tokenizer.model import ConfigurationError

PINNED_DIGEST = ("8711aca694c020c03214bd2105a00212"
                 "1864f95c644556d81121422f9281851d")


def demo_grammar():
    return json.loads((FIXTURES / "grammar_expr_demo.json").read_text())


class SpecTests(unittest.TestCase):
    def test_worked_example_compiles_with_the_pinned_fingerprint(self):
        grammar = load_grammar(FIXTURES / "grammar_expr_demo.json")
        self.assertEqual(grammar.fingerprint, PINNED_DIGEST)
        self.assertEqual(grammar.start, "expr")
        self.assertEqual([p.name for p in grammar.productions],
                         ["sum", "lift", "num", "ref"])
        self.assertEqual(grammar.productions[0].rhs,
                         (("nt", "expr"), ("t", "PLUS"), ("nt", "term")))
        self.assertEqual(grammar.nonterminals, ("expr", "term"))
        self.assertEqual(grammar.terminals, ("IDENT", "INT", "PLUS"))
        self.assertEqual(grammar.max_rhs_length, 3)

    def test_rejected_specifications(self):
        good = demo_grammar()
        cases = {}

        def case(label, mutate):
            raw = copy.deepcopy(good)
            mutate(raw)
            cases[label] = raw

        case("version string", lambda raw: raw.update(version="1"))
        case("version float", lambda raw: raw.update(version=1.0))
        case("version boolean", lambda raw: raw.update(version=True))
        case("version two", lambda raw: raw.update(version=2))
        case("unknown root field", lambda raw: raw.update(extra=1))
        case("missing start", lambda raw: raw.pop("start"))
        case("empty productions", lambda raw: raw.update(productions=[]))
        case("productions not array", lambda raw: raw.update(productions={}))
        case("unknown production field",
             lambda raw: raw["productions"][0].update(extra=1))
        case("duplicate production name",
             lambda raw: raw["productions"][1].update(name="sum"))
        case("uppercase production name",
             lambda raw: raw["productions"][0].update(name="Sum"))
        case("uppercase nonterminal",
             lambda raw: raw["productions"][0].update(lhs="Expr"))
        case("overlong name",
             lambda raw: raw["productions"][0].update(name="a" * 33))
        case("epsilon production",
             lambda raw: raw["productions"][0].update(rhs=[]))
        case("rhs element with both fields",
             lambda raw: raw["productions"][0]["rhs"].__setitem__(
                 0, {"nt": "expr", "t": "PLUS"}))
        case("rhs element with neither field",
             lambda raw: raw["productions"][0]["rhs"].__setitem__(0, {}))
        case("rhs element unknown tag",
             lambda raw: raw["productions"][0]["rhs"].__setitem__(
                 0, {"sym": "expr"}))
        case("lowercase terminal",
             lambda raw: raw["productions"][2]["rhs"].__setitem__(
                 0, {"t": "int"}))
        case("uppercase value under nt",
             lambda raw: raw["productions"][1]["rhs"].__setitem__(
                 0, {"nt": "TERM"}))
        case("undefined nonterminal",
             lambda raw: raw["productions"][1]["rhs"].__setitem__(
                 0, {"nt": "ghost"}))
        case("undefined start", lambda raw: raw.update(start="ghost"))
        for label, raw in cases.items():
            with self.subTest(case=label), self.assertRaises(ConfigurationError):
                compile_grammar(raw)
        with self.assertRaises(ConfigurationError):
            compile_grammar(["not", "an", "object"])

    def test_errors_carry_production_and_field_context(self):
        raw = demo_grammar()
        raw["productions"][2]["rhs"] = []
        with self.assertRaises(ConfigurationError) as caught:
            compile_grammar(raw)
        self.assertEqual(caught.exception.rule, "num")
        self.assertEqual(caught.exception.field, "rhs")
        self.assertIn("num", str(caught.exception))

    def test_duplicate_json_keys_are_rejected_at_load(self):
        duplicated = (FIXTURES / "grammar_expr_demo.json").read_text().replace(
            '"start": "expr",', '"start": "expr", "start": "term",', 1)
        path = FIXTURES.parent.parent / "output"
        path.mkdir(exist_ok=True)
        target = path / "duplicate_keys.json"
        target.write_text(duplicated)
        with self.assertRaises(ConfigurationError) as caught:
            load_grammar(target)
        self.assertEqual(caught.exception.field, "start")
        self.assertEqual(caught.exception.source, str(target))

    def test_terminal_catalog_check_names_the_missing_kinds(self):
        grammar = compile_grammar(demo_grammar())
        grammar.check_terminals(["IDENT", "INT", "PLUS", "EQ", "ASSIGN"])
        with self.assertRaises(ConfigurationError) as caught:
            grammar.check_terminals(["IDENT", "INT"])
        self.assertIn("PLUS", str(caught.exception))
        self.assertNotIn("INT,", str(caught.exception))


class SerializationTests(unittest.TestCase):
    def test_generated_facts_match_the_hand_written_fixture(self):
        grammar = compile_grammar(demo_grammar())
        generated = set(parse_facts("".join(grammar_facts(grammar, "gexp"))))
        expected = set(parse_facts(fixture("grammar_expr_demo.mm2")))
        self.assertEqual(generated, expected | {("grm-grammar", "gexp", "1")})

    def test_identifier_and_round_table_validation(self):
        grammar = compile_grammar(demo_grammar())
        for bad in ("", "0abc", "has-dash", "x" * 33, None):
            with self.subTest(grammar_id=bad), self.assertRaises(ConfigurationError):
                list(grammar_facts(grammar, bad))
        with self.assertRaises(ConfigurationError):
            demand_fact("demo", "s0", "0bad")
        self.assertEqual(demand_fact("demo", "s0", "gexp"), "(parse demo s0 gexp)\n")
        for bad in (0, MAX_ROUNDS + 1, True, "8"):
            with self.subTest(rounds=bad), self.assertRaises(ValueError):
                round_table_facts(bad)
        table = round_table_facts(2)
        self.assertEqual(table, "(nextround r001 r002)\n(nextround r002 r003)\n"
                                "(budget b002)\n")


class CompiledRecognitionTests(EngineCase):
    def test_compiled_grammar_recognizes_the_real_lexer_bundle(self):
        grammar = load_grammar(FIXTURES / "grammar_expr_demo.json")
        grammar.check_terminals(["ASSIGN", "EQ", "IDENT", "INT", "PLUS"])
        pieces = ["".join(grammar_facts(grammar, "gexp")),
                  fixture("tokens_x_plus_12.mm2"),
                  demand_fact("demo", "s0", "gexp")]
        key = ("demo", "s0", "gexp")
        facts = self.converged(RECOGNITION, pieces, 16, [key],
                               self.RECOGNITION_HEADS)
        self.assertEqual(select(facts, "accepted"),
                         {("accepted", "demo", "s0", "gexp")})
        self.assertEqual(len(select(facts, "item", *key)), 13)
        self.assertIn(("grm-spec", "gexp", "sha256",
                       "h" + PINNED_DIGEST[:32], "h" + PINNED_DIGEST[32:]),
                      facts)
