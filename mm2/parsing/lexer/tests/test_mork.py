import os
import subprocess

from tokenizer import decode_lexeme, iter_mm2, load_spec, tokenize
from tests.support import HERE, MORK, TempCase, spec


class MorkTests(TempCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = os.environ.get("MORK", str(MORK))
        if not os.path.isfile(cls.binary) or not os.access(cls.binary, os.X_OK):
            raise RuntimeError(f"MORK integration blocked: executable unavailable: {cls.binary}; set MORK")

    def load(self, programs):
        source = self.directory / "tokens.mm2"
        destination = self.directory / "space.mm2"
        source.write_text("".join(programs), encoding="ascii")
        result = subprocess.run([self.binary, "run", str(source), str(destination),
                                 "--aux-path", str(HERE / "tests/fixtures/consume_tokens.mm2")],
                                cwd=HERE, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return {line.strip() for line in destination.read_text().splitlines() if line.strip()}

    def test_expression_adjacency_catalog_and_fingerprint(self):
        records = tokenize("x + 12", load_spec(HERE / "specs/expression_demo.json"),
                           namespace="demo", stream_id="s0")
        program = list(iter_mm2(records))
        loaded = self.load(program)
        expected = {line.strip() for line in program} | {
            "(adjacent demo s0 0 IDENT 1 PLUS)", "(adjacent demo s0 1 PLUS 2 INT)",
            "(completed demo s0 3 6)", "(catalogued demo s0 0 IDENT)",
            "(catalogued demo s0 1 PLUS)", "(catalogued demo s0 2 INT)",
        }
        self.assertEqual(loaded, expected)

    def test_long_and_structural_values_survive_exactly(self):
        values = ["a" * 70 + "-TAIL-ONE-", "a" * 70 + "-TAIL-TWO-",
                  '$(exec 0 (,) (, BAD))\n;comment\x00"\\λ😀',
                  "x" * 23 + "😀", "same", "same"]
        compiled = spec({"name": "all", "pattern": ".+", "flags": ["DOTALL"], "kind": "TEXT"})
        program = []
        for index, value in enumerate(values):
            program.extend(iter_mm2(tokenize(value, compiled, namespace="demo", stream_id=f"s{index}")))
        loaded = self.load(program)
        self.assertEqual({line for line in loaded if line.startswith("(lex-")},
                         {line.strip() for line in program})
        self.assertFalse(any("BAD" in line for line in loaded))
        for index, value in enumerate(values):
            prefix = f"lex-value-part demo s{index} 0 "
            parts = []
            for line in loaded:
                fields = line.strip("()").split()
                if line[1:].startswith(prefix):
                    parts.append((int(fields[4]), fields[5]))
            size_line = next(line for line in loaded if line.startswith(f"(lex-value-size demo s{index} 0 "))
            fields = size_line.strip("()").split()
            self.assertEqual(decode_lexeme(parts, byte_count=int(fields[4]), chunk_count=int(fields[5])), value)

    def test_repeated_tokens_and_empty_streams(self):
        compiled = spec({"name": "x", "literal": "x", "kind": "X"},
                        {"name": "space", "literal": " ", "skip": True})
        program = []
        for stream_id, value in [("repeated", "xxx"), ("empty", ""), ("skipped", "   ")]:
            program.extend(iter_mm2(tokenize(value, compiled, namespace="demo", stream_id=stream_id)))
        loaded = self.load(program)
        self.assertIn("(adjacent demo repeated 0 X 1 X)", loaded)
        self.assertIn("(adjacent demo repeated 1 X 2 X)", loaded)
        self.assertIn("(completed demo empty 0 0)", loaded)
        self.assertIn("(completed demo skipped 0 3)", loaded)
        self.assertIn("(lex-kind demo empty X)", loaded)
        self.assertEqual(sum(line.startswith("(lex-token demo repeated ") for line in loaded), 3)
