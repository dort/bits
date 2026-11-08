from collections import namedtuple
import json
import subprocess
import sys
from unittest.mock import patch

from tokenizer import RuntimeVersionError, compile_spec
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
