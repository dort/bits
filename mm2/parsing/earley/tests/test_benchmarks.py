"""Tests for the benchmark harness: accounting, classification, cleanup.

These test the harness itself on tiny deterministic cases, not benchmark
timings. Assertions use known outcomes (verdicts, counts, cleanup state);
elapsed-time fields are only checked for presence, so timing noise cannot
fail them.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.support import OUTPUT, PROJECT
from benchmarks.cases import Case, catalan, registry
from benchmarks.parser import (classify_reason, engines_agreement,
                               measure_case, run_case, run_worker,
                               validate_row)


class ClassificationTests(unittest.TestCase):
    def test_reason_labels(self):
        self.assertIsNone(classify_reason(None))
        self.assertEqual(classify_reason("wall-time limit timeout_seconds=30.0"),
                         "wall-time")
        self.assertEqual(classify_reason("sweep budget limit max_sweeps=4"),
                         "sweeps")
        self.assertEqual(classify_reason("token limit: max_tokens=8 exceeded"),
                         "tokens")
        self.assertEqual(
            classify_reason("output-size limit max_dump_bytes=1 enforced"),
            "dump")
        self.assertEqual(
            classify_reason("memory limit max_process_bytes=1 (allocation)"),
            "memory")
        self.assertEqual(classify_reason("some novel diagnostic"), "other")


class WorkerSupervisionTests(unittest.TestCase):
    """run_worker classifies worker outcomes without the real registry."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.streams = Path(self._directory.name)

    def test_successful_worker_row_round_trips(self):
        row = {"case_id": "demo", "units": 1}
        outcome = run_worker(
            [sys.executable, "-c", f"print({json.dumps(json.dumps(row))})"],
            10.0, self.streams)
        self.assertEqual(outcome, {"status": "ok", "row": row})

    def test_failing_worker_is_classified_with_bounded_diagnostics(self):
        outcome = run_worker(
            [sys.executable, "-c",
             "import sys; sys.stderr.write('boom'); sys.exit(3)"],
            10.0, self.streams)
        self.assertEqual(outcome["status"], "worker-failed")
        self.assertEqual(outcome["exit_code"], 3)
        self.assertIn("boom", outcome["stderr_head"])

    def test_unparseable_worker_output_is_a_failure_not_a_row(self):
        outcome = run_worker([sys.executable, "-c", "print('not json')"],
                             10.0, self.streams)
        self.assertEqual(outcome["status"], "worker-failed")
        self.assertIn("no parseable result row", outcome["stderr_head"])

    def test_supervisor_timeout_kills_the_worker_promptly(self):
        started = time.monotonic()
        outcome = run_worker(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            0.2, self.streams)
        self.assertEqual(outcome["status"], "supervisor-timeout")
        self.assertLess(time.monotonic() - started, 10.0)

    def test_interrupting_the_supervisor_stops_worker_and_grandchild_first(self):
        """SIGINT to a supervisor kills the worker group, then cleans scratch.

        The worker runs in its own session, so the terminal interrupt does
        not reach it on its own; `run_worker` must stop the group — the MORK
        stand-in grandchild included — before the driver's cleanup removes
        the scratch directory they were using.
        """
        scratch = self.streams / "interrupt"
        scratch.mkdir()
        worker_code = (
            "import os, subprocess, sys, time\n"
            f"scratch = {str(scratch)!r}\n"
            "grand = subprocess.Popen([sys.executable, '-c',"
            " 'import time; time.sleep(120)'])\n"
            "open(scratch + '/grandchild-pid', 'w').write(str(grand.pid))\n"
            "open(scratch + '/worker-pid', 'w').write(str(os.getpid()))\n"
            "time.sleep(120)\n")
        driver_code = (
            "import shutil, sys\n"
            "from benchmarks.parser import run_worker\n"
            "try:\n"
            f"    run_worker([sys.executable, '-c', {worker_code!r}],"
            f" 120.0, {str(scratch)!r})\n"
            "finally:\n"
            f"    shutil.rmtree({str(scratch)!r}, ignore_errors=True)\n")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(PROJECT), str(PROJECT.parent / "lexer")])
        driver = subprocess.Popen([sys.executable, "-c", driver_code],
                                  cwd=str(PROJECT), env=env,
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL,
                                  start_new_session=True)
        pids = []
        try:
            deadline = time.monotonic() + 30.0
            worker_pid_file = scratch / "worker-pid"
            grand_pid_file = scratch / "grandchild-pid"
            while not (worker_pid_file.exists() and grand_pid_file.exists()):
                self.assertLess(time.monotonic(), deadline,
                                "worker never started")
                time.sleep(0.05)
            pids = [int(worker_pid_file.read_text()),
                    int(grand_pid_file.read_text())]
            os.kill(driver.pid, signal.SIGINT)
            driver.wait(timeout=30.0)
            for pid in pids:
                with self.assertRaises(ProcessLookupError,
                                       msg=f"process {pid} survived"):
                    os.kill(pid, 0)
            self.assertFalse(scratch.exists(),
                             "scratch must be removed after termination")
        finally:
            for pid in pids + [driver.pid]:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass


def accepted_row(**overrides):
    """A minimal valid row for a one-unit accepted recognition case."""
    row = {"units": 1, "published_rows": 1,
           "verdicts": {"accepted": 1, "rejected": 0, "incomplete": 0},
           "closure_complete_units": 1, "forest_complete_units": None,
           "enumeration": None, "incomplete_reasons": {},
           "trees_listed": 0, "distinct_trees": 0}
    row.update(overrides)
    return row


class ValidationTests(unittest.TestCase):
    """Semantic mismatches must fail validation; correct limits must not."""

    def case(self, **overrides):
        fields = dict(case_id="demo", dimension="tokens", grammar="expr",
                      text="fixed", tokens_per_unit=3, expect="accepted")
        fields.update(overrides)
        return Case(**fields)

    def test_a_valid_accepted_row_passes(self):
        self.assertEqual(validate_row(self.case(), accepted_row()), [])

    def test_wrong_recognition_fails(self):
        failures = validate_row(self.case(), accepted_row(
            verdicts={"accepted": 0, "rejected": 1, "incomplete": 0},
            closure_complete_units=1))
        self.assertTrue(any("verdicts" in failure for failure in failures))

    def test_wrong_unit_count_and_missing_published_rows_fail(self):
        failures = validate_row(self.case(), accepted_row(published_rows=0))
        self.assertTrue(any("published" in failure for failure in failures))
        failures = validate_row(
            self.case(unit_count=2),
            accepted_row())
        self.assertTrue(any("units" in failure for failure in failures))

    def test_incomplete_closure_fails_an_accepted_expectation(self):
        failures = validate_row(self.case(), accepted_row(
            closure_complete_units=0))
        self.assertTrue(any("closure" in failure for failure in failures))

    def test_a_correctly_named_limit_passes_and_a_wrong_one_fails(self):
        case = self.case(expect="incomplete", expect_reason="sweeps")
        row = accepted_row(
            verdicts={"accepted": 0, "rejected": 0, "incomplete": 1},
            closure_complete_units=0, incomplete_reasons={"sweeps": 1})
        self.assertEqual(validate_row(case, row), [])
        row["incomplete_reasons"] = {"wall-time": 1}
        failures = validate_row(case, row)
        self.assertTrue(any("sweeps" in failure for failure in failures))

    def test_enumeration_completion_and_duplicates_are_validated(self):
        case = self.case(engine="forest", max_trees=8, max_depth=10,
                         expect_enumeration="complete", expect_trees=2)
        row = accepted_row(forest_complete_units=1,
                           enumeration={"complete": 1, "incomplete": 0},
                           trees_listed=2, distinct_trees=2)
        self.assertEqual(validate_row(case, row), [])
        duplicated = dict(row, distinct_trees=1)
        failures = validate_row(case, duplicated)
        self.assertTrue(any("distinct" in failure for failure in failures))
        cut = dict(row, enumeration={"complete": 0, "incomplete": 1})
        failures = validate_row(case, cut)
        self.assertTrue(any("enumeration" in failure for failure in failures))


class EnginesAgreementTests(unittest.TestCase):
    def rows(self):
        verdicts = {"accepted": 1, "rejected": 0, "incomplete": 0}
        return {"a": {"verdicts": dict(verdicts)},
                "b": {"verdicts": dict(verdicts)}}

    def test_agreement_over_all_expected_participants(self):
        agreement = engines_agreement(["a", "b"], self.rows())
        self.assertEqual(agreement["status"], "ok")
        self.assertTrue(agreement["verdicts_agree"])
        self.assertEqual(agreement["compared"], ["a", "b"])

    def test_disagreeing_engines_fail(self):
        rows = self.rows()
        rows["b"]["verdicts"] = {"accepted": 0, "rejected": 1, "incomplete": 0}
        agreement = engines_agreement(["a", "b"], rows)
        self.assertEqual(agreement["status"], "validation-failed")
        self.assertTrue(any("disagree" in failure
                            for failure in agreement["failures"]))

    def test_a_missing_participant_does_not_shrink_the_comparison(self):
        rows = self.rows()
        del rows["b"]
        agreement = engines_agreement(["a", "b"], rows)
        self.assertEqual(agreement["status"], "validation-failed")
        self.assertTrue(any("missing" in failure
                            for failure in agreement["failures"]))

    def test_an_incomplete_participant_cannot_vouch_for_agreement(self):
        rows = self.rows()
        rows["b"]["verdicts"] = {"accepted": 0, "rejected": 0, "incomplete": 1}
        agreement = engines_agreement(["a", "b"], rows)
        self.assertEqual(agreement["status"], "validation-failed")
        self.assertTrue(any("compared" in failure
                            for failure in agreement["failures"]))


class AccountingTests(unittest.TestCase):
    """run_case aggregates real runner results into fixed-size accumulators."""

    @classmethod
    def setUpClass(cls):
        OUTPUT.mkdir(exist_ok=True)
        cls._directory = tempfile.TemporaryDirectory(dir=OUTPUT)
        cls.addClassCleanup(cls._directory.cleanup)
        cls.base = Path(cls._directory.name)

    def test_accepted_units_are_counted_with_staging_sizes_and_cleanup(self):
        scratch = self.base / "accepted"
        scratch.mkdir()
        row = run_case(Case("demo-units", "units", "expr", "fixed", 3,
                            unit_count=2), scratch)
        self.assertEqual(row["units"], 2)
        self.assertEqual(row["verdicts"],
                         {"accepted": 2, "rejected": 0, "incomplete": 0})
        self.assertEqual(row["closure_complete_units"], 2)
        self.assertEqual(row["incomplete_reasons"], {})
        self.assertEqual(row["item_count_max"], 13)
        self.assertGreaterEqual(row["engine_runs"], 4)
        self.assertEqual(row["engine_attempts"], row["engine_runs"])
        self.assertGreater(row["bytes"]["bundle"], 0)
        self.assertGreater(row["bytes"]["peak_engine_input"], 0)
        self.assertGreater(row["bytes"]["peak_engine_dump"], 0)
        self.assertGreater(row["bytes"]["peak_engine_staging"],
                           row["bytes"]["peak_engine_dump"])
        self.assertGreater(row["bytes"]["published_results"], 0)
        self.assertEqual(row["published_rows"], 2)
        self.assertTrue(row["work_dir_clean"])
        for stage in ("build_bundle", "validate_archive", "parse", "unit_max",
                      "serialize_results", "publish"):
            self.assertIn(stage, row["seconds"])
        self.assertEqual(validate_row(
            Case("demo-units", "units", "expr", "fixed", 3, unit_count=2,
                 expect="accepted"), row), [])

    def test_a_limit_result_is_incomplete_never_a_rejection(self):
        scratch = self.base / "limited"
        scratch.mkdir()
        row = run_case(Case("demo-limit", "limits", "expr", "fixed", 3,
                            runner={"max_tokens": 1}), scratch)
        self.assertEqual(row["verdicts"],
                         {"accepted": 0, "rejected": 0, "incomplete": 1})
        self.assertEqual(row["incomplete_reasons"], {"tokens": 1})
        self.assertEqual(row["closure_complete_units"], 0)
        self.assertEqual(row["engine_attempts"], 0)
        self.assertEqual(row["published_rows"], 1)

    def test_a_timed_out_writer_counts_its_attempt_and_partial_dump(self):
        """One killed engine process is one attempt with its actual bytes.

        The stand-in writes a 4,096-byte dump and sleeps past the unit
        deadline, so no budget completes; the attempt and the partial dump
        must still be accounted.
        """
        scratch = self.base / "standin"
        scratch.mkdir()
        engine = scratch / "fake-mork"
        engine.write_text(f"#!{sys.executable}\n"
                          "import sys, time\n"
                          "with open(sys.argv[3], 'wb') as dump:\n"
                          "    dump.write(b'x' * 4096)\n"
                          "time.sleep(10)\n")
        engine.chmod(0o755)
        work = self.base / "standin-work"
        work.mkdir()
        row = run_case(Case("demo-stall", "limits", "expr", "fixed", 3,
                            runner={"mork": str(engine),
                                    "timeout_seconds": 0.2}), work)
        self.assertEqual(row["verdicts"],
                         {"accepted": 0, "rejected": 0, "incomplete": 1})
        self.assertEqual(row["incomplete_reasons"], {"wall-time": 1})
        self.assertEqual(row["engine_attempts"], 1)
        self.assertEqual(row["engine_runs"], 0)
        self.assertEqual(row["budget_max"], 0)
        self.assertEqual(row["bytes"]["peak_engine_dump"], 4096)

    def test_enumerated_trees_match_the_exact_oracle_in_published_results(self):
        """concat over three tokens has exactly the two binary trees.

        The published `results.jsonl` must carry both, structurally equal to
        the hand-written oracle — a count alone cannot exclude one missing
        tree offset by one duplicate.
        """
        scratch = self.base / "oracle"
        scratch.mkdir()
        case = Case("demo-oracle", "engines", "concat", "ints", 3,
                    engine="forest", max_trees=8, max_depth=10)
        row = run_case(case, scratch)
        self.assertEqual(row["trees_listed"], 2)
        self.assertEqual(row["distinct_trees"], 2)
        self.assertEqual(row["enumeration"], {"complete": 1, "incomplete": 0})
        with (scratch / "results" / "results.jsonl").open() as published:
            unit_rows = [json.loads(line) for line in published]
        self.assertEqual(len(unit_rows), 1)

        def leaf(i):
            return {"nt": "s", "production": "one", "span": [i, i + 1],
                    "children": [{"t": "INT", "span": [i, i + 1]}]}

        def join(left, right, start, end):
            return {"nt": "s", "production": "join", "span": [start, end],
                    "children": [left, right]}

        oracle = [join(join(leaf(0), leaf(1), 0, 2), leaf(2), 0, 3),
                  join(leaf(0), join(leaf(1), leaf(2), 1, 3), 0, 3)]
        canonical = sorted(json.dumps(tree, sort_keys=True)
                           for tree in unit_rows[0]["trees"])
        self.assertEqual(canonical, sorted(json.dumps(tree, sort_keys=True)
                                           for tree in oracle))
        with (scratch / "results" / "forests.jsonl").open() as published:
            forest_rows = [json.loads(line) for line in published]
        self.assertEqual(len(forest_rows), 1)
        self.assertTrue(forest_rows[0]["graph_complete"])
        self.assertEqual(forest_rows[0]["stream_id"], "case_u0")
        summary = json.loads((scratch / "results" / "summary.json").read_text())
        self.assertEqual(summary["units"], 1)
        self.assertEqual(summary["counts"]["accepted"], 1)


class CleanupTests(unittest.TestCase):
    """measure_case removes its scratch directory on every outcome."""

    @classmethod
    def setUpClass(cls):
        OUTPUT.mkdir(exist_ok=True)
        cls._directory = tempfile.TemporaryDirectory(dir=OUTPUT)
        cls.addClassCleanup(cls._directory.cleanup)
        cls.base = Path(cls._directory.name)

    def case(self):
        return Case("demo-clean", "units", "expr", "fixed", 3)

    def test_normal_completion_leaves_no_scratch(self):
        outcome = measure_case(self.case(), self.base, 120.0)
        self.assertEqual(outcome["status"], "ok")
        self.assertEqual(outcome["row"]["verdicts"]["accepted"], 1)
        self.assertIn("peak_rss_kib", outcome["row"])
        self.assertIn("cleanup_seconds", outcome)
        self.assertEqual(list(self.base.iterdir()), [])

    def test_killed_worker_still_leaves_no_scratch(self):
        outcome = measure_case(self.case(), self.base, 0.01)
        self.assertEqual(outcome["status"], "supervisor-timeout")
        self.assertEqual(list(self.base.iterdir()), [])


class RegistryTests(unittest.TestCase):
    def test_case_identities_are_deterministic_and_unique(self):
        first = [case.case_id for case in registry()]
        second = [case.case_id for case in registry()]
        self.assertEqual(first, second)
        self.assertEqual(len(first), len(set(first)))

    def test_every_dimension_is_covered(self):
        dimensions = {case.dimension for case in registry()}
        self.assertEqual(dimensions,
                         {"control", "units", "tokens", "engines", "limits"})

    def test_enumeration_expectations_follow_the_catalan_count(self):
        self.assertEqual([catalan(n) for n in range(8)],
                         [1, 1, 2, 5, 14, 42, 132, 429])
        trees_case, = [case for case in registry()
                       if case.case_id.endswith("-trees")
                       and case.dimension == "engines"]
        self.assertEqual(trees_case.expect_trees, catalan(7))
        self.assertEqual(trees_case.expect_enumeration, "complete")
        bigger, = [case for case in registry(concat_tokens=(3, 10))
                   if case.case_id.endswith("-trees")
                   and case.dimension == "engines"]
        self.assertEqual(bigger.expect_trees, 512)
        self.assertEqual(bigger.expect_enumeration, "incomplete")


if __name__ == "__main__":
    unittest.main()
