import copy
import json
import re
import unittest

from tokenizer import ConfigurationError, compile_spec, load_spec, loads_spec
from tests.support import HERE, PLAN


class SpecificationTests(unittest.TestCase):
    def setUp(self):
        self.raw = {"version": 1, "rules": [{"name": "word", "pattern": "[a-z]+", "kind": "WORD"}]}

    def test_exact_version_type(self):
        for spelling in ["true", "false", "1.0", "1e0", '"1"', "null", "2"]:
            with self.subTest(spelling=spelling), self.assertRaises(ConfigurationError) as caught:
                loads_spec(json.dumps(self.raw).replace('"version": 1', f'"version": {spelling}'))
            self.assertEqual(caught.exception.field, "version")
        self.assertEqual(compile_spec(self.raw).kinds, ("WORD",))

    def test_duplicate_json_keys_at_every_depth(self):
        for source in [
            '{"version":1,"version":1,"rules":[]}',
            '{"version":1,"rules":[{"name":"x","name":"y","literal":"x","kind":"X"}]}',
        ]:
            with self.subTest(source=source), self.assertRaisesRegex(ConfigurationError, "duplicate JSON key"):
                loads_spec(source)

    def test_non_json_constants_and_bad_json(self):
        for value in ["NaN", "Infinity", "-Infinity"]:
            with self.subTest(value=value), self.assertRaisesRegex(ConfigurationError, "non-JSON"):
                loads_spec('{"version":' + value + ',"rules":[]}')
        with self.assertRaises(ConfigurationError) as caught:
            loads_spec('{\n"version": }', source="rules.json")
        self.assertEqual((caught.exception.source, caught.exception.line), ("rules.json", 2))

    def test_rule_validation(self):
        bad_rules = [
            {}, [], {"name": "bad name", "literal": "x", "kind": "X"},
            {"name": "x", "literal": "x", "pattern": "x", "kind": "X"},
            {"name": "x", "literal": "x", "kind": "X", "skip": True},
            {"name": "x", "literal": "x", "skip": 1},
            {"name": "x", "literal": "x", "skip": False},
            {"name": "x", "literal": "", "kind": "X"},
            {"name": "x", "pattern": "", "kind": "X"},
            {"name": "x", "literal": 3, "kind": "X"},
            {"name": "x", "literal": "x", "kind": "lower"},
            {"name": "x", "literal": "x", "kind": "X", "flags": []},
            {"name": "x", "pattern": "x", "kind": "X", "flags": "ASCII"},
            {"name": "x", "pattern": "x", "kind": "X", "flags": ["LOCALE"]},
            {"name": "x", "pattern": "x", "kind": "X", "flags": ["ASCII", "ASCII"]},
            {"name": "x", "pattern": "x", "kind": "X", "flags": [1]},
            {"name": "x", "literal": "x", "kind": "X", "extra": True},
        ]
        for rule in bad_rules:
            with self.subTest(rule=rule), self.assertRaises(ConfigurationError):
                compile_spec({"version": 1, "rules": [rule]})
        for raw in [[], {}, {"version": 1, "rules": []}, {"version": 1, "rules": {}, "extra": 1}]:
            with self.subTest(raw=raw), self.assertRaises(ConfigurationError):
                compile_spec(raw)

    def test_duplicate_names_but_repeated_kinds_allowed(self):
        self.raw["rules"].append({"name": "another", "literal": "!", "kind": "WORD"})
        self.assertEqual(compile_spec(self.raw).kinds, ("WORD",))
        self.raw["rules"][1]["name"] = "word"
        with self.assertRaisesRegex(ConfigurationError, "duplicate rule name"):
            compile_spec(self.raw)

    def test_invalid_pattern_diagnostic(self):
        self.raw["rules"][0]["pattern"] = "("
        with self.assertRaises(ConfigurationError) as caught:
            compile_spec(self.raw)
        self.assertEqual((caught.exception.rule, caught.exception.pattern_offset), ("word", 0))

    def test_empty_patterns_in_314(self):
        for pattern in ["a*", r"\B", r"\z", "(?:)"]:
            self.raw["rules"][0]["pattern"] = pattern
            with self.subTest(pattern=pattern), self.assertRaisesRegex(ConfigurationError, "empty input"):
                compile_spec(self.raw)

    def test_fingerprint_and_compiled_spec_are_stable(self):
        initial = compile_spec(self.raw)
        self.assertEqual(initial.fingerprint, loads_spec(json.dumps(self.raw, indent=4)).fingerprint)
        self.assertEqual(initial.fingerprint, compile_spec(dict(reversed(list(self.raw.items())))).fingerprint)
        self.raw["rules"][0]["kind"] = "CHANGED"
        self.assertEqual(initial.kinds, ("WORD",))
        self.assertNotEqual(initial.fingerprint, compile_spec(self.raw).fingerprint)
        self.raw["rules"].append({"name": "a", "literal": "a", "kind": "A"})
        reversed_rules = copy.deepcopy(self.raw)
        reversed_rules["rules"].reverse()
        self.assertNotEqual(compile_spec(self.raw).fingerprint, compile_spec(reversed_rules).fingerprint)

    def test_plan_fixture_is_synchronized(self):
        text = PLAN.read_text()
        documented = json.loads(re.search(r'```json\n(.*?)\n```', text, re.S).group(1))
        self.assertEqual(documented, json.loads((HERE / "specs/expression_demo.json").read_text()))
        compiled = load_spec(HERE / "specs/expression_demo.json")
        digest = compiled.fingerprint
        self.assertIn(f'(lex-spec demo s0 sha256 h{digest[:32]} h{digest[32:]})', text)
