import json
import re

from tokenizer import ConfigurationError, compile_spec
from tokenizer.config import (canonical_json_bytes, compile_flags, fingerprint,
                              load_json, loads_json)
from tests.support import HERE, TempCase


class ConfigurationTests(TempCase):
    def test_shared_loader_does_not_impose_a_lexical_schema(self):
        raw = {"version": 1, "start": "expr", "productions": []}
        self.assertEqual(loads_json(json.dumps(raw)), raw)
        path = self.directory / "grammar.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        self.assertEqual(load_json(path), raw)

    def test_duplicate_keys_and_constants_keep_source_context(self):
        cases = ['{"x":1,"x":2}', '{"x":[{"y":1,"y":2}]}',
                 '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}']
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ConfigurationError) as caught:
                loads_json(text, source="grammar.json")
            self.assertEqual(caught.exception.source, "grammar.json")
        with self.assertRaises(ConfigurationError) as caught:
            loads_json('{\n "x": }', source="broken.json")
        self.assertEqual((caught.exception.source, caught.exception.line), ("broken.json", 2))
        self.assertIsNotNone(caught.exception.offset)

    def test_configuration_file_errors_are_named(self):
        missing = self.directory / "missing.json"
        invalid = self.directory / "invalid.json"
        invalid.write_bytes(b'\xff')
        for path in [missing, invalid]:
            with self.subTest(path=path), self.assertRaises(ConfigurationError) as caught:
                load_json(path)
            self.assertEqual(caught.exception.source, str(path))

    def test_canonical_bytes_preserve_array_order_and_exact_text(self):
        value = {"z": [2, 1], "a": "λ\n"}
        self.assertEqual(canonical_json_bytes(value), b'{"a":"\\u03bb\\n","z":[2,1]}')
        self.assertEqual(fingerprint(value), fingerprint(dict(reversed(list(value.items())))))
        self.assertNotEqual(fingerprint(value), fingerprint({"z": [1, 2], "a": "λ\n"}))
        for value in [{"x": float("nan")}, {"x": float("inf")}, {"x": object()}]:
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                canonical_json_bytes(value)

    def test_existing_fingerprint_recipe_is_unchanged(self):
        raw = load_json(HERE / "specs/expression_demo.json")
        expected = "abcfb5fed40800240f2db2a33558d2a4e0c7010c6b165172b8554beda8ddcbc3"
        self.assertEqual(fingerprint(raw), expected)
        self.assertEqual(compile_spec(raw).fingerprint, expected)

    def test_flags_are_shared_and_checked(self):
        self.assertEqual(compile_flags(["ASCII", "IGNORECASE"]), re.ASCII | re.IGNORECASE)
        self.assertEqual(compile_flags([]), re.NOFLAG)
        for value in ["ASCII", None, ["ASCII", "ASCII"], ["LOCALE"], [True], [[]]]:
            with self.subTest(value=value), self.assertRaises(ConfigurationError) as caught:
                compile_flags(value)
            self.assertEqual(caught.exception.field, "flags")
