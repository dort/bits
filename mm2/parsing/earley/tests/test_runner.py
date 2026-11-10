"""Tests for the per-unit MORK runner over real version-2 token bundles.

Each bundle is produced by the actual lexer pipeline (`source_records` +
`write_bundle`) with generated stream identities, then recognized through
`grammarc.Runner` and the `python -m grammarc parse` command against the real
binary.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tests.support import OUTPUT, PROJECT, FIXTURES
from grammarc import Runner, compile_grammar, load_grammar
from grammarc.__main__ import main
from tokenizer import SourcePiece, load_spec, source_records, write_bundle

LEXER_SPEC = PROJECT.parent / "lexer/specs/expression_demo.json"


def build_bundle(destination, texts):
    """One generated-identity bundle with one unit per text, no gaps."""
    pieces = [SourcePiece(text, following=texts[i + 1][0] if i + 1 < len(texts) else "")
              for i, text in enumerate(texts)]
    records = source_records(pieces, load_spec(LEXER_SPEC),
                             namespace="demo", source_id="src")
    write_bundle(records, destination)
    return destination


def chain_grammar(depth=31):
    productions = [{"name": f"c{i:02d}", "lhs": f"a{i:02d}",
                    "rhs": [{"nt": f"a{i + 1:02d}"}]} for i in range(depth - 1)]
    productions.append({"name": f"c{depth - 1:02d}", "lhs": f"a{depth - 1:02d}",
                        "rhs": [{"t": "INT"}]})
    return {"version": 1, "start": "a00", "productions": productions}


class RunnerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUTPUT.mkdir(exist_ok=True)
        cls._directory = tempfile.TemporaryDirectory(dir=OUTPUT)
        cls.addClassCleanup(cls._directory.cleanup)
        base = Path(cls._directory.name)
        cls.mixed = build_bundle(base / "mixed", ["x + 12", "1 + 2", "+"])
        cls.single = build_bundle(base / "single", ["1"])
        cls.gexp = load_grammar(FIXTURES / "grammar_expr_demo.json")


class RunnerTests(RunnerCase):
    def test_mixed_bundle_recognition_contract(self):
        results = list(Runner(self.gexp, "gexp").run_bundle(self.mixed))
        self.assertEqual([unit.recognition for unit in results],
                         ["accepted", "accepted", "rejected"])
        self.assertEqual([unit.stream_id for unit in results],
                         ["src_u0", "src_u1", "src_u2"])
        for unit in results:
            self.assertTrue(unit.closure_complete)
            self.assertIsNone(unit.forest_complete)
            self.assertIsNone(unit.reason)
            self.assertGreaterEqual(len(unit.budgets), 2)
            self.assertEqual(unit.node_count, 0)
        self.assertEqual(results[0].item_count, 13)

    def test_forest_engine_reports_forest_completion_and_facts(self):
        results = list(Runner(self.gexp, "gexp", engine="forest").run_bundle(self.mixed))
        self.assertEqual([unit.recognition for unit in results],
                         ["accepted", "accepted", "rejected"])
        for unit in results:
            self.assertTrue(unit.forest_complete)
            self.assertIsNone(unit.enumeration_complete)
        self.assertGreater(results[0].node_count, 0)
        self.assertGreater(results[0].part_count, 0)

    def test_unit_chain_exhaustion_is_incomplete_not_rejected(self):
        grammar = compile_grammar(chain_grammar())
        limited, = Runner(grammar, "gchn", max_sweeps=24).run_bundle(self.single)
        self.assertEqual(limited.recognition, "incomplete")
        self.assertFalse(limited.closure_complete)
        self.assertIn("max_sweeps", limited.reason)
        self.assertEqual(limited.budgets, (16,))
        complete, = Runner(grammar, "gchn").run_bundle(self.single)
        self.assertEqual(complete.recognition, "accepted")
        self.assertTrue(complete.closure_complete)
        self.assertEqual(complete.budgets, (16, 32, 64, 128))
        self.assertEqual(complete.item_count, 62)

    def test_unproductive_grammar_is_rejected_with_closure(self):
        grammar = compile_grammar({"version": 1, "start": "uuu", "productions": [
            {"name": "self", "lhs": "uuu", "rhs": [{"nt": "uuu"}]}]})
        unit, = Runner(grammar, "gbad").run_bundle(self.single)
        self.assertEqual(unit.recognition, "rejected")
        self.assertTrue(unit.closure_complete)

    def test_token_limit_is_reported_without_an_engine_run(self):
        results = list(Runner(self.gexp, "gexp", max_tokens=1).run_bundle(self.mixed))
        self.assertEqual([unit.recognition for unit in results],
                         ["incomplete", "incomplete", "rejected"])
        self.assertIn("max_tokens", results[0].reason)
        self.assertEqual(results[0].budgets, ())

    def test_exhausted_deadline_is_incomplete(self):
        unit, = Runner(self.gexp, "gexp", timeout_seconds=1e-9).run_bundle(self.single)
        self.assertEqual(unit.recognition, "incomplete")
        self.assertIn("wall-time", unit.reason)
        self.assertEqual(unit.budgets, ())


class CommandTests(RunnerCase):
    def run_command(self, *arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr)):
            status = main(["parse", *arguments])
        return status, stdout.getvalue(), stderr.getvalue()

    def parse_args(self, bundle, output, *extra):
        return ("--grammar", str(FIXTURES / "grammar_expr_demo.json"),
                "--grammar-id", "gexp", "--tokens", str(bundle),
                "--output-dir", str(output), *extra)

    def test_statuses_and_published_results(self):
        base = Path(self._directory.name)
        accepted_only = build_bundle(base / "accepted", ["x + 12", "1 + 2"])
        status, stdout, _ = self.run_command(*self.parse_args(accepted_only, base / "out0"))
        self.assertEqual(status, 0)
        self.assertIn("2 accepted, 0 rejected, 0 incomplete", stdout)
        rows = [json.loads(line)
                for line in (base / "out0/results.jsonl").read_text().splitlines()]
        self.assertEqual([row["recognition"] for row in rows], ["accepted", "accepted"])
        summary = json.loads((base / "out0/summary.json").read_text())
        self.assertEqual(summary["counts"], {"accepted": 2, "rejected": 0, "incomplete": 0})
        self.assertEqual(summary["units"], 2)
        self.assertEqual(len(summary["engine_sha256"]), 64)

        status, _, _ = self.run_command(*self.parse_args(self.mixed, base / "out1"))
        self.assertEqual(status, 1)

        grammar_path = base / "chain.json"
        grammar_path.write_text(json.dumps(chain_grammar()))
        status, _, _ = self.run_command(
            "--grammar", str(grammar_path), "--grammar-id", "gchn",
            "--tokens", str(self.single), "--output-dir", str(base / "out3"),
            "--max-sweeps", "24")
        self.assertEqual(status, 3)

        status, _, stderr = self.run_command(*self.parse_args(base / "absent", base / "out2"))
        self.assertEqual(status, 2)
        self.assertIn("error[", stderr)

        status, _, stderr = self.run_command(*self.parse_args(accepted_only, base / "out0"))
        self.assertEqual(status, 2)
