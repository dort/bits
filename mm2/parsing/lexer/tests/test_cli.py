from collections import namedtuple
import io
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

from tokenizer import BundleReader, RuntimeVersionError, compile_spec
from tests.support import HERE, TempCase


class CliTests(TempCase):
    def run_cli(self, *args, input=None):
        return subprocess.run([sys.executable, "-m", "tokenizer", *map(str, args)],
                              cwd=HERE, input=input, capture_output=True, timeout=15)

    def args(self, output, source="-"):
        return ["--spec", HERE / "specs/expression_demo.json", "--input", source,
                "--namespace", "demo", "--stream-id", "s0", "--output-dir", output]

    def test_stdin_and_file_agree(self):
        text = b'x + 12\r\n'
        path = self.directory / "input"
        path.write_bytes(text)
        first, second = self.directory / "stdin", self.directory / "file"
        a = self.run_cli(*self.args(first), input=text)
        b = self.run_cli(*self.args(second, path))
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertEqual(b.returncode, 0, b.stderr)
        self.assertEqual((first / "tokens.mm2").read_bytes(), (second / "tokens.mm2").read_bytes())
        self.assertEqual(json.loads((first / "manifest.json").read_text())["source_length"], 8)

    def test_errors_have_exit_status_and_no_completed_output(self):
        for data, options, expected, category in [
            (b'x@', [], 1, b'lexical'), (b'\xff', [], 1, b'source'),
            (b'ab', ["--max-bytes", "1"], 1, b'limit'),
            (b'ab', ["--max-chars", "1"], 1, b'limit'),
            (b'x', ["--namespace", "$invalid"], 2, b'configuration'),
            (b'x', ["--encoding", "not-an-encoding"], 2, b'configuration'),
        ]:
            with self.subTest(data=data, options=options):
                output = self.directory / "result"
                result = self.run_cli(*self.args(output), *options, input=data)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertIn(category, result.stderr)
                self.assertNotIn(b'Traceback', result.stderr)
                self.assertFalse(output.exists())

    def test_bad_spec_fails_before_source_access(self):
        path = self.directory / "bad.json"
        path.write_text('{"version":1.0,"rules":[]}')
        result = self.run_cli(*self.args(self.directory / "out", self.directory / "missing"),
                              "--spec", path)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'version', result.stderr)
        self.assertFalse((self.directory / "out").exists())

    def test_runtime_version_guard(self):
        version = namedtuple("Version", "major minor")(3, 13)
        with patch("tokenizer.model.sys.version_info", version):
            with self.assertRaisesRegex(RuntimeVersionError, "requires Python 3.14"):
                compile_spec({"version": 1, "rules": []})

    def split_spec(self, **changes):
        path = self.directory / "split.json"
        path.write_text(json.dumps(dict(version=1, separator={"literal": "\n"},
                                        max_unit_chars=32, **changes)))
        return path

    def test_split_cli_stdin_and_file(self):
        text = b'x + 12\r\ny + 3\n'
        source = self.directory / "input"
        source.write_bytes(text)
        split = self.split_spec()
        outputs = []
        for label in ["-", source]:
            output = self.directory / ("stdin" if label == "-" else "file")
            result = self.run_cli(*self.args(output, label), "--split-spec", split,
                                  input=text if label == "-" else None)
            self.assertEqual(result.returncode, 0, result.stderr)
            reader = BundleReader(output)
            entries = list(reader.iter_entries())
            self.assertEqual([e["stream_id"] for e in entries], ["s0_u0", "s0_u1"])
            self.assertEqual([reader.read_stream(e).end.token_count for e in entries], [3, 3])
            outputs.append((output / "tokens.mm2").read_bytes())
        self.assertEqual(*outputs)

    def test_split_cli_limits_drops_and_late_errors(self):
        split = self.split_spec(retain="gap", empty_units="drop")
        output = self.directory / "empty"
        result = self.run_cli(*self.args(output), "--split-spec", split, input=b'\n\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual((manifest["unit_count"], manifest["gap_count"], manifest["dropped_empty_count"]),
                         (0, 2, 2))
        for data, options in [(b'x\ny', ["--max-units", "1"]),
                              (b'x\ny', ["--max-chars", "2"]),
                              (b'x\ny', ["--max-bytes", "2"]),
                              (b'x\ny@', []), (b'x\ny\xff', [])]:
            output = self.directory / "failure"
            result = self.run_cli(*self.args(output), "--split-spec", split, *options, input=data)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertNotIn(b'Traceback', result.stderr)
            self.assertFalse(output.exists())
            self.assertEqual(list(self.directory.glob(".failure.*")), [])

    def test_bad_split_configuration_precedes_source_access(self):
        split = self.directory / "bad-split.json"
        split.write_text(json.dumps({"version": 1, "separator": {"pattern": "a(?=b)", "max_length": 1},
                                     "max_unit_chars": 32}))
        result = self.run_cli(*self.args(self.directory / "out", self.directory / "missing"),
                              "--split-spec", split)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(b'pattern', result.stderr)
        self.assertNotIn(b'Traceback', result.stderr)

    def test_split_and_unsplit_default_source_limits(self):
        from tokenizer.__main__ import main

        # Lower the finite-input defaults to exercise mode selection with a tiny
        # real source. Split mode's default totals must remain unlimited.
        for splitting, expected in [(False, 1), (True, 0)]:
            output = self.directory / str(splitting)
            args = list(map(str, self.args(output)))
            if splitting:
                args += ["--split-spec", str(self.split_spec())]
            with (patch("tokenizer.__main__.DEFAULT_MAX_BYTES", 1),
                  patch("tokenizer.__main__.DEFAULT_MAX_CHARS", 1),
                  patch("sys.stdin", SimpleNamespace(buffer=io.BytesIO(b'x\ny'))),
                  patch("sys.stdout", io.StringIO()), patch("sys.stderr", io.StringIO())):
                self.assertEqual(main(args), expected)
            self.assertEqual(output.exists(), splitting)
