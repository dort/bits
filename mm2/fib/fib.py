#!/usr/bin/env python3
"""Run the Fibonacci MM2 program through the reusable magic-sets engine."""

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "magic_sets"))
from run import run_file, sexpr


def run_fibonacci(indices, timeout=60):
    """Construct query facts and invoke MORK; no Fibonacci arithmetic in Python."""
    indices = sorted(set(indices))
    if any(not isinstance(index, int) or not 0 <= index <= 92 for index in indices):
        raise ValueError("indices must be integers from 0 through 92 (exact signed-i64 results)")
    queries = [
        f"(query fib-{index} (atom fib (cons (c {index}) (cons (v value) nil))))"
        for index in indices
    ]
    with tempfile.TemporaryDirectory(prefix="mm2-fib-") as directory:
        path = Path(directory) / "input.mm2"
        path.write_text((HERE / "fib.mm2").read_text() + "\n" + "\n".join(queries) + "\n")
        space, log = run_file(path, timeout=timeout)
    answered = {expr[1] for expr in space if isinstance(expr, tuple) and expr and expr[0] == "result"}
    expected = {f"fib-{index}" for index in indices}
    if answered != expected:
        raise RuntimeError(f"incomplete Fibonacci results: expected {expected}, got {answered}")
    return space, log


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("indices", nargs="*", type=int, help="indices 0..92; default: 10")
    parser.add_argument("--show", choices=("answers", "magic", "rules", "derived", "all"), default="answers")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    try:
        space, log = run_fibonacci(args.indices or [10], args.timeout)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    tags = {"answers": "result", "magic": "magic", "rules": "generated", "derived": "derived"}
    for expr in space:
        if args.show == "all" or (isinstance(expr, tuple) and expr and expr[0] == tags[args.show]):
            print(sexpr(expr))
    if args.stats:
        for line in log.splitlines():
            if line.startswith("executing "):
                print(line, file=sys.stderr)
        for tag in ("result", "magic", "derived"):
            print(f"{tag}: {sum(isinstance(e, tuple) and bool(e) and e[0] == tag for e in space)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
