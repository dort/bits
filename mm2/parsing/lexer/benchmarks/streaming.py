"""Source pipeline measurements with lazy input and fresh, supervised workers.

Run from lexer/: .venv/bin/python -m benchmarks.streaming
Input generation, timed iterator advancement, and the correctness oracle keep
bounded state. Bundle runs exercise the actual writer and atomic publisher.
"""

import argparse
from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from tokenizer import (BundleReader, DecodedStream, Gap, Skipped, SourceEnd,
                       StreamEnd, Token, UnitStart, compile_spec, compile_split_spec,
                       load_spec, source_records, split_chunks, write_bundle)
from tokenizer.bundle import publish_directory


HERE = Path(__file__).resolve().parents[1]
WORKLOADS = ("dense", "long", "tiny", "headers", "unicode", "gaps")
STAGES = ("decode", "split", "lex", "bundle")
MIB = 1024 * 1024
ROW_BYTES = 65536


class ValidationFailure(ValueError):
    """Measured output disagrees with the deterministic fixture."""


def require(condition, message):
    if not condition:
        raise ValidationFailure(message)


@dataclass(frozen=True)
class Case:
    workload: str
    units: int
    stage: str

    @property
    def name(self):
        return f"{self.workload}-n{self.units}-{self.stage}"

    def validate(self):
        if self.workload not in WORKLOADS or self.stage not in STAGES:
            raise ValueError("unknown workload or stage")
        if type(self.units) is not int or self.units < 1:
            raise ValueError("unit counts must be positive integers")


@dataclass(frozen=True)
class Fixture:
    text: str
    parts: tuple
    tokens: tuple
    lexical: object
    splitting: object


def fixture(name):
    word_rules = [{"name": "word", "pattern": "[a-z]+", "kind": "WORD"},
                  {"name": "space", "pattern": r"\s+", "skip": True}]
    lexical = compile_spec({"version": 1, "rules": word_rules})
    split_raw = {"version": 1, "separator": {"literal": "\n"}, "max_unit_chars": 4096}
    if name == "dense":
        text = "x + 12 " * 9 + "\n"
        lexical = load_spec(HERE / "specs/expression_demo.json")
        tokens = (("IDENT", "x"), ("PLUS", "+"), ("INT", "12")) * 9
    elif name == "long":
        text = "x" * 4095 + "\n"
        tokens = (("WORD", text[:-1]),)
    elif name in ("tiny", "gaps"):
        text = "x\n"
        tokens = (("WORD", "x"),)
    elif name == "headers":
        text = "UNIT 0001: " + "x" * 116 + "\n"
        lexical = compile_spec({"version": 1, "rules": [
            {"name": "header", "pattern": "^UNIT [0-9]{4}: ", "skip": True}, *word_rules]})
        split_raw = {"version": 1, "boundary": {
            "pattern": "^UNIT [0-9]{4}: ", "max_length": 11, "flags": ["MULTILINE"]},
            "preamble": "reject", "max_unit_chars": 4096}
        tokens = (("WORD", "x" * 116),)
    elif name == "unicode":
        text = "λ😀" * 31 + "\r\n"
        lexical = compile_spec({"version": 1, "rules": [
            {"name": "text", "pattern": r"[^\r\n]+", "kind": "TEXT"},
            {"name": "space", "pattern": r"[\r\n]+", "skip": True}]})
        split_raw["separator"] = {"literal": "\r\n"}
        tokens = (("TEXT", text[:-2]),)
    else:
        raise ValueError(f"unknown workload {name!r}")
    parts = ((text, "unit"),)
    if name == "gaps":
        split_raw["retain"] = "gap"
        parts = (("x", "unit"), ("\n", "gap"))
    return Fixture(text, parts, tokens, lexical, compile_split_spec(split_raw))


class RepeatingReader:
    """A finite virtual source; each read allocates at most request + one unit."""

    def __init__(self, pattern, count):
        self.pattern = pattern
        self.length = len(pattern) * count
        self.position = self.calls = 0
        self.seconds = 0.0
        self.digest = hashlib.sha256()

    def read(self, size):
        if type(size) is not int or size < 0:
            raise ValueError("benchmark input requires bounded binary reads")
        started = time.perf_counter()
        count = min(size, self.length - self.position)
        offset = self.position % len(self.pattern)
        copies = (offset + count + len(self.pattern) - 1) // len(self.pattern)
        data = (self.pattern * copies)[offset:offset + count] if count else b""
        self.position += count
        self.calls += 1
        self.digest.update(data)
        self.seconds += time.perf_counter() - started
        return data


def timed_values(values, totals, label):
    iterator = iter(values)
    while True:
        started = time.perf_counter()
        try:
            value = next(iterator)
        except StopIteration:
            return
        finally:
            totals[label] += time.perf_counter() - started
        yield value


class Oracle:
    """Validate known pieces/tokens and exact reconstruction without retaining them."""

    def __init__(self, definition, count):
        self.definition, self.count = definition, count
        self.units = self.chars = self.token_count = self.in_unit = self.pieces = 0
        self.gaps = 0
        self.ended = False
        self.digest = hashlib.sha256()
        self.seconds = 0.0

    def text(self, value):
        self.chars += len(value)
        self.digest.update(value.encode("utf-8"))

    def piece(self, value):
        expected = self.definition.parts[self.pieces % len(self.definition.parts)]
        require((value.text, value.disposition) == expected, "split piece differs from fixture")
        self.text(value.text)
        following = (self.definition.text[self.chars % len(self.definition.text)]
                     if self.chars < self.count * len(self.definition.text) else "")
        require(value.following == following, "split following-character context differs")
        self.units += value.disposition == "unit"
        self.gaps += value.disposition == "gap"
        self.pieces += 1

    def record(self, value):
        if isinstance(value, UnitStart):
            require(value.unit_index == self.units and value.stream_id == f"source_u{self.units}",
                    "unit identity differs from fixture")
            require(value.span.char_start == self.units * len(self.definition.text), "unit start differs")
        elif isinstance(value, Token):
            require(self.in_unit < len(self.definition.tokens), "unexpected extra token")
            require((value.kind, value.lexeme) == self.definition.tokens[self.in_unit],
                    "token differs from fixture")
            require(value.index == self.in_unit, "token index differs")
            self.in_unit += 1
            self.token_count += 1
            self.text(value.lexeme)
        elif isinstance(value, Skipped):
            self.text(value.lexeme)
        elif isinstance(value, Gap):
            require((value.text, "gap") in self.definition.parts, "unexpected gap")
            self.gaps += 1
            self.text(value.text)
        elif isinstance(value, StreamEnd):
            require(value.token_count == self.in_unit == len(self.definition.tokens), "unit token count differs")
            require(value.source_length == len(self.definition.parts[0][0]), "unit character count differs")
            self.units += 1
            self.in_unit = 0
        elif isinstance(value, SourceEnd):
            require(value.unit_count == self.count and value.source_length == self.count * len(self.definition.text),
                    "source completion differs")
            self.ended = True

    def checked_records(self, records):
        for value in records:
            started = time.perf_counter()
            self.record(value)
            self.seconds += time.perf_counter() - started
            yield value
        require(self.ended, "missing source completion")

    def finish(self, reader, *, stage):
        require(reader.position == reader.length, "input was not exhausted")
        require(self.chars == self.count * len(self.definition.text), "reconstructed character count differs")
        require(self.digest.digest() == reader.digest.digest(), "reconstructed UTF-8 bytes differ")
        if stage != "decode":
            require(self.units == self.count, "unit count differs")
            expected_gaps = self.count * sum(kind == "gap" for _, kind in self.definition.parts)
            require(self.gaps == expected_gaps, "gap count differs")
        if stage in ("lex", "bundle"):
            require(self.ended and self.token_count == self.count * len(self.definition.tokens),
                    "lexical completion differs")


def file_sizes(directory):
    files = {}
    for path in sorted(Path(directory).iterdir()):
        if path.is_file():
            stat = path.stat()
            files[path.name] = {"bytes": stat.st_size, "allocated_bytes": stat.st_blocks * 512}
    return files


def measure(case, scratch, *, chunk_bytes=65536):
    case.validate()
    definition = fixture(case.workload)
    reader = RepeatingReader(definition.text.encode("utf-8"), case.units)
    oracle = Oracle(definition, case.units)
    totals = {name: 0.0 for name in ("decode", "split", "lex")}
    staged = {}
    publication_seconds = observation_seconds = 0.0
    started = time.perf_counter()
    decoded = DecodedStream(reader, max_bytes=None, max_chars=None, chunk_size=chunk_bytes)
    chunks = timed_values(decoded, totals, "decode")
    if case.stage == "decode":
        for chunk in chunks:
            check_start = time.perf_counter()
            oracle.text(chunk)
            oracle.seconds += time.perf_counter() - check_start
    else:
        pieces = timed_values(split_chunks(chunks, definition.splitting), totals, "split")
        if case.stage == "split":
            for piece in pieces:
                check_start = time.perf_counter()
                oracle.piece(piece)
                oracle.seconds += time.perf_counter() - check_start
        else:
            records = source_records(pieces, definition.lexical, namespace="bench", source_id="source",
                                     max_units=case.units, max_unit_chars=definition.splitting.max_unit_chars,
                                     split_fingerprint=definition.splitting.fingerprint)
            records = oracle.checked_records(timed_values(records, totals, "lex"))
            if case.stage == "lex":
                for _ in records:
                    pass
            else:
                def publish(staging, destination):
                    nonlocal staged, publication_seconds, observation_seconds
                    before = time.perf_counter()
                    staged = file_sizes(staging)
                    observation_seconds += time.perf_counter() - before
                    before = time.perf_counter()
                    publish_directory(staging, destination)
                    publication_seconds += time.perf_counter() - before

                with patch("tokenizer.bundle.publish_directory", side_effect=publish):
                    write_bundle(records, Path(scratch) / "bundle")
    elapsed = time.perf_counter() - started
    require(decoded.complete, "decoder did not finish")
    oracle.finish(reader, stage=case.stage)
    pipeline_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    verify_seconds = 0.0
    published = {}
    if case.stage == "bundle":
        before = time.perf_counter()
        bundle = BundleReader(Path(scratch) / "bundle")
        verifier = Oracle(definition, case.units)
        for _ in verifier.checked_records(bundle.iter_records()):
            pass
        verifier.finish(reader, stage="bundle")
        verify_seconds = time.perf_counter() - before
        published = file_sizes(Path(scratch) / "bundle")
        require({name: value["bytes"] for name, value in published.items()} ==
                {name: value["bytes"] for name, value in staged.items()},
                "published files differ from staged files")
    stage_times = {"synthetic_read_and_hash": reader.seconds,
                   "decode": totals["decode"] - reader.seconds,
                   "split": totals["split"] - totals["decode"] if case.stage != "decode" else None,
                   "lex_and_envelope": totals["lex"] - totals["split"] if case.stage in ("lex", "bundle") else None,
                   "write_validate_index": (elapsed - totals["lex"] - oracle.seconds
                                             - publication_seconds - observation_seconds)
                   if case.stage == "bundle" else None,
                   "publication": publication_seconds if case.stage == "bundle" else None,
                   "oracle": oracle.seconds, "observe_staging": observation_seconds,
                   "pipeline_wall": elapsed, "verify_bundle": verify_seconds}
    require(all(value is None or value >= 0 for value in stage_times.values()), "invalid stage timing attribution")
    return {"case_id": case.name, "parameters": asdict(case), "status": "ok", "validation": "passed",
            "input": {"bytes": reader.length, "characters": len(definition.text) * case.units,
                      "unit_characters": len(definition.parts[0][0]), "units": case.units,
                      "sha256": reader.digest.hexdigest(), "read_calls": reader.calls},
            "lexical_tokens": oracle.token_count if case.stage in ("lex", "bundle") else None,
            "fingerprints": {"lexical": definition.lexical.fingerprint, "split": definition.splitting.fingerprint},
            "seconds": stage_times, "mib_per_second": reader.length / MIB / elapsed,
            "peak_rss_kib": {"through_pipeline": pipeline_rss,
                             "with_verification": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},
            "files": published, "staging_files": staged,
            "output_bytes": sum(entry["bytes"] for entry in published.values()),
            "output_expansion": sum(entry["bytes"] for entry in published.values()) / reader.length}


def stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_worker(command, scratch, *, timeout_seconds, cwd=HERE):
    """Read a bounded row; callers remove scratch only after this worker stops."""
    stdout = Path(scratch) / "worker-stdout"
    stderr = Path(scratch) / "worker-stderr"
    with stdout.open("wb") as out, stderr.open("wb") as err:
        process = subprocess.Popen(command, cwd=cwd, stdout=out, stderr=err, start_new_session=True)
        try:
            code = process.wait(timeout_seconds)
        except subprocess.TimeoutExpired:
            return {"status": "supervisor-timeout", "timeout_seconds": timeout_seconds}
        finally:
            # Stop descendants even if the worker failed or returned normally
            # before them. Cleanup of scratch follows termination, never races it.
            stop_group(process)
    with stdout.open("rb") as handle:
        raw = handle.read(ROW_BYTES + 1)
    with stderr.open("rb") as handle:
        diagnostic = handle.read(4096).decode("utf-8", "replace")
    try:
        if len(raw) > ROW_BYTES:
            raise ValueError("worker result exceeds row bound")
        row = json.loads(raw)
        if not isinstance(row, dict) or row.get("status") not in ("ok", "validation-failed", "qualification-failed"):
            raise ValueError("worker did not return a measurement status")
        if code and row["status"] == "ok":
            raise ValueError("successful row from failed worker")
    except (ValueError, UnicodeError) as error:
        return {"status": "worker-failed", "exit_code": code, "diagnostic": (str(error) + ": " + diagnostic)[:4096]}
    return row


def measure_case(case, output, args):
    scratch = Path(tempfile.mkdtemp(prefix=f"tmp-{case.name}-", dir=output))
    command = [sys.executable, "-m", "benchmarks.streaming", "--worker", json.dumps(asdict(case)),
               "--scratch", str(scratch), "--chunk-bytes", str(args.chunk_bytes),
               "--max-rss-mib", str(args.max_rss_mib), "--max-file-mib", str(args.max_file_mib),
               "--address-space-mib", str(args.address_space_mib)]
    try:
        row = run_worker(command, scratch, timeout_seconds=args.timeout_seconds)
    finally:
        before = time.perf_counter()
        shutil.rmtree(scratch)
        cleanup_seconds = time.perf_counter() - before
    row["case_id"] = case.name
    row["cleanup_seconds"] = cleanup_seconds
    row["scratch_removed"] = not scratch.exists()
    return row


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def positive_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return number


def source_identity():
    digest = hashlib.sha256()
    paths = [Path(__file__), *sorted((HERE / "tokenizer").glob("*.py"))]
    for path in paths:
        digest.update(str(path.relative_to(HERE)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workloads", choices=WORKLOADS, nargs="+", default=list(WORKLOADS))
    parser.add_argument("--units", type=positive_int, nargs="+", default=[16, 64, 256])
    parser.add_argument("--stages", choices=STAGES, nargs="+", default=list(STAGES))
    parser.add_argument("--chunk-bytes", type=positive_int, default=65536)
    parser.add_argument("--timeout-seconds", type=positive_seconds, default=120.0)
    parser.add_argument("--max-rss-mib", type=positive_int, default=64)
    parser.add_argument("--max-file-mib", type=positive_int, default=1024)
    parser.add_argument("--address-space-mib", type=positive_int, default=512)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--scratch", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        resource.setrlimit(resource.RLIMIT_FSIZE, (args.max_file_mib * MIB,) * 2)
        resource.setrlimit(resource.RLIMIT_AS, (args.address_space_mib * MIB,) * 2)
        try:
            row = measure(Case(**json.loads(args.worker)), args.scratch, chunk_bytes=args.chunk_bytes)
        except ValidationFailure as error:
            row = {"status": "validation-failed", "diagnostic": str(error)}
        if row["status"] == "ok" and row["peak_rss_kib"]["with_verification"] > args.max_rss_mib * 1024:
            row["status"] = "qualification-failed"
            row["diagnostic"] = "peak resident memory exceeds the configured qualification envelope"
        row["source_sha256"] = source_identity()
        print(json.dumps(row, sort_keys=True))
        return 0 if row["status"] == "ok" else 1
    root = HERE / "output/streaming-benchmarks"
    root.mkdir(parents=True, exist_ok=True)
    if args.out is None:
        output = Path(tempfile.mkdtemp(prefix="run-", dir=root))
    else:
        output = args.out.resolve()
        output.mkdir(parents=True, exist_ok=False)
    identity = source_identity()
    meta = {"schema_version": 1, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "python": sys.version, "executable": sys.executable, "platform": tuple(os.uname()),
            "source_sha256": identity, "arguments": dict(vars(args), out=str(output)),
            "notes": ["Linux ru_maxrss in KiB, fresh workers; includes interpreter and imports.",
                      "Nested iterator timers include instrumentation overhead; oracle work is reported separately.",
                      "Synthetic input read time includes constructing bounded byte reads and hashing them.",
                      "Staging sizes are observed before atomic publication of append-only bundle files.",
                      "Allocated bytes count file blocks, excluding directory metadata; no fsync durability claim."]}
    (output / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    failures = 0
    try:
        with (output / "rows.jsonl").open("x", encoding="ascii") as sink:
            for workload, units, stage in itertools.product(args.workloads, args.units, args.stages):
                case = Case(workload, units, stage)
                row = measure_case(case, output, args)
                if row["status"] == "ok" and row["source_sha256"] != identity:
                    row["status"] = "validation-failed"
                    row["diagnostic"] = "source files changed during the benchmark"
                failures += row["status"] != "ok"
                sink.write(json.dumps(row, sort_keys=True) + "\n")
                sink.flush()
                print(f"{case.name}: {row['status']}; "
                      f"wall={row.get('seconds', {}).get('pipeline_wall', 0):.3f}s; "
                      f"RSS={row.get('peak_rss_kib', {}).get('with_verification', 0)} KiB", flush=True)
    except KeyboardInterrupt:
        print(f"Interrupted; completed rows retained in {output}", file=sys.stderr)
        return 130
    print(f"Results: {output}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
