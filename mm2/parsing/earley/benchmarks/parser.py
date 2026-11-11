"""Parser scale measurements: fresh-process workers under a supervisor.

The supervisor runs every registry case in its own worker process so peak
resident memory is comparable across cases, enforces one supervisor timeout
per case, removes the case's scratch directory whether the worker finished,
failed, or was killed, and streams one JSON row per case to `rows.jsonl`. A
worker builds one synthetic version-2 bundle from lazily generated units,
validates the whole archive, recognizes every unit through `grammarc.Runner`
with the real MORK binary, and aggregates per-unit results into fixed-size
accumulators; neither the input units nor the result rows are ever all
resident at once.

Memory accounting is explicit about its mechanisms: the worker reports its own
peak resident set (`RUSAGE_SELF`) separately from its MORK children's
(`RUSAGE_CHILDREN`), both in KiB as Linux reports `ru_maxrss`. Resident-set
peaks say nothing about MORK's ~10 GiB virtual address-space reservation,
which is address space, not resident memory. The control case times a minimal
one-fact MORK run; that is an estimate of process startup plus arena
reservation plus a trivial run, not a measurement of full-join inference.

Run from `earley/` with the sibling lexer importable:

    PYTHONPATH=../lexer ../lexer/.venv/bin/python -m benchmarks.parser
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import dataclasses
import statistics
import subprocess
import sys
import time

from tokenizer import (BundleReader, SourcePiece, load_spec, source_records,
                       write_bundle)
from grammarc import Runner, compile_grammar
from grammarc.runner import DEFAULT_MORK

from .cases import (CHAIN_DEPTH, GRAMMAR_IDS, GRAMMARS, LEXER_SPEC, PROJECT,
                    TEXTS, Case, registry)

STDERR_HEAD_BYTES = 4096
ROW_LINE_BYTES = 1 << 22
DEFAULT_SUPERVISOR_TIMEOUT = 900.0
CONTROL_RUNS = 5

# Incomplete-outcome classification: each label is the limit named in the
# runner's reason string, recognized by the parameter it embeds.
REASON_LABELS = (("wall-time", "timeout_seconds"), ("sweeps", "max_sweeps"),
                 ("tokens", "max_tokens"), ("chars", "max_chars"),
                 ("payload", "max_payload_bytes"), ("dump", "max_dump_bytes"),
                 ("memory", "max_process_bytes"))


def classify_reason(reason):
    """The exhausted limit named in a runner reason, or None/'other'."""
    if reason is None:
        return None
    for label, token in REASON_LABELS:
        if token in reason:
            return label
    return "other"


def build_bundle(case, scratch):
    """Write one generated-identity bundle of `unit_count` lazy units."""
    spec = load_spec(LEXER_SPEC)
    text = TEXTS[case.text](case.tokens_per_unit)

    def pieces():
        for index in range(case.unit_count):
            following = text[0] if index + 1 < case.unit_count else ""
            yield SourcePiece(text, following=following)

    path = scratch / "bundle"
    write_bundle(source_records(pieces(), spec, namespace="bench",
                                source_id="case",
                                max_units=max(case.unit_count, 1)), path)
    return path, spec.fingerprint, len(text)


def run_case(case, scratch):
    """Build, validate, and parse one case; return its measurement row.

    Per-unit results are folded into fixed-size accumulators as the runner
    yields them, so the row's size does not grow with the unit count.
    """
    grammar = compile_grammar(GRAMMARS[case.grammar]())
    grammar_id = GRAMMAR_IDS[case.grammar]
    started = time.perf_counter()
    bundle, lexer_fingerprint, unit_chars = build_bundle(case, scratch)
    built = time.perf_counter()
    reader = BundleReader(bundle)
    for _ in reader.iter_records():
        pass
    validated = time.perf_counter()
    runner = Runner(grammar, grammar_id, engine=case.engine,
                    max_trees=case.max_trees, max_depth=case.max_depth,
                    work_dir=scratch / "work", **case.runner)
    verdicts = {"accepted": 0, "rejected": 0, "incomplete": 0}
    reasons = {}
    units = closure_units = forest_units = 0
    enumeration = {"complete": 0, "incomplete": 0}
    engine_runs = budget_max = trees_listed = 0
    items_max = nodes_max = parts_max = 0
    unit_seconds_max = 0.0
    for unit in runner.run_bundle(bundle, preflight=False):
        units += 1
        verdicts[unit.recognition] += 1
        closure_units += unit.closure_complete
        forest_units += unit.forest_complete is True
        if unit.enumeration_complete is not None:
            enumeration["complete" if unit.enumeration_complete
                        else "incomplete"] += 1
        label = classify_reason(unit.reason)
        if label is not None:
            reasons[label] = reasons.get(label, 0) + 1
        engine_runs += len(unit.budgets)
        budget_max = max(budget_max, *unit.budgets, 0) if unit.budgets else budget_max
        trees_listed += len(unit.trees)
        items_max = max(items_max, unit.item_count)
        nodes_max = max(nodes_max, unit.node_count)
        parts_max = max(parts_max, unit.part_count)
        unit_seconds_max = max(unit_seconds_max, unit.elapsed_seconds)
    parsed = time.perf_counter()
    work_dir = scratch / "work"
    leftovers = [entry.name for entry in work_dir.iterdir()] if work_dir.exists() else []
    return {
        "case_id": case.case_id, "dimension": case.dimension,
        "parameters": {
            "grammar": case.grammar, "grammar_id": grammar_id,
            "text": case.text, "tokens_per_unit": case.tokens_per_unit,
            "unit_count": case.unit_count, "engine": case.engine,
            "max_trees": case.max_trees, "max_depth": case.max_depth,
            "runner_overrides": dict(case.runner),
            "chain_depth": CHAIN_DEPTH if case.grammar == "chain" else None},
        "provenance": {
            "grammar_fingerprint": grammar.fingerprint,
            "lexer_fingerprint": lexer_fingerprint,
            "limits": {"initial_rounds": runner.initial_rounds,
                       "max_sweeps": runner.max_sweeps,
                       "timeout_seconds": runner.timeout_seconds,
                       **runner.read_limits,
                       "max_dump_bytes": runner.max_dump_bytes,
                       "max_process_bytes": runner.max_process_bytes}},
        "units": units, "unit_chars": unit_chars,
        "verdicts": verdicts, "expected_recognition": case.expect,
        "closure_complete_units": closure_units,
        "forest_complete_units": forest_units if case.engine == "forest" else None,
        "enumeration": enumeration if case.max_trees is not None else None,
        "incomplete_reasons": reasons,
        "engine_runs": engine_runs, "budget_max": budget_max,
        "item_count_max": items_max, "node_count_max": nodes_max,
        "part_count_max": parts_max, "trees_listed": trees_listed,
        "seconds": {"build_bundle": round(built - started, 6),
                    "validate_archive": round(validated - built, 6),
                    "parse": round(parsed - validated, 6),
                    "unit_max": round(unit_seconds_max, 6)},
        "bytes": {"bundle": sum(entry.stat().st_size
                                for entry in bundle.iterdir()),
                  "peak_engine_input": runner.peak_input_bytes,
                  "peak_engine_dump": runner.peak_dump_bytes},
        "work_dir_clean": not leftovers,
    }


def control_row(scratch):
    """Time a minimal one-fact MORK run; an overhead estimate, not inference."""
    input_path = scratch / "control.mm2"
    input_path.write_text("(noop)\n")
    seconds = []
    for index in range(CONTROL_RUNS):
        dump = scratch / f"dump{index}.mm2"
        started = time.perf_counter()
        subprocess.run([DEFAULT_MORK, "run", str(input_path), str(dump)],
                       check=True, capture_output=True, timeout=60)
        seconds.append(time.perf_counter() - started)
    return {
        "case_id": "control-mork", "dimension": "control",
        "runs": CONTROL_RUNS,
        "startup_estimate_seconds": {"min": round(min(seconds), 6),
                                     "mean": round(statistics.mean(seconds), 6)},
        "note": ("estimate from a one-fact space: process startup, arena "
                 "reservation, and a trivial run; not a measurement of "
                 "full-join inference time"),
    }


def worker_main(case_json, scratch):
    case = Case(**json.loads(case_json))
    scratch = Path(scratch)
    row = (control_row(scratch) if case.dimension == "control"
           else run_case(case, scratch))
    row["peak_rss_kib"] = {
        "worker": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "mork_children": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss}
    print(json.dumps(row, ensure_ascii=True, sort_keys=True))


def run_worker(command, timeout_seconds, streams_dir, *, cwd=None, env=None):
    """Run one worker under the supervisor timeout; classify its outcome.

    The worker starts its own session so a timeout kill reaches its whole
    process group, MORK children included. Its streams go to files and are
    read back bounded.
    """
    streams_dir = Path(streams_dir)
    stdout_path = streams_dir / "worker-stdout"
    stderr_path = streams_dir / "worker-stderr"
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=out,
                                   stderr=err, start_new_session=True)
        try:
            exit_code = process.wait(timeout_seconds)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            return {"status": "supervisor-timeout",
                    "timeout_seconds": timeout_seconds}
    with stderr_path.open("r", encoding="utf-8", errors="replace") as captured:
        stderr_head = captured.read(STDERR_HEAD_BYTES).strip()
    if exit_code != 0:
        return {"status": "worker-failed", "exit_code": exit_code,
                "stderr_head": stderr_head}
    with stdout_path.open("r", encoding="utf-8", errors="replace") as captured:
        line = captured.readline(ROW_LINE_BYTES)
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return {"status": "worker-failed", "exit_code": exit_code,
                "stderr_head": "worker produced no parseable result row; "
                               + stderr_head}
    return {"status": "ok", "row": row}


def measure_case(case, out_dir, timeout_seconds):
    """One case in a fresh worker; always removes the case scratch directory."""
    scratch = Path(out_dir) / f"tmp-{case.case_id}"
    scratch.mkdir()
    env = dict(os.environ)
    lexer = str(PROJECT.parent / "lexer")
    env["PYTHONPATH"] = lexer + (os.pathsep + env["PYTHONPATH"]
                                 if env.get("PYTHONPATH") else "")
    command = [sys.executable, "-m", "benchmarks.parser",
               "--worker", json.dumps(dataclasses.asdict(case)),
               "--scratch", str(scratch)]
    try:
        return run_worker(command, timeout_seconds, scratch,
                          cwd=str(PROJECT), env=env)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def write_meta(out_dir, args):
    mork = Path(DEFAULT_MORK)
    with mork.open("rb") as binary:
        digest = hashlib.file_digest(binary, "sha256").hexdigest()
    uname = os.uname()
    meta = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "machine": {"sysname": uname.sysname, "release": uname.release,
                    "machine": uname.machine, "nodename": uname.nodename},
        "python": sys.version, "implementation": sys.implementation.name,
        "mork": str(mork), "mork_sha256": digest,
        "lexer_spec": str(LEXER_SPEC),
        "registry": {"units": args.units, "expr_tokens": args.expr_tokens,
                     "ints_tokens": args.ints_tokens,
                     "chain_tokens": args.chain_tokens,
                     "concat_tokens": args.concat_tokens, "only": args.only},
        "supervisor_timeout_seconds": args.supervisor_timeout,
    }
    (Path(out_dir) / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="ascii")


def engines_agreement(engine_rows):
    """Recognition must agree across engines on completed cases."""
    completed = {case_id: tuple(sorted(row["verdicts"].items()))
                 for case_id, row in engine_rows.items()
                 if row["verdicts"]["incomplete"] == 0}
    return {"case_id": "engines-agreement", "dimension": "engines",
            "status": "ok", "compared": sorted(completed),
            "verdicts_agree": len(set(completed.values())) <= 1 and
                              len(completed) == len(engine_rows)}


def supervise(args):
    cases = registry(units=tuple(args.units),
                     expr_tokens=tuple(args.expr_tokens),
                     ints_tokens=tuple(args.ints_tokens),
                     chain_tokens=tuple(args.chain_tokens),
                     concat_tokens=tuple(args.concat_tokens))
    if args.only:
        cases = [case for case in cases if args.only in case.case_id]
    if args.list:
        for case in cases:
            print(case.case_id)
        return 0
    out_dir = Path(args.out) if args.out else (
        PROJECT / "output/benchmarks" / time.strftime("run-%Y%m%d-%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=False)
    write_meta(out_dir, args)
    failures = 0
    engine_rows = {}
    with (out_dir / "rows.jsonl").open("x", encoding="ascii") as sink:

        def emit(line):
            sink.write(json.dumps(line, ensure_ascii=True, sort_keys=True) + "\n")
            sink.flush()

        for case in cases:
            outcome = measure_case(case, out_dir, args.supervisor_timeout)
            if outcome["status"] != "ok":
                failures += 1
                emit({"case_id": case.case_id, "dimension": case.dimension,
                      **outcome})
                print(f"{case.case_id}: {outcome['status']}")
                continue
            row = outcome["row"]
            emit({"status": "ok", **row})
            if case.dimension == "control":
                print(f"{case.case_id}: startup estimate "
                      f"{row['startup_estimate_seconds']['min']}s min over "
                      f"{row['runs']} runs")
                continue
            if case.dimension == "engines":
                engine_rows[case.case_id] = row
            verdicts = row["verdicts"]
            note = ("" if case.expect is None
                    or verdicts.get(case.expect) == row["units"]
                    else "  [differs from the expected recognition]")
            print(f"{case.case_id}: {row['units']} units "
                  f"{verdicts['accepted']}/{verdicts['rejected']}/"
                  f"{verdicts['incomplete']} a/r/i, "
                  f"parse {row['seconds']['parse']}s, "
                  f"rss {row['peak_rss_kib']['worker']}/"
                  f"{row['peak_rss_kib']['mork_children']} KiB "
                  f"worker/mork{note}")
        if engine_rows:
            agreement = engines_agreement(engine_rows)
            emit(agreement)
            print(f"engines-agreement: verdicts_agree="
                  f"{agreement['verdicts_agree']}")
    print(f"rows: {out_dir / 'rows.jsonl'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="benchmarks.parser",
        description="Reproducible parser scale measurements with real MORK.")
    parser.add_argument("--worker", help="internal: one case as JSON")
    parser.add_argument("--scratch", help="internal: the worker's scratch directory")
    parser.add_argument("--units", type=int, nargs="+", default=[4, 16, 64])
    parser.add_argument("--expr-tokens", type=int, nargs="+", default=[7, 15, 31])
    parser.add_argument("--ints-tokens", type=int, nargs="+", default=[7, 15, 31])
    parser.add_argument("--chain-tokens", type=int, nargs="+", default=[1, 7, 15])
    parser.add_argument("--concat-tokens", type=int, nargs="+", default=[3, 8])
    parser.add_argument("--only", help="run only case IDs containing this text")
    parser.add_argument("--out", help="run directory (default: a fresh "
                                      "output/benchmarks/run-* directory)")
    parser.add_argument("--supervisor-timeout", type=float,
                        default=DEFAULT_SUPERVISOR_TIMEOUT,
                        help="per-case ceiling on one worker process")
    parser.add_argument("--list", action="store_true",
                        help="print the selected case IDs and exit")
    args = parser.parse_args(argv)
    if args.worker:
        worker_main(args.worker, args.scratch)
        return 0
    return supervise(args)


if __name__ == "__main__":
    sys.exit(main())
