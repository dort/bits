"""The production result-writing path, shared by the CLI and the benchmarks.

`ResultWriter` streams one `UnitResult` at a time into the staged result
files of the published-set contract: `results.jsonl` (one row per unit,
without graphs) and, in forest mode, `forests.jsonl` (one row per unit with
the lossless packed graph and its completion flag). It keeps only fixed-size
verdict counters, never the rows. `summary_payload` builds the `summary.json`
content from the runner's own configuration, so every writer of the set
reports the same engine identity and limits.
"""

import dataclasses
import hashlib
import json


class ResultWriter:
    """Stream per-unit results to staged files; hold only the counters."""

    def __init__(self, staging, *, forest):
        self.counts = {"accepted": 0, "rejected": 0, "incomplete": 0}
        self.incomplete_results = 0
        self._results = (staging / "results.jsonl").open("x", encoding="ascii")
        self._forests = ((staging / "forests.jsonl").open("x", encoding="ascii")
                         if forest else None)

    def write(self, unit):
        self.counts[unit.recognition] += 1
        # A requested forest or enumeration cut short by a limit makes the
        # command incomplete even when recognition accepted.
        if (unit.recognition == "incomplete"
                or unit.forest_complete is False
                or unit.enumeration_complete is False):
            self.incomplete_results += 1
        row = dataclasses.asdict(unit)
        graph = row.pop("graph")
        self._results.write(json.dumps(row, ensure_ascii=True,
                                       sort_keys=True) + "\n")
        if self._forests is not None:
            self._forests.write(json.dumps(
                {"namespace": unit.namespace, "source_id": unit.source_id,
                 "stream_id": unit.stream_id, "unit_index": unit.unit_index,
                 "graph_complete": unit.forest_complete, "graph": graph},
                ensure_ascii=True, sort_keys=True) + "\n")

    def close(self):
        self._results.close()
        if self._forests is not None:
            self._forests.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


def summary_payload(runner, writer, *, grammar_path, bundle_path):
    """The summary.json content for one completed run of `runner`."""
    return {
        "grammar": str(grammar_path),
        "grammar_id": runner.grammar_id,
        "grammar_fingerprint": runner.grammar.fingerprint,
        "engine": runner.engine,
        "engine_file": runner.engine_path.name,
        "engine_sha256": hashlib.sha256(
            runner.engine_path.read_bytes()).hexdigest(),
        "bundle": str(bundle_path),
        "units": sum(writer.counts.values()),
        "counts": writer.counts,
        "incomplete_results": writer.incomplete_results,
        "limits": {"initial_rounds": runner.initial_rounds,
                   "max_sweeps": runner.max_sweeps,
                   "timeout_seconds": runner.timeout_seconds,
                   **runner.read_limits,
                   "max_dump_bytes": runner.max_dump_bytes,
                   "max_process_bytes": runner.max_process_bytes,
                   "max_trees": runner.max_trees,
                   "max_depth": runner.max_depth},
    }
