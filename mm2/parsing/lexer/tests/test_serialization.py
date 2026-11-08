from dataclasses import replace
import json
import random
import re
import subprocess
import sys
from unittest.mock import patch

from tokenizer import (LexicalError, OutputError, Token, decode_lexeme,
                       encode_lexeme, iter_jsonl, iter_mm2, load_spec, tokenize, write_bundle)
from tokenizer.serialize import checked_atom
from tests.support import HERE, PLAN, TempCase, chars_spec, spec


class SerializationTests(TempCase):
    def records(self, text="x + 12"):
        return list(tokenize(text, load_spec(HERE / "specs/expression_demo.json"),
                             namespace="demo", stream_id="s0"))

    def test_exact_plan_example(self):
        expected = re.findall(r'```scheme\n(.*?)\n```', PLAN.read_text(), re.S)[-1]
        self.assertEqual("".join(iter_mm2(self.records())), expected + "\n")

    def test_json_reconstructs_input_and_retains_metadata(self):
        text = "x + 12\r\n"
        result = [json.loads(line) for line in iter_jsonl(self.records(text))]
        self.assertEqual("".join(row["lexeme"] for row in result if "lexeme" in row), text)
        self.assertEqual(result[0]["unicode_version"], "16.0.0")
        self.assertTrue(result[0]["python_version"].startswith("3.14."))
        self.assertEqual(result[-1]["token_count"], 3)
        self.assertTrue(result[-1]["complete"])

    def test_chunk_boundaries_and_random_round_trips(self):
        rng = random.Random(312)
        values = ["", "x" * 23, "x" * 24, "x" * 25, "x" * 63, "x" * 10000,
                  "x" * 23 + "😀", "\x00$();\n\r\"\\é"]
        values += ["".join(rng.choice("ab\x00\r\nλ😀\u0301") for _ in range(rng.randrange(200)))
                   for _ in range(100)]
        for text in values:
            byte_count, pieces = encode_lexeme(text)
            pieces = list(pieces)
            for _, atom in pieces:
                self.assertLessEqual(len(atom), 49)
                checked_atom(atom)
            rng.shuffle(pieces)
            self.assertEqual(decode_lexeme(pieces, byte_count=byte_count, chunk_count=len(pieces)), text)

    def test_corrupt_chunks_fail(self):
        cases = [
            ([], 1, 1), ([(0, "h61"), (0, "h61")], 1, 1),
            ([(1, "h61")], 1, 1), ([(0, "h6")], 1, 1),
            ([(0, "hgg")], 1, 1), ([(0, "h6162")], 1, 1),
            ([(0, "hff")], 1, 1), ([(0, "h61")], 25, 2),
            ([], 0, 1), ([], True, 1),
        ]
        for parts, size, count in cases:
            with self.subTest(parts=parts, size=size, count=count), self.assertRaises(OutputError):
                decode_lexeme(parts, byte_count=size, chunk_count=count)

    def test_atom_check_is_active_under_optimization(self):
        self.assertEqual(checked_atom("a" * 63), "a" * 63)
        for atom in ["a" * 64, "$x", "(exec)", "x y", "é", "", True, -1]:
            with self.subTest(atom=atom), self.assertRaises(OutputError):
                checked_atom(atom)
        code = "from tokenizer.serialize import checked_atom; checked_atom('a' * 64)"
        result = subprocess.run([sys.executable, "-O", "-c", code], cwd=HERE,
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OutputError", result.stderr)

    def test_bad_record_streams_never_complete(self):
        original = self.records()
        token = next(record for record in original if isinstance(record, Token))
        cases = [original[:-1], [], original[1:], original + [original[-1]],
                 [original[0], replace(token, index=7), original[-1]],
                 [original[0], replace(token, kind="UNDECLARED"), original[-1]],
                 [original[0], replace(token, stream_id="another"), original[-1]],
                 original[:-1] + [replace(original[-1], token_count=99)]]
        for records in cases:
            with self.subTest(records=records):
                emitted = []
                with self.assertRaises(OutputError):
                    for line in iter_mm2(records):
                        emitted.append(line)
                self.assertFalse(any(line.startswith("(lex-end ") for line in emitted))

    def test_bundle_is_complete_and_refuses_existing_destinations(self):
        output = self.directory / "result"
        manifest = write_bundle(self.records(), output)
        self.assertEqual(manifest["token_count"], 3)
        self.assertEqual(set(path.name for path in output.iterdir()),
                         {"tokens.jsonl", "tokens.mm2", "manifest.json"})
        self.assertEqual(json.loads((output / "manifest.json").read_text()),
                         json.loads(json.dumps(manifest)))
        expected = (output / "tokens.mm2").read_bytes()
        with self.assertRaises(OutputError):
            write_bundle(self.records("a"), output)
        self.assertEqual((output / "tokens.mm2").read_bytes(), expected)
        empty = self.directory / "empty"
        empty.mkdir()
        with self.assertRaises(OutputError):
            write_bundle(self.records(), empty)
        dangling = self.directory / "dangling"
        dangling.symlink_to(self.directory / "absent")
        with self.assertRaises(OutputError):
            write_bundle(self.records(), dangling)
        self.assertTrue(dangling.is_symlink())

    def test_destination_created_during_processing_is_preserved(self):
        output = self.directory / "race"
        def stream():
            yield from self.records()
            output.mkdir()
        with self.assertRaises(OutputError):
            write_bundle(stream(), output)
        self.assertEqual(list(output.iterdir()), [])
        self.assertEqual(list(self.directory.iterdir()), [output])

    def test_failures_clean_staging_directory(self):
        output = self.directory / "failed"
        broken = tokenize("a@", spec({"name": "a", "literal": "a", "kind": "A"}),
                          namespace="demo", stream_id="s0")
        with self.assertRaises(LexicalError):
            write_bundle(broken, output)
        self.assertEqual(list(self.directory.iterdir()), [])
        with patch("tokenizer.serialize._publish_directory", side_effect=OSError("disk full")):
            with self.assertRaises(OutputError):
                write_bundle(self.records(), output)
        self.assertEqual(list(self.directory.iterdir()), [])
        def interrupted():
            yield self.records()[0]
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            write_bundle(interrupted(), output)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_payload_is_always_data(self):
        text = '$(exec 0 (,) (, BAD))\n;comment\x00"\\😀'
        result = list(tokenize(text, chars_spec(), namespace="n", stream_id="s"))
        output = "".join(iter_mm2(result))
        self.assertNotIn("BAD", output)
        self.assertNotIn("$", output)
        self.assertNotIn(";", output)
        self.assertTrue(output.isascii())
