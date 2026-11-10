from pathlib import Path
import tempfile
import unittest

from tokenizer import SourcePiece, compile_spec, source_records


HERE = Path(__file__).resolve().parents[1]
PLAN = HERE.parent / "detailed_plan_python_tokenization.md"
MORK = HERE.parents[3] / "MORK/target/release/mork"


def spec(*rules):
    return compile_spec({"version": 1, "rules": list(rules)})


def chars_spec():
    return spec({"name": "char", "pattern": ".", "flags": ["DOTALL"], "kind": "CHAR"})


def envelope(text, compiled, *, namespace="demo", stream_id="s0", **options):
    return source_records([SourcePiece(text, stream_id=stream_id)], compiled,
                          namespace=namespace, source_id=stream_id, identity_policy="caller",
                          max_units=1, **options)


class TempCase(unittest.TestCase):
    def setUp(self):
        root = HERE / "output/test-tmp"
        root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
