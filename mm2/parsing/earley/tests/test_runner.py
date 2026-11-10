"""Tests for the per-unit MORK runner over real version-2 token bundles.

Each bundle is produced by the actual lexer pipeline (`source_records` +
`write_bundle`) with generated stream identities, then recognized through
`grammarc.Runner` and the `python -m grammarc parse` command against the real
binary.
"""

import contextlib
import io
import itertools
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.support import OUTPUT, PROJECT, FIXTURES
from grammarc import (Deadline, DeadlineExceeded, Runner, compile_grammar,
                      load_grammar, parse_facts, projection)
from grammarc.__main__ import main
from tokenizer import SourcePiece, load_spec, source_records, write_bundle

LEXER_SPEC = PROJECT.parent / "lexer/specs/expression_demo.json"


class FakeDeadline:
    """Expires after a fixed number of consultations; deterministic for tests."""

    def __init__(self, consultations):
        self.left = consultations

    def _tick(self):
        self.left -= 1
        return self.left < 0

    def expired(self):
        return self._tick()

    def check(self):
        if self._tick():
            raise DeadlineExceeded("wall-time limit timeout_seconds=0 (test)")

    def remaining(self):
        return 10.0 if self.left > 0 else 0.0


class SlowSecondRun(Runner):
    """Returns one real engine run's facts, then burns the unit deadline.

    The second `_execute` call sleeps past the deadline before handing back
    the cached first run, so every Python stage after it sees an exhausted
    deadline while a sound acceptance fact is already in hand.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache = None
        self.calls = 0

    def _execute(self, stream, demand, budget, deadline):
        self.calls += 1
        if self.cache is None:
            self.cache = super()._execute(stream, demand, budget, deadline)
        if self.calls == 2:
            time.sleep(max(deadline.remaining(), 0) + 0.05)
        return self.cache


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


class DeadlineTests(RunnerCase):
    def test_dump_parsing_and_projection_stop_at_the_deadline(self):
        self.assertTrue(Deadline(-1.0).expired())
        with self.assertRaises(DeadlineExceeded):
            Deadline(-1.0).check()
        with self.assertRaises(DeadlineExceeded):
            parse_facts("(item a b c x)", deadline=FakeDeadline(0))
        facts = parse_facts("(item a b c x)\n(accepted a b c)")
        with self.assertRaises(DeadlineExceeded):
            projection(facts, "a", "b", "c", ("item", "accepted"),
                       deadline=FakeDeadline(0))
        self.assertEqual(len(projection(facts, "a", "b", "c", ("item", "accepted"))),
                         2)

    def test_sound_acceptance_survives_expiry_with_no_new_forest_work(self):
        runner = SlowSecondRun(self.gexp, "gexp", engine="forest",
                               max_trees=10, max_depth=20, timeout_seconds=1.0)
        with mock.patch("grammarc.runner.Forest") as forest:
            unit, = runner.run_bundle(self.single)
        forest.assert_not_called()
        self.assertEqual(unit.recognition, "accepted")
        self.assertFalse(unit.closure_complete)
        self.assertFalse(unit.forest_complete)
        self.assertFalse(unit.enumeration_complete)
        self.assertIsNone(unit.graph)
        self.assertIn("wall-time", unit.reason)

    def test_enumeration_cut_by_the_deadline_names_the_limit(self):
        from grammarc.forest import Forest

        class DelayedEnumeration(Forest):
            def enumerate(self, max_trees, max_depth):
                time.sleep(1.3)
                return super().enumerate(max_trees, max_depth)

        runner = Runner(self.gexp, "gexp", engine="forest",
                        max_trees=10, max_depth=20, timeout_seconds=1.0)
        with mock.patch("grammarc.runner.Forest", DelayedEnumeration):
            unit, = runner.run_bundle(self.single)
        self.assertEqual(unit.recognition, "accepted")
        self.assertTrue(unit.closure_complete)
        self.assertTrue(unit.forest_complete)
        self.assertIsNotNone(unit.graph)
        self.assertFalse(unit.enumeration_complete)
        self.assertEqual(unit.trees, ())
        self.assertIn("wall-time", unit.reason)


class ResourceLimitTests(RunnerCase):
    def fake_engine(self, name, body):
        path = Path(self._directory.name) / f"{name}.py"
        path.write_text("#!/usr/local/bin/python3.14 -I\n" + body)
        path.chmod(0o755)
        return path

    def test_default_runner_has_a_finite_memory_ceiling(self):
        self.assertEqual(Runner(self.gexp, "gexp").max_process_bytes, 16 * 1024 ** 3)

    def test_oversized_dump_writer_is_stopped_at_the_bound(self):
        sentinel = Path(self._directory.name) / "sentinel"
        script = self.fake_engine("oversized", (
            "import os, sys\n"
            "with open(sys.argv[3], 'wb') as dump:\n"
            "    dump.write(b'x' * 2_097_152)\n"
            "with open(os.environ['GRAMMARC_TEST_SENTINEL'], 'w') as mark:\n"
            "    mark.write('continued past the bound')\n"))
        with mock.patch.dict(os.environ, {"GRAMMARC_TEST_SENTINEL": str(sentinel)}):
            unit, = Runner(self.gexp, "gexp", mork=script,
                           max_dump_bytes=1024).run_bundle(self.single)
        self.assertEqual(unit.recognition, "incomplete")
        self.assertIn("max_dump_bytes", unit.reason)
        self.assertIn("enforced", unit.reason)
        self.assertFalse(sentinel.exists(),
                         "the writer continued past the configured bound")

    def test_memory_exhaustion_is_a_verified_limit_outcome(self):
        # The real engine's startup arena allocation fails under a 1 GiB
        # address-space ceiling and aborts with an allocation message.
        unit, = Runner(self.gexp, "gexp",
                       max_process_bytes=1024 ** 3).run_bundle(self.single)
        self.assertEqual(unit.recognition, "incomplete")
        self.assertIn("max_process_bytes", unit.reason)
        self.assertEqual(unit.budgets, ())

    def test_ordinary_engine_failure_is_a_diagnostic_with_and_without_a_cap(self):
        script = self.fake_engine("failing", (
            "import sys\n"
            "sys.stderr.write('unrelated failure\\n')\n"
            "sys.exit(1)\n"))
        for cap in (None, 2 * 1024 ** 3):
            runner = Runner(self.gexp, "gexp", mork=script, max_process_bytes=cap)
            with self.assertRaises(RuntimeError) as caught:
                list(runner.run_bundle(self.single))
            self.assertIn("exit 1", str(caught.exception))
            self.assertIn("unrelated failure", str(caught.exception))


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
        preserved = [json.loads(line)
                     for line in (base / "out0/results.jsonl").read_text().splitlines()]
        self.assertEqual(len(preserved), 2, "an existing destination was altered")

    def test_failures_publish_nothing_and_do_not_block_a_retry(self):
        base = Path(self._directory.name)
        out = base / "staged"
        status, _, _ = self.run_command(*self.parse_args(base / "missing-bundle", out))
        self.assertEqual(status, 2)
        self.assertFalse(out.exists(), "a failed run left a final output directory")
        self.assertEqual(list(base.glob(f".{out.name}.*")), [],
                         "a failed run left its staging directory")
        status, _, _ = self.run_command(*self.parse_args(self.mixed, out))
        self.assertEqual(status, 1)
        self.assertTrue((out / "results.jsonl").exists())
        self.assertTrue((out / "summary.json").exists())

    def test_interruption_and_midway_failure_clean_their_staging(self):
        base = Path(self._directory.name)
        with mock.patch.object(Runner, "run_bundle", side_effect=KeyboardInterrupt):
            status, _, _ = self.run_command(*self.parse_args(self.mixed, base / "intr"))
        self.assertEqual(status, 130)
        self.assertFalse((base / "intr").exists())
        self.assertEqual(list(base.glob(".intr.*")), [])

        real = Runner.run_bundle

        def flaky(runner, bundle, **kwargs):
            yield from itertools.islice(real(runner, bundle, **kwargs), 1)
            raise RuntimeError("engine failed after one unit")

        with mock.patch.object(Runner, "run_bundle", flaky):
            status, _, stderr = self.run_command(*self.parse_args(self.mixed, base / "half"))
        self.assertEqual(status, 2)
        self.assertIn("after one unit", stderr)
        self.assertFalse((base / "half").exists())
        self.assertEqual(list(base.glob(".half.*")), [])

    def test_forest_command_publishes_graphs_in_a_fixed_file_set(self):
        base = Path(self._directory.name)
        bundle = build_bundle(base / "graphs", ["x + 12"])
        out = base / "forest-out"
        status, _, _ = self.run_command(*self.parse_args(bundle, out, "--engine", "forest"))
        self.assertEqual(status, 0)
        self.assertEqual(sorted(path.name for path in out.iterdir()),
                         ["forests.jsonl", "results.jsonl", "summary.json"])
        row, = [json.loads(line)
                for line in (out / "results.jsonl").read_text().splitlines()]
        self.assertNotIn("graph", row)
        forest_row, = [json.loads(line)
                       for line in (out / "forests.jsonl").read_text().splitlines()]
        self.assertEqual(forest_row["stream_id"], row["stream_id"])
        self.assertTrue(forest_row["graph_complete"])
        self.assertGreater(len(forest_row["graph"]["nodes"]), 0)
        self.assertGreater(len(forest_row["graph"]["parts"]), 0)
        summary = json.loads((out / "summary.json").read_text())
        self.assertIn("max_trees", summary["limits"])
        self.assertIn("max_depth", summary["limits"])
        recognition = self.run_command(*self.parse_args(bundle, base / "rec-out"))
        self.assertEqual(recognition[0], 0)
        self.assertFalse((base / "rec-out/forests.jsonl").exists())

    def test_enumeration_timeout_makes_the_command_incomplete(self):
        base = Path(self._directory.name)
        with mock.patch("grammarc.__main__.Runner", SlowSecondRun):
            status, _, _ = self.run_command(
                *self.parse_args(self.single, base / "enum-timeout",
                                 "--engine", "forest", "--max-trees", "10",
                                 "--max-depth", "20", "--timeout-seconds", "1.0"))
        self.assertEqual(status, 3)
        row, = [json.loads(line) for line in
                (base / "enum-timeout/results.jsonl").read_text().splitlines()]
        self.assertEqual(row["recognition"], "accepted")
        self.assertFalse(row["enumeration_complete"])
        self.assertIn("wall-time", row["reason"])
