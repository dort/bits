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
"""

from dataclasses import dataclass, field
from pathlib import Path
import resource
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
DEFAULT_MORK = "/home/ni/repos/m/MORK/target/release/mork"
DEFAULT_MAX_TOKENS = 512          # parser token limit, below the reader default
DEFAULT_MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_DUMP_BYTES = 64 * 1024 * 1024
DEFAULT_INITIAL_ROUNDS = 16
DEFAULT_MAX_SWEEPS = 512          # one run's round table is capped at MAX_ROUNDS
DEFAULT_TIMEOUT_SECONDS = 30.0


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
    reason: str | None = None          # the exhausted limit, for incomplete units
    budgets: tuple = field(default=())  # sweep budgets that ran to their marker
    item_count: int = 0
    node_count: int = 0
    part_count: int = 0
    elapsed_seconds: float = 0.0
    trees: tuple = ()                  # bounded enumeration output, when requested


class Runner:
    def __init__(self, grammar, grammar_id, *, engine="recognition",
                 mork=DEFAULT_MORK, initial_rounds=DEFAULT_INITIAL_ROUNDS,
                 max_sweeps=DEFAULT_MAX_SWEEPS,
                 timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
                 max_tokens=DEFAULT_MAX_TOKENS, max_chars=DEFAULT_MAX_CHARS,
                 max_payload_bytes=DEFAULT_MAX_PAYLOAD_BYTES,
                 max_dump_bytes=DEFAULT_MAX_DUMP_BYTES,
                 max_process_bytes=None, max_trees=None, max_depth=None,
                 work_dir=None):
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

        def result(recognition, closure, *, reason=None, budgets=(), facts=None):
            key = (entry["namespace"], entry["stream_id"], self.grammar_id)
            enumeration = None
            trees = ()
            if self.max_trees is not None:
                # Enumeration is complete only when the graph itself is: an
                # unconverged forest could be missing alternatives.
                enumeration = False
                if facts is not None:
                    forest = Forest(self.grammar, facts, *key)
                    listed, exhausted = forest.enumerate(self.max_trees, self.max_depth)
                    trees = tuple(listed)
                    enumeration = closure and exhausted
            return UnitResult(
                entry["namespace"], entry["source_id"], entry["stream_id"],
                entry["unit_index"], recognition, closure,
                closure if self.engine == "forest" else None,
                enumeration_complete=enumeration,
                reason=reason, budgets=tuple(budgets),
                item_count=len(select(facts or [], "item", *key)),
                node_count=len(select(facts or [], "node", *key)),
                part_count=len(select(facts or [], "part", *key)),
                elapsed_seconds=time.monotonic() - started,
                trees=trees)

        try:
            stream = reader.read_stream(entry, **self.read_limits)
        except LimitError as error:
            return result("incomplete", False, reason=str(error))
        self.grammar.check_terminals(stream.start.kinds)
        demand = demand_fact(entry["namespace"], entry["stream_id"], self.grammar_id)
        deadline = started + self.timeout_seconds
        key = (entry["namespace"], entry["stream_id"], self.grammar_id)
        budgets = []
        previous = facts = None
        budget = self.initial_rounds
        closure = False
        reason = None
        while True:
            if budget > self.max_sweeps:
                reason = f"sweep budget limit max_sweeps={self.max_sweeps}"
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                reason = f"wall-time limit timeout_seconds={self.timeout_seconds}"
                break
            run, failure = self._execute(stream, demand, budget, remaining)
            if failure is not None:
                reason = failure
                break
            facts = run
            budgets.append(budget)
            current = projection(facts, *key, self.heads)
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

    def _execute(self, stream, demand, budget, remaining_seconds):
        """One fresh-space MORK run; returns (facts, None) or (None, reason)."""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        preexec = None
        if self.max_process_bytes is not None:
            ceiling = self.max_process_bytes

            def preexec():
                resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
        with tempfile.TemporaryDirectory(dir=self.work_dir) as directory:
            input_path = Path(directory) / "input.mm2"
            dump_path = Path(directory) / "dump.mm2"
            text = self.grammar_source + demand + round_table_facts(budget)
            input_path.write_bytes(text.encode("ascii") + stream.mm2)
            command = [self.mork, "run", str(input_path), str(dump_path)]
            command += ["--aux-path", str(self.engine_path)]
            try:
                completed = subprocess.run(command, capture_output=True, text=True,
                                           timeout=remaining_seconds,
                                           preexec_fn=preexec)
            except subprocess.TimeoutExpired:
                return None, (f"wall-time limit timeout_seconds="
                              f"{self.timeout_seconds} during {budget} sweeps")
            if completed.returncode != 0:
                if self.max_process_bytes is not None:
                    return None, (f"engine process failed under max_process_bytes="
                                  f"{self.max_process_bytes} (exit {completed.returncode})")
                raise RuntimeError(f"mork failed (exit {completed.returncode}): "
                                   f"{completed.stderr.strip()}")
            if dump_path.stat().st_size > self.max_dump_bytes:
                return None, (f"dump-size limit max_dump_bytes={self.max_dump_bytes} "
                              f"at {budget} sweeps")
            facts = parse_facts(dump_path.read_text())
        if ("swept", f"b{budget:03d}") not in facts:
            return None, f"scheduled sweeps did not finish at budget {budget}"
        if select(facts, "exec"):
            return None, f"pending engine executions remain at budget {budget}"
        return facts, None
