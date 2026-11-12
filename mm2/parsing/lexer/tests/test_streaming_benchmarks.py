import dataclasses
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import tracemalloc
from unittest.mock import patch

from benchmarks.streaming import (Case, Oracle, RepeatingReader, STAGES, WORKLOADS,
                                  ValidationFailure, fixture, main, measure,
                                  run_worker)
from tokenizer import Token
import tokenizer.envelope as envelope
from tests.support import HERE, TempCase


def alive(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1][0] != "Z"
    except FileNotFoundError:
        return False


class StreamingMeasurementTests(TempCase):
    def test_virtual_source_is_bounded_and_exact_across_reads(self):
        pattern = "λ😀\r\n".encode("utf-8")
        tracemalloc.start()
        try:
            reader = RepeatingReader(pattern, 10**12)
            chunks = [reader.read(size) for size in (1, 3, 17, 64)]
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 128 * 1024)
        self.assertEqual(b"".join(chunks), (pattern * 20)[:85])
        small = RepeatingReader(pattern, 2)
        self.assertEqual(small.read(100), pattern * 2)
        self.assertEqual(small.read(100), b"")
        with self.assertRaises(ValueError):
            reader.read(-1)

    def test_all_fixtures_and_stages_have_real_oracles_and_output(self):
        for name in WORKLOADS:
            definition = fixture(name)
            expected_hash = hashlib.sha256((definition.text * 2).encode("utf-8")).hexdigest()
            for stage in STAGES:
                with self.subTest(workload=name, stage=stage):
                    scratch = self.directory / f"{name}-{stage}"
                    scratch.mkdir()
                    row = measure(Case(name, 2, stage), scratch, chunk_bytes=7)
                    self.assertEqual(row["status"], "ok")
                    self.assertEqual(row["input"]["sha256"], expected_hash)
                    self.assertEqual(row["input"]["characters"], len(definition.text) * 2)
                    if stage in ("lex", "bundle"):
                        self.assertEqual(row["lexical_tokens"], len(definition.tokens) * 2)
                    if stage == "bundle":
                        self.assertEqual(set(row["files"]),
                                         {"tokens.jsonl", "tokens.mm2", "streams.jsonl", "manifest.json"})
                        self.assertEqual(row["output_bytes"], sum(p.stat().st_size for p in (scratch/"bundle").iterdir()))
                        self.assertEqual({name: value["bytes"] for name, value in row["staging_files"].items()},
                                         {name: value["bytes"] for name, value in row["files"].items()})
                    else:
                        self.assertEqual(row["output_bytes"], 0)
                    self.assertTrue(all(value is None or value >= 0 for value in row["seconds"].values()))

    def test_wrong_tokens_fail_and_bundle_is_not_published(self):
        original = envelope.tokenize
        def corrupted(*args, **kwargs):
            for record in original(*args, **kwargs):
                yield dataclasses.replace(record, kind="WRONG") if isinstance(record, Token) else record
        with patch.object(envelope, "tokenize", corrupted):
            with self.assertRaisesRegex(ValidationFailure, "token differs"):
                measure(Case("tiny", 2, "bundle"), self.directory)
        self.assertFalse((self.directory / "bundle").exists())
        self.assertEqual(list(self.directory.glob(".bundle.*")), [])

    def test_missing_source_completion_fails(self):
        oracle = Oracle(fixture("tiny"), 1)
        with self.assertRaisesRegex(ValidationFailure, "missing source completion"):
            list(oracle.checked_records([]))

    def test_publication_checks_logical_content_not_block_allocation_timing(self):
        import benchmarks.streaming as streaming
        original = streaming.file_sizes
        calls = []
        def allocations(path):
            sizes = original(path)
            calls.append(path)
            if len(calls) == 2:
                for value in sizes.values():
                    value["allocated_bytes"] += 4096
            return sizes
        with patch.object(streaming, "file_sizes", allocations):
            row = measure(Case("tiny", 1, "bundle"), self.directory)
        self.assertEqual(row["status"], "ok")


class StreamingSupervisorTests(TempCase):
    def test_failure_and_bad_rows_are_not_success(self):
        for code in ["print('not json')", "import sys; sys.stderr.write('broken'); sys.exit(2)",
                     "print('{\"status\":\"unexpected\"}')",
                     "import sys; print('{\"status\":\"ok\"}'); sys.exit(1)"]:
            outcome = run_worker([sys.executable, "-c", code], self.directory, timeout_seconds=5)
            self.assertEqual(outcome["status"], "worker-failed")

    def test_timeout_stops_the_worker(self):
        marker = self.directory / "pid"
        code = f"import os,time; from pathlib import Path; Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(30)"
        outcome = run_worker([sys.executable, "-c", code], self.directory, timeout_seconds=0.2)
        self.assertEqual(outcome["status"], "supervisor-timeout")
        self.assertTrue(marker.exists())
        self.assertFalse(alive(int(marker.read_text())))

    def test_failed_worker_does_not_leave_a_grandchild(self):
        marker = self.directory / "child-pid"
        code = ("import subprocess,sys\nfrom pathlib import Path\n"
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n"
                f"Path({str(marker)!r}).write_text(str(child.pid))\n"
                "sys.exit(2)\n")
        child = None
        try:
            outcome = run_worker([sys.executable, "-c", code], self.directory, timeout_seconds=5)
            child = int(marker.read_text())
            self.assertEqual(outcome["status"], "worker-failed")
            deadline = time.monotonic() + 5
            while alive(child) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(alive(child))
        finally:
            if child is not None and alive(child):
                os.kill(child, signal.SIGKILL)

    def test_interruption_stops_worker_and_grandchild_before_cleanup(self):
        marker = self.directory / "pids"
        worker_code = (
            "import os,subprocess,sys,time\nfrom pathlib import Path\n"
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n"
            f"Path({str(marker)!r}).write_text(str(os.getpid())+' '+str(child.pid))\n"
            "time.sleep(30)\n")
        supervisor_code = (
            "import sys,tempfile\nfrom benchmarks.streaming import run_worker\ntry:\n"
            f"    with tempfile.TemporaryDirectory(prefix='case-',dir={str(self.directory)!r}) as scratch:\n"
            f"        run_worker([sys.executable,'-c',{worker_code!r}],scratch,timeout_seconds=60)\n"
            "except KeyboardInterrupt:\n    sys.exit(130)\n")
        supervisor = subprocess.Popen([sys.executable, "-c", supervisor_code], cwd=HERE,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       start_new_session=True)
        worker = child = None
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            worker, child = map(int, marker.read_text().split())
            os.kill(supervisor.pid, signal.SIGINT)
            self.assertEqual(supervisor.wait(timeout=5), 130)
            deadline = time.monotonic() + 5
            while (alive(worker) or alive(child)) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(alive(worker))
            self.assertFalse(alive(child))
            self.assertEqual(list(self.directory.glob("case-*")), [])
        finally:
            if worker is not None:
                try:
                    os.killpg(worker, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if supervisor.poll() is None:
                os.killpg(supervisor.pid, signal.SIGKILL)
                supervisor.wait(timeout=5)

    def test_memory_qualification_failure_has_nonzero_exit_and_cleanup(self):
        output = self.directory / "report"
        result = subprocess.run([sys.executable, "-m", "benchmarks.streaming", "--workloads", "tiny",
                                 "--units", "1", "--stages", "bundle", "--max-rss-mib", "1", "--out", str(output)],
                                cwd=HERE, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 1, result.stderr)
        row = json.loads((output/"rows.jsonl").read_text())
        self.assertEqual(row["status"], "qualification-failed")
        self.assertEqual(row["validation"], "passed")
        self.assertTrue(row["scratch_removed"])
        self.assertEqual(list(output.glob("tmp-*")), [])

    def test_invalid_options_fail_before_output_creation(self):
        for options in [("--units", "0"), ("--units", "-1"), ("--timeout-seconds", "nan"),
                        ("--timeout-seconds", "inf"), ("--chunk-bytes", "0")]:
            with self.subTest(options=options), patch("sys.stderr", io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    main([*options, "--out", str(self.directory/"absent")])
                self.assertEqual(caught.exception.code, 2)
            self.assertFalse((self.directory/"absent").exists())
