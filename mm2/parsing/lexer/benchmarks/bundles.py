"""Measure v2 archive memory as unit count grows, with fresh worker processes."""

import argparse
import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
import tracemalloc

from tokenizer import BundleReader, SourcePiece, compile_spec, source_records, write_bundle
from tokenizer.envelope import IdentityTracker


HERE = Path(__file__).resolve().parents[1]


def worker(count):
    compiled = compile_spec({"version": 1, "rules": [{"name": "x", "literal": "x", "kind": "X"}]})
    root = HERE / "output/benchmark-tmp"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        path = Path(temporary) / "bundle"
        pieces = (SourcePiece("x", following="x" if index + 1 < count else "") for index in range(count))
        start = time.perf_counter()
        manifest = write_bundle(source_records(pieces, compiled, namespace="bench", source_id="batch",
                                               max_units=max(1, count), max_unit_chars=1), path)
        written = time.perf_counter()
        reader = BundleReader(path)
        visited = 0
        for entry in reader.iter_entries():
            visited += 1
        indexed = time.perf_counter()
        if count:
            reader.read_stream(entry, max_tokens=1, max_chars=1)
        records = sum(1 for _ in reader.iter_records())
        verified = time.perf_counter()
        if visited != count or manifest["unit_count"] != count:
            raise RuntimeError("archive unit count differs")
        return dict(units=count, writer_seconds=round(written - start, 6),
                    index_seconds=round(indexed - written, 6),
                    verification_seconds=round(verified - indexed, 6), records=records,
                    output_bytes=sum(file.stat().st_size for file in path.iterdir()),
                    peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def identity_peak(policy, count=100000):
    tracker = IdentityTracker(policy, namespace="bench",
                              stream_base="batch" if policy == "generated" else None, max_units=count)
    tracemalloc.start()
    try:
        for index in range(count):
            tracker.add("bench", f"batch_u{index}", index)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units", type=int, nargs="+", default=[100, 10000])
    parser.add_argument("--worker", type=int)
    parser.add_argument("--report", default="output/bundle-v2-benchmark.json")
    args = parser.parse_args()
    if args.worker is not None:
        print(json.dumps(worker(args.worker)))
        return
    rows = []
    for count in args.units:
        if count < 0:
            parser.error("unit counts must be nonnegative")
        result = subprocess.run([sys.executable, "-m", "benchmarks.bundles", "--worker", str(count)],
                                cwd=HERE, capture_output=True, text=True, check=True, timeout=180)
        row = json.loads(result.stdout)
        rows.append(row)
        print(json.dumps(row), flush=True)
    report = dict(python=sys.version, rows=rows,
                  identity_peak_allocated_bytes={policy: identity_peak(policy) for policy in ("caller", "generated")},
                  notes=["One-character units; fresh processes; peak RSS includes writing and full archive validation.",
                         "Generated identities; index rows and records consumed without retention.",
                         "Identity allocation measurements track 100000 IDs with tracemalloc, separately from RSS."])
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
