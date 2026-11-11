"""Per-unit MORK orchestration over version-2 token bundles.

For each selected unit the runner reads and validates the unit's stream
through `tokenizer.BundleReader`, checks the grammar's terminals against the
stream's declared kind catalog, and runs one engine in a fresh MORK process
with the grammar facts, the unit's lexical facts, one demand fact, and a
generated round table. The sweep budget doubles between reruns until the
canonical semantic projection stops changing (closure) or a limit intervenes.

Outcomes follow the plan's contract: `accepted` needs only a sound acceptance
fact; `rejected` additionally requires established closure; everything cut
short by a round, wall-time, dump-size, memory, or token limit is
`incomplete` with the exhausted limit named. Runtime failures and malformed
bundles raise; they are diagnostics, not grammatical rejections.

Resource limits are enforced, not inspected after the fact. One absolute
deadline per unit covers every engine run and all Python processing after it
(dump parsing, projection, forest construction, tree enumeration); expiry
preserves sound acceptance and any previously established closure but marks
the unfinished output incomplete. The engine process runs under RLIMIT_FSIZE
at `max_dump_bytes`, so the OS stops an oversized dump (and the captured
diagnostic streams) while it is being written, and under RLIMIT_AS at
`max_process_bytes`. A limit outcome is reported only on evidence of that
particular exhaustion — the runner's own timeout, the file-size signal, or an
allocation-failure abort — and every other nonzero exit is a runtime
diagnostic whether or not limits were installed.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
import resource
import signal
import subprocess
import tempfile
import time

from tokenizer import BundleReader
from tokenizer.model import (ConfigurationError, DEFAULT_MAX_CHARS, LimitError,
                             require_python314, validate_limit)

from .facts import FOREST_HEADS, RECOGNITION_HEADS, parse_facts, projection, select
from .forest import Forest
from .serialize import MAX_ROUNDS, demand_fact, grammar_facts, round_table_facts

PROJECT = Path(__file__).resolve().parents[1]
ENGINES = {"recognition": PROJECT / "earley.mm2",
           "forest": PROJECT / "earley_forest.mm2"}
DEFAULT_MORK = os.environ.get("MORK", "/home/ni/repos/m/MORK/target/release/mork")
DEFAULT_MAX_TOKENS = 512          # parser token limit, below the reader default
DEFAULT_MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_DUMP_BYTES = 64 * 1024 * 1024
# RLIMIT_AS bounds virtual address space. The release MORK binary reserves
# just under 10 GiB of it at startup (a 4 GiB arena allocation fails under
# any smaller ceiling), measured 2026-11-10 on this machine; 16 GiB leaves
# that fixed reservation room while still bounding runaway growth.
DEFAULT_MAX_PROCESS_BYTES = 16 * 1024 ** 3
DEFAULT_INITIAL_ROUNDS = 16
DEFAULT_MAX_SWEEPS = 512          # one run's round table is capped at MAX_ROUNDS
DEFAULT_TIMEOUT_SECONDS = 30.0
STDERR_DIAGNOSTIC_BYTES = 4096    # bounded prefix of the captured stream


class DeadlineExceeded(Exception):
    """The per-unit wall-time budget ran out during a Python stage."""


class Deadline:
    """One absolute per-unit deadline shared by engine runs and Python stages."""

    def __init__(self, seconds, start=None):
        self.seconds = seconds
        self._at = (time.monotonic() if start is None else start) + seconds

    def remaining(self):
        return self._at - time.monotonic()

    def expired(self):
        return time.monotonic() >= self._at

    def check(self):
        if self.expired():
            raise DeadlineExceeded(f"wall-time limit timeout_seconds={self.seconds}")


@dataclass(frozen=True)
class UnitResult:
    namespace: str
    source_id: str
    stream_id: str
    unit_index: int
    recognition: str                  # accepted | rejected | incomplete
    closure_complete: bool
    forest_complete: bool | None      # None: no forest was requested
    enumeration_complete: bool | None = None  # None: no enumeration requested
    reason: str | None = None          # the exhausted limit, when any output is incomplete
    budgets: tuple = field(default=())  # sweep budgets that ran to their marker
    item_count: int = 0
    node_count: int = 0
    part_count: int = 0
    elapsed_seconds: float = 0.0
    trees: tuple = ()                  # bounded enumeration output, when requested
    graph: dict | None = None          # the packed alternative set, in forest mode


class Runner:
    def __init__(self, grammar, grammar_id, *, engine="recognition",
                 mork=DEFAULT_MORK, initial_rounds=DEFAULT_INITIAL_ROUNDS,
                 max_sweeps=DEFAULT_MAX_SWEEPS,
                 timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
                 max_tokens=DEFAULT_MAX_TOKENS, max_chars=DEFAULT_MAX_CHARS,
                 max_payload_bytes=DEFAULT_MAX_PAYLOAD_BYTES,
                 max_dump_bytes=DEFAULT_MAX_DUMP_BYTES,
                 max_process_bytes=DEFAULT_MAX_PROCESS_BYTES,
                 max_trees=None, max_depth=None, work_dir=None):
        require_python314()
        if engine not in ENGINES:
            raise ConfigurationError(f"unknown engine {engine!r}; expected one of "
                                     + ", ".join(sorted(ENGINES)), field="engine")
        if (max_trees is None) != (max_depth is None):
            raise ConfigurationError("max_trees and max_depth are requested together",
                                     field="max_trees")
        if max_trees is not None:
            if engine != "forest":
                raise ConfigurationError("tree enumeration requires the forest engine",
                                         field="max_trees")
            for label, value in (("max_trees", max_trees), ("max_depth", max_depth)):
                if type(value) is not int or value < 1:
                    raise ConfigurationError("must be a positive integer", field=label)
        for label, value in (("initial_rounds", initial_rounds), ("max_sweeps", max_sweeps)):
            validate_limit(value, label)
        if not 1 <= initial_rounds <= max_sweeps <= MAX_ROUNDS:
            raise ConfigurationError(
                f"need 1 <= initial_rounds <= max_sweeps <= {MAX_ROUNDS} "
                "(the three-digit round-symbol scheme bounds one run's table)",
                field="max_sweeps")
        validate_limit(max_dump_bytes, "max_dump_bytes")
        if max_process_bytes is not None:
            validate_limit(max_process_bytes, "max_process_bytes")
        if not (isinstance(timeout_seconds, (int, float))
                and not isinstance(timeout_seconds, bool) and timeout_seconds > 0):
            raise ConfigurationError("must be a positive number", field="timeout_seconds")
        self.grammar = grammar
        self.grammar_id = grammar_id
        self.engine = engine
        self.engine_path = ENGINES[engine]
        self.heads = FOREST_HEADS if engine == "forest" else RECOGNITION_HEADS
        self.grammar_source = "".join(grammar_facts(grammar, grammar_id))
        self.mork = str(mork)
        self.initial_rounds = initial_rounds
        self.max_sweeps = max_sweeps
        self.timeout_seconds = float(timeout_seconds)
        self.read_limits = dict(max_tokens=max_tokens, max_chars=max_chars,
                                max_payload_bytes=max_payload_bytes)
        self.max_dump_bytes = max_dump_bytes
        self.max_process_bytes = max_process_bytes
        self.max_trees = max_trees
        self.max_depth = max_depth
        self.work_dir = Path(work_dir) if work_dir is not None else PROJECT / "output"
        # Largest engine input and dump files staged by any run of this
        # runner, in bytes. The staging directory is deleted per run, so
        # these counters are the only record of its disk footprint.
        self.peak_input_bytes = 0
        self.peak_dump_bytes = 0

    def run_bundle(self, bundle_path, *, preflight=True):
        """Yield one UnitResult per unit, in index order.

        With `preflight` (the default), the whole archive is first validated
        by exhausting `iter_records()` — gaps and dropped empties included —
        because reading selected streams alone is a deliberately narrower
        check and a completed whole-source claim needs the full validation.
        """
        reader = BundleReader(bundle_path)
        if preflight:
            for _ in reader.iter_records():
                pass
        for entry in reader.iter_entries():
            yield self.run_unit(reader, entry)

    def run_unit(self, reader, entry):
        started = time.monotonic()
        deadline = Deadline(self.timeout_seconds, start=started)
        wall_reason = f"wall-time limit timeout_seconds={self.timeout_seconds}"
        key = (entry["namespace"], entry["stream_id"], self.grammar_id)

        def result(recognition, closure, *, reason=None, budgets=(), facts=None):
            graph = None
            forest_done = None
            enumeration = None
            trees = ()
            if self.engine == "forest":
                forest_done = False
                if self.max_trees is not None:
                    # Enumeration is complete only when the graph itself is:
                    # an unconverged forest could be missing alternatives.
                    enumeration = False
                if facts is not None:
                    try:
                        deadline.check()  # no forest work on an exhausted deadline
                        forest = Forest(self.grammar, facts, *key, deadline=deadline)
                        graph = forest.graph()
                        if deadline.expired():
                            # The final sorts in graph() follow its last
                            # checkpoint; a completion claim must still be
                            # inside the budget, and no enumeration starts
                            # past it. The fully built graph is kept.
                            raise DeadlineExceeded(wall_reason)
                        forest_done = closure
                        if self.max_trees is not None:
                            listed, exhausted = forest.enumerate(self.max_trees,
                                                                 self.max_depth)
                            trees = tuple(listed)
                            enumeration = closure and exhausted
                            if not exhausted and deadline.expired():
                                reason = reason or wall_reason
                    except DeadlineExceeded:
                        forest_done = False
                        reason = reason or wall_reason
            return UnitResult(
                entry["namespace"], entry["source_id"], entry["stream_id"],
                entry["unit_index"], recognition, closure, forest_done,
                enumeration_complete=enumeration,
                reason=reason, budgets=tuple(budgets),
                item_count=len(select(facts or [], "item", *key)),
                node_count=len(select(facts or [], "node", *key)),
                part_count=len(select(facts or [], "part", *key)),
                elapsed_seconds=time.monotonic() - started,
                trees=trees, graph=graph)

        try:
            stream = reader.read_stream(entry, **self.read_limits)
        except LimitError as error:
            return result("incomplete", False, reason=str(error))
        self.grammar.check_terminals(stream.start.kinds)
        demand = demand_fact(entry["namespace"], entry["stream_id"], self.grammar_id)
        budgets = []
        previous = facts = None
        budget = self.initial_rounds
        closure = False
        reason = None
        while True:
            if budget > self.max_sweeps:
                reason = f"sweep budget limit max_sweeps={self.max_sweeps}"
                break
            if deadline.expired():
                reason = wall_reason
                break
            try:
                run, failure = self._execute(stream, demand, budget, deadline)
                if failure is not None:
                    reason = failure
                    break
                facts = run
                budgets.append(budget)
                current = projection(facts, *key, self.heads, deadline=deadline)
            except DeadlineExceeded:
                reason = wall_reason
                break
            if deadline.expired():
                # The projection's final assembly may have crossed the
                # deadline after its last checkpoint; closure is only
                # declared when established inside the budget.
                reason = wall_reason
                break
            if previous is not None and current == previous:
                closure = True
                break
            previous = current
            budget *= 2
        accepted = bool(facts) and bool(
            select(facts, "accepted", *key))
        if accepted:
            recognition = "accepted"
        elif closure:
            recognition = "rejected"
        else:
            recognition = "incomplete"
        return result(recognition, closure,
                      reason=None if closure else reason,
                      budgets=budgets, facts=facts)

    def _execute(self, stream, demand, budget, deadline):
        """One fresh-space MORK run; returns (facts, None) or (None, reason)."""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        dump_ceiling = self.max_dump_bytes
        memory_ceiling = self.max_process_bytes

        def preexec():
            # The OS stops the engine at the ceilings while it runs:
            # RLIMIT_FSIZE bounds every file it writes (the dump and the
            # captured streams), RLIMIT_AS bounds its address space.
            resource.setrlimit(resource.RLIMIT_FSIZE, (dump_ceiling, dump_ceiling))
            if memory_ceiling is not None:
                resource.setrlimit(resource.RLIMIT_AS, (memory_ceiling, memory_ceiling))

        with tempfile.TemporaryDirectory(dir=self.work_dir) as directory:
            input_path = Path(directory) / "input.mm2"
            dump_path = Path(directory) / "dump.mm2"
            stderr_path = Path(directory) / "stderr"
            stdout_path = Path(directory) / "stdout"
            text = self.grammar_source + demand + round_table_facts(budget)
            input_path.write_bytes(text.encode("ascii") + stream.mm2)
            self.peak_input_bytes = max(self.peak_input_bytes,
                                        input_path.stat().st_size)
            command = [self.mork, "run", str(input_path), str(dump_path)]
            command += ["--aux-path", str(self.engine_path)]
            try:
                with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
                    completed = subprocess.run(command, stdout=out, stderr=err,
                                               timeout=deadline.remaining(),
                                               preexec_fn=preexec)
            except subprocess.TimeoutExpired:
                return None, (f"wall-time limit timeout_seconds="
                              f"{self.timeout_seconds} during {budget} sweeps")
            if dump_path.exists():
                self.peak_dump_bytes = max(self.peak_dump_bytes,
                                           dump_path.stat().st_size)
            with stderr_path.open("rb") as captured:
                stderr_head = captured.read(STDERR_DIAGNOSTIC_BYTES)
            stderr_head = stderr_head.decode("utf-8", "replace").strip()
            if completed.returncode != 0:
                # RLIMIT_FSIZE stopped the engine at the output ceiling only
                # when there is evidence of an attempted oversized write: the
                # limit signal (the process died by it), or a write-failure
                # diagnostic with a constrained file sitting at the ceiling
                # (a process that handles or ignores the signal fails on the
                # truncated write instead). A file merely at the ceiling is
                # not that evidence — a writer may fill it exactly and fail
                # for an unrelated reason. A dump from a limit-stopped run
                # can still contain the budget marker, so it is never parsed.
                at_ceiling = [name for name, path in
                              (("dump", dump_path), ("stdout", stdout_path),
                               ("stderr", stderr_path))
                              if path.exists() and path.stat().st_size >= dump_ceiling]
                write_failed = ("File too large" in stderr_head
                                or "[Errno 27]" in stderr_head)
                if (completed.returncode == -signal.SIGXFSZ
                        or (write_failed and at_ceiling)):
                    streams = ", ".join(at_ceiling) or "output"
                    return None, (f"output-size limit max_dump_bytes="
                                  f"{self.max_dump_bytes} enforced on {streams} "
                                  f"during {budget} sweeps")
                if (memory_ceiling is not None
                        and completed.returncode == -signal.SIGABRT
                        and "memory allocation" in stderr_head):
                    return None, (f"memory limit max_process_bytes={memory_ceiling} "
                                  f"(allocation failed during {budget} sweeps)")
                truncated = (" (stderr truncated at the max_dump_bytes ceiling)"
                             if "stderr" in at_ceiling else "")
                raise RuntimeError(f"mork failed (exit {completed.returncode})"
                                   f"{truncated}: {stderr_head}")
            if dump_path.stat().st_size > self.max_dump_bytes:
                return None, (f"dump-size limit max_dump_bytes={self.max_dump_bytes} "
                              f"at {budget} sweeps")
            facts = parse_facts(dump_path.read_text(), deadline=deadline)
        if ("swept", f"b{budget:03d}") not in facts:
            return None, f"scheduled sweeps did not finish at budget {budget}"
        if select(facts, "exec"):
            return None, f"pending engine executions remain at budget {budget}"
        return facts, None
