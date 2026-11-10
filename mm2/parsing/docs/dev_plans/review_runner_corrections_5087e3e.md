# Review of Claude's runner and forest corrections

Reviewed 2026-11-10 against commit `5087e3e` by Codex. This follows the
[review of the initial completion](review_runner_and_forest_5165d33.md).

The corrections address the main missing functionality: forest mode publishes
its packed graph, the CLI stages results through the shared publication helper,
the child process has enforced resource ceilings, and traversal handles deep
cycles without Python recursion failures. Three issues remain in the deadline
and diagnostic contracts. Keep those portions of milestones 4–5 open.

## Verification

- All **53 Earley tests** passed against the real local MORK binary.
- All **83 lexer tests** passed, including the migrated publication-helper tests.
- A real CLI run on a one-token bundle with productions `expr -> expr` and
  `expr -> INT`, `max_trees=1`, and `max_depth=10000` published a tree containing
  10,000 nonterminal nodes. It reported complete closure and forest, incomplete
  enumeration, and exit status 3. No staging directory remained.
- Targeted probes used actual version-2 bundles and cached actual MORK facts
  for the single-production grammar `expr -> INT`. Controlled clock expiry and
  a delayed tree copy isolate deadline handling; these are not MORK performance
  measurements. Small stand-in executables isolate subprocess failure handling.
- Reproductions and results are retained locally in ignored
  `lexer/output/claude-corrections-review-5087e3e/{probe.py,report.json}`.
  Essential inputs and outcomes appear below so the review does not depend on
  those generated files.

## Remaining corrections

### 1. P1 — check deadlines during final work and before declaring completion

Locations: [forest.py](../../earley/grammarc/forest.py), `_copy_tree()` lines
30–50, `graph()` lines 88–104, and `enumerate()` lines 203–207;
[runner.py](../../earley/grammarc/runner.py), lines 195–205.

The shared absolute deadline is a useful correction, but several final stages
can cross it without another check. `graph()` sorts its nodes and parts after
its last checkpoint. `_copy_tree()` traverses a complete tree without consulting
the deadline. After copying the last tree, enumeration can exhaust its choice
stack and return `complete=True` without testing time again. The runner accepts
both completion claims; it checks expiry after enumeration only when the
enumerator already returned incomplete.

**Reproductions:** expire a controlled deadline during the final graph sort.
The runner returns `forest_complete=true` and `reason=null` while the deadline
is expired. Expire it during the last tree copy and the runner also returns
`enumeration_complete=true`. With a real 100 ms deadline and a controlled
300 ms delay inside that last copy, the result took approximately 300.5 ms and
still reported complete enumeration with no reason. Recognition and closure
had already been established before the delay.

**Required correction:** carry deadline checks into tree copying and other
potentially long loops, and check the deadline after operations such as sorting
before declaring that output complete. The runner must also validate the
deadline when accepting stage completion. Preserve sound acceptance and closure
already established within the budget, and retain trees completed before expiry.
Mark the affected requested output incomplete with a wall-time reason.

Audit the adjacent paths at the same time: fact selection, final projection
assembly/comparison, and result counts also contain unchecked work. The CLI's
`dataclasses.asdict()` and JSON serialization occur after `run_unit()` returns
and are outside its deadline; account for that work if the advertised unit budget
is intended to bound producing the serialized output. The reproduced defect
above occurs inside the existing, explicitly promised runner deadline.

**Acceptance checks:** expire time during the final graph sort and during the
last tree copy, including a grammar with exactly one tree and no remaining
alternative. Verify incomplete flags and wall-time reason, preserved acceptance,
and CLI exit status 3. An expiry-at-entry test alone does not cover these paths.

### 2. P2 — read a bounded stderr prefix from the file

Location: [runner.py](../../earley/grammarc/runner.py), line 298.

`stderr_path.read_bytes()[:STDERR_DIAGNOSTIC_BYTES]` reads the entire captured
file before retaining 4 KiB. The file-size ceiling bounds disk consumption, but
the parent still allocates memory proportional to the whole diagnostic file.
Its memory is not covered by the child process's `RLIMIT_AS` limit.

**Reproduction:** use a stand-in that writes stderr and exits 1, with
`max_dump_bytes=16 MiB`. Increasing stderr from 1 KiB to 8 MiB increased traced
peak parent allocations from approximately 321 KiB to 8,400,628 bytes, although
the returned diagnostic still contained only a 4 KiB prefix plus its wrapper.

**Required correction:** open the file and read at most
`STDERR_DIAGNOSTIC_BYTES` bytes directly. If additional bounded diagnostic
inspection is needed for failure classification, give it an explicit bound as
well. Do not read the complete file and slice afterward.

**Acceptance check:** an 8 MiB stderr file must yield the bounded diagnostic
without an allocation proportional to 8 MiB. Test the read bound, not just the
length of the final exception message.

### 3. P2 — distinguish file-limit evidence from a file exactly at the ceiling

Location: [runner.py](../../earley/grammarc/runner.py), lines 300–318.

For a nonzero exit, a dump whose size equals `max_dump_bytes` is treated as proof
of exhaustion. Writing exactly the allowed number of bytes does not establish
that any write exceeded the limit. Conversely, only the dump's size is inspected
when a process handles or ignores `SIGXFSZ`, the file-size-limit signal. A limit
on stdout or stderr can therefore be reported as an ordinary runtime failure.

**Reproductions:**

- A stand-in writes exactly 1,024 dump bytes, emits `unrelated failure`, and
  exits 1 under a 1,024-byte ceiling. The runner reports a dump-size limit,
  suppressing the ordinary runtime diagnostic despite no oversized write.
- A Python stand-in attempts a 2 MiB stdout write under the same ceiling. The
  OS stops the write with `OSError: [Errno 27] File too large`, but the runner
  raises `RuntimeError` instead of returning an explicit resource-limit result.
  This exercises the handled-signal case that the implementation comments
  explicitly intend to support.

**Required correction:** use evidence of an attempted oversized write, such as
the limit signal or an explicit bounded write-failure diagnostic, and consider
all constrained output streams. File size alone is insufficient to distinguish
these cases. Preserve uncertain or unrelated failures as runtime diagnostics;
report confirmed exhaustion as an incomplete resource outcome identifying the
affected output. Merely extending the size-equality check to all files would
retain the false-positive problem.

**Acceptance checks:** cover an exactly-full successful write followed by an
unrelated error, stdout and stderr write-limit failures, and the existing dump
overflow case. Confirm runtime failures clean staging without publication, while
confirmed resource exhaustion produces an explicit incomplete result.

## Disposition

The new graph export, atomic publication, ordinary nonzero-exit handling with a
memory ceiling, and iterative traversal pass the reviewed cases. The deadline
and diagnostic findings above are the remaining corrections. This review changes
no production code and makes no commit.
