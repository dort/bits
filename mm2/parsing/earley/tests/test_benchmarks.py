"""Tests for the benchmark harness: accounting, classification, cleanup.

These test the harness itself on tiny deterministic cases, not benchmark
timings. Assertions use known outcomes (verdicts, counts, cleanup state);
elapsed-time fields are only checked for presence, so timing noise cannot
fail them.
"""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.support import OUTPUT
from benchmarks.cases import Case, registry
from benchmarks.parser import (classify_reason, measure_case, run_case,
                               run_worker)


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
        self.assertGreater(row["bytes"]["bundle"], 0)
        self.assertGreater(row["bytes"]["peak_engine_input"], 0)
        self.assertGreater(row["bytes"]["peak_engine_dump"], 0)
        self.assertTrue(row["work_dir_clean"])
        for stage in ("build_bundle", "validate_archive", "parse", "unit_max"):
            self.assertIn(stage, row["seconds"])

    def test_a_limit_result_is_incomplete_never_a_rejection(self):
        scratch = self.base / "limited"
        scratch.mkdir()
        row = run_case(Case("demo-limit", "limits", "expr", "fixed", 3,
                            runner={"max_tokens": 1}), scratch)
        self.assertEqual(row["verdicts"],
                         {"accepted": 0, "rejected": 0, "incomplete": 1})
        self.assertEqual(row["incomplete_reasons"], {"tokens": 1})
        self.assertEqual(row["closure_complete_units"], 0)


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


if __name__ == "__main__":
    unittest.main()
