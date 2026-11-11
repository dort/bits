import json
import unittest
from unittest.mock import patch

from tokenizer import ConfigurationError
from tokenizer.split_spec import compile_split_spec, loads_split_spec


class SplitSpecTests(unittest.TestCase):
    def setUp(self):
        self.raw = {"version": 1, "separator": {"literal": "\n"}, "max_unit_chars": 64}

    def regex(self, pattern, width=64, **options):
        return compile_split_spec(dict(self.raw, separator={
            "pattern": pattern, "max_length": width, **options}))

    def test_defaults_and_fingerprint(self):
        compiled = compile_split_spec(self.raw)
        self.assertEqual((compiled.mode, compiled.retain, compiled.empty_units),
                         ("separator", "end", "keep"))
        self.assertEqual(compiled.fingerprint,
                         loads_split_spec(json.dumps(self.raw, indent=2)).fingerprint)
        self.raw["separator"]["literal"] = ";"
        self.assertEqual(compiled.literal, "\n")
        self.assertNotEqual(compiled.fingerprint, compile_split_spec(self.raw).fingerprint)

    def test_strict_schema_and_types(self):
        changes = [
            {"version": True}, {"version": 1.0}, {"version": 2},
            {"max_unit_chars": True}, {"max_unit_chars": 0}, {"max_unit_chars": -1},
            {"max_unit_chars": "64"}, {"unknown": 1}, {"preamble": "unit"},
            {"retain": "discard"}, {"retain": []}, {"empty_units": "ignore"},
            {"boundary": {"literal": "!"}}, {"separator": []},
            {"separator": {}}, {"separator": {"literal": ""}},
            {"separator": {"literal": "x", "flags": []}},
            {"separator": {"literal": "x", "max_length": 1}},
            {"separator": {"literal": "x", "pattern": "x"}},
            {"separator": {"pattern": "x"}},
            {"separator": {"pattern": "x", "max_length": True}},
            {"separator": {"pattern": "x", "max_length": 65537}},
            {"separator": {"literal": "x" * 65537}},
        ]
        for change in changes:
            with self.subTest(change=repr(change)[:120]), self.assertRaises(ConfigurationError):
                compile_split_spec(dict(self.raw, **change))
        for raw in [[], {}, {"version": 1, "max_unit_chars": 1},
                    {"version": 1, "boundary": {"literal": "!"}, "max_unit_chars": 10,
                     "retain": "end"}]:
            with self.subTest(raw=raw), self.assertRaises(ConfigurationError):
                compile_split_spec(raw)

    def test_json_errors_and_source_context(self):
        for text in ['{"version":1,"version":1}',
                     '{"separator":{"literal":"x","literal":"y"}}',
                     '{"version":NaN}']:
            with self.assertRaises(ConfigurationError) as caught:
                loads_split_spec(text, source="split.json")
            self.assertEqual(caught.exception.source, "split.json")

    def test_finite_regex_subset(self):
        for pattern, width in [(r"^UNIT [0-9]{4}: ", 11),
                               (r"(?i:ab|c){1,3}?", 6), (r"[^;]{1,2};", 3),
                               (r"\s?\w\d", 3), (r"(?:x{0,2})?y", 3),
                               (r"a|ab", 2), (r"(?m)^x", 1), (r"^a|^b", 1), (r".{1,2}", 2)]:
            with self.subTest(pattern=pattern):
                compiled = self.regex(pattern, width)
                self.assertEqual(compiled.width, width)
        # A loose declaration is safe; use the computed bound for buffering.
        self.assertEqual(self.regex("x", 64).width, 1)

    def test_context_dependent_unbounded_and_unknown_operations_rejected(self):
        for pattern in [r"a(?=b{10})", r"(?<=x)a", r"(a)\1", r"(a)?(?(1)b|c)",
                        r"a+", r"a*", r"a{1,}", r"(?:a|)", r"a?", r"(?:)",
                        r"a$", r"a\Z", r"a\z", r"\Aa", r"\ba", r"a\B", r"x^y",
                        r"^a|b^c", r"(?m:^a)", r"(?>a)", r"a{1,2}+", r"a{0,100}",
                        r"a{65537}", r"(?:a{256}){256}", r"("]:
            with self.subTest(pattern=pattern), self.assertRaises(ConfigurationError):
                self.regex(pattern)
        with self.assertRaises(ConfigurationError):
            self.regex("abc", 2)
        # Fail closed on a parser opcode introduced by an unqualified runtime.
        with patch("tokenizer.split_regex._parser.parse", return_value=[(object(), None)]):
            with self.assertRaises(ConfigurationError):
                self.regex("x")

    def test_flags_and_pattern_errors_are_named(self):
        for flags in ["MULTILINE", ["LOCALE"], ["MULTILINE", "MULTILINE"], [False]]:
            with self.assertRaises(ConfigurationError):
                self.regex("x", flags=flags)
        with self.assertRaises(ConfigurationError) as caught:
            self.regex("(")
        self.assertEqual(caught.exception.field, "pattern")
        self.assertEqual(caught.exception.pattern_offset, 0)
