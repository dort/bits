import json
import os
import subprocess
import sys

from tokenizer import BundleReader
from tests.support import HERE, TempCase


class SplitParserTests(TempCase):
    def test_source_to_both_parser_engines(self):
        parsing = HERE.parent
        environment = dict(os.environ, PYTHONPATH=os.pathsep.join((str(HERE), str(parsing / "earley"))))
        bundle = self.directory / "bundle"
        tokenized = subprocess.run([
            sys.executable, "-m", "tokenizer", "--spec", str(HERE / "specs/expression_demo.json"),
            "--split-spec", str(HERE / "specs/split_lines.json"), "--input", "-",
            "--namespace", "demo", "--stream-id", "expressions", "--output-dir", str(bundle)],
            input=b'x + 12\nx +\n\n3\n', cwd=parsing, env=environment, capture_output=True, timeout=15)
        self.assertEqual(tokenized.returncode, 0, tokenized.stderr)
        self.assertEqual(BundleReader(bundle).end.unit_count, 4)
        results = []
        for engine in ("recognition", "forest"):
            output = self.directory / engine
            command = [sys.executable, "-m", "grammarc", "parse", "--grammar",
                       str(parsing / "earley/tests/fixtures/grammar_expr_demo.json"),
                       "--grammar-id", "gexp", "--tokens", str(bundle), "--engine", engine,
                       "--output-dir", str(output)]
            if engine == "forest":
                command += ["--max-trees", "10", "--max-depth", "32"]
            completed = subprocess.run(command, cwd=parsing, env=environment, capture_output=True, timeout=30)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            with (output / "results.jsonl").open() as source:
                rows = [json.loads(line) for line in source]
            self.assertEqual([row["stream_id"] for row in rows], [f"expressions_u{i}" for i in range(4)])
            self.assertEqual([row["recognition"] for row in rows], ["accepted", "rejected", "rejected", "accepted"])
            self.assertTrue(all(row["closure_complete"] for row in rows))
            self.assertTrue(all(row["reason"] is None for row in rows))
            results.append([(row["recognition"], row["item_count"]) for row in rows])
            if engine == "forest":
                self.assertTrue(all(row["forest_complete"] and row["enumeration_complete"] for row in rows))
                self.assertEqual([len(row["trees"]) for row in rows], [1, 0, 0, 1])
                with (output / "forests.jsonl").open() as source:
                    graphs = [json.loads(line) for line in source]
                self.assertEqual([row["stream_id"] for row in graphs], [row["stream_id"] for row in rows])
                self.assertTrue(all(row["graph_complete"] for row in graphs))
        self.assertEqual(*results)
