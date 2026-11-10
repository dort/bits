# Implementation handoff for Claude

Updated 2026-11-10. This is a file-based handoff in the shared repository; creating
it does not launch a Claude process or send a message to another service.

The user has authorized starting implementation after reviewing the revised
plan, and has requested tasks Claude can pick up. Codex accepts the substantive
revisions in commit `a37180f`: complete alternative identities,
production-specific child traversal, merged start roots, corrected packing
arguments, and the new regression requirements address the critical review.

## Read first

1. [Revised Earley plan](earley_span_forest_parser.md), especially the exact
   inference rules, identity table, traversal contract, and acceptance criteria.
2. [Integrated pipeline plan](stream_splitter_and_earley_pipeline.md), taking
   the Earley plan's amendments as authoritative where they differ.
3. [Critical review](review_earley_span_forest_parser.md) for the counterexamples.
4. [Remy's contribution](../../remy.mm2) and the
   [lexer README](../../lexer/README.md).
5. `/home/ni/AGENTS.md` and any more specific repository instructions.

The Git repository is `/home/ni/repos/m/bits`, not `/home/ni/repos/m`.
All new project files belong under `bits/mm2/parsing/`.

## Ownership for the initial implementation

| Owner | Files and work |
| --- | --- |
| Codex | `lexer/tokenizer/config.py`, `source.py`, location handling, lexical compiler migration, their tests and documentation. Subsequent source-envelope and splitter integration remains on this side until reassigned. |
| Claude | `earley/` MM2 engine artifacts, grammar compiler, and focused engine/compiler tests described below. |
| Coordinate first | Bundle record models, `lexer/tokenizer/serialize.py`, CLI migration, and any shared helper API changes. |

Work in the shared checkout without resetting, cleaning, or committing another
agent's changes. Before editing, inspect `git status` and read the latest versions
of the files you will touch. Keep your changes inside `earley/` except for adding
a dated progress entry to this handoff when Codex is not editing it.
Do not rewrite the plans or lexer implementation to make a local test pass.
Do not commit unless the user requests it.

## Shared foundations ready for use

Codex's initial implementation is present in the working tree:

- `tokenizer.config` provides the shared helpers listed under Task B. The lexical
  compiler has migrated to them with its existing fingerprint unchanged.
- `tokenizer.DecodedStream` is a lazy, single-use decoded-chunk iterator.
  `read_stream()` now joins it. It supports optional total limits, bounds pending
  decoder bytes at 64 KiB, preserves strict decoding and byte diagnostics, and
  marks completion only after successful EOF decoding. The caller owns the reader.
- `tokenizer.model.advance_location(..., following="")` accepts the character
  immediately beyond a separately held text piece, preserving CRLF coordinates
  when a chunk or unit ends between CR and LF. A streaming caller must resolve
  that lookahead before advancing past a trailing CR.
- The README and serialization explainer describe the migrated APIs. The two
  active plans now agree on capped caller-owned IDs and span-forest semantics.

Validation on Python 3.14.10: **63 tests passed**, including the actual MORK
integration tests. New coverage includes shared configuration diagnostics,
stable fingerprints, multibyte/BOM boundaries, EOF flushes, late source failures,
decoder limits, every CRLF piece boundary, and bounded decoder allocation while
consuming a virtual 8 MiB input. `git diff --check` also passed.

This completes the helper extraction portion of milestone 1. Source-envelope
contract fixtures, version-2 bundle records/writer/reader, splitting, and the
parser remain to implement. The existing CLI still publishes version-1
single-stream bundles. The next shared work is source-envelope fixtures and the
version-2 bundle migration; Tasks A/B can proceed independently under the
ownership table above.

## Task A — implement and test the two MM2 engines

This is the first independent assignment. It does not depend on the version-2
bundle writer or splitter being finished.

Create:

```text
earley/
  earley.mm2
  earley_forest.mm2
  tests/test_engines.py
  tests/fixtures/
  README.md
  .gitignore
```

Use the original five rules for recognition and the revised six rules for
forest mode. Load exactly one engine at a time. Keep the grammar as facts and
the scanner's token successor as data. Do not add grounded arithmetic or
hard-code example-specific grammar rules into the engine.

Factor the repeated rule definition if that improves maintenance, or keep the
two readable artifacts with tests checking their shared item/acceptance sets.
Do not create a second production rule-rewriting framework merely to generate
these two small files.

Supply finite round facts as test input. Design and test the final
execution-completed marker so it runs after the last complete sweep under MORK's
actual priority ordering. A clean process exit and an empty execution queue
alone do not establish Earley closure. The eventual runner will compare semantic
projections after additional completed sweeps.

For these engine tests, use ground `lex-*` token facts or facts generated by the
existing lexer. This is an inference test interface, not a production fallback
for old token bundles. The eventual parse command must consume version-2 bundles.

Required tests against real MORK:

- The existing `x + 12` example, with the pinned grammar digest and 13-item
  recognition result.
- Remy's `4 + 57 * 6 + 7` with a grammar enforcing multiplication precedence
  and left-associated addition; verify its expected completed forest facts.
- Wrong tokens, truncated input, an empty stream under a non-nullable grammar,
  and genuinely unproductive recursion.
- The 31-production unit chain: insufficient rounds are not a rejection proof;
  further complete sweeps eventually produce acceptance.
- Two streams and two grammar IDs with no cross-contamination.
- The ambiguous concatenation grammar and its binary-production dot-2 part
  counts at two token lengths.
- Direct/indirect unit cycles with finite item/node/part sets.
- Two identically shaped child productions retaining two distinct `part`
  alternatives, two independently ambiguous children, and one start-symbol root
  retaining two accepting production alternatives.
- Equality of canonical item and acceptance sets between the two engines on
  shared completed fixtures. The forest projection additionally includes
  `node` and `part`; round tables are excluded.
- A deliberately short runtime execution limit cannot satisfy the final marker
  check prematurely.

Record precise limitations. Do not report a recognition result as rejected
unless a fixture's closure has been established independently of its acceptance
Boolean. Do not claim a production runner or tree enumerator is complete when
only the engine artifacts and tests are implemented.

## Task B — grammar specification compiler

After Task A, implement `earley/grammarc/spec.py` and grammar serialization with
strict schema checks and named production/field diagnostics. This may proceed
once the shared configuration helpers below are present and tested.

Follow the grammar JSON and `grm-*` schema in the original and revised plans:
unique production names, declared start/nonterminals, tagged terminals, nonempty
right-hand sides in version 1, dot successors, and a deterministic fingerprint.
Terminal catalog checks use declared kinds, not only kinds observed in a unit.

Shared helper interface implemented in `tokenizer.config`:

```python
loads_json(text, *, source="<specification>")
load_json(path)
canonical_json_bytes(value)
fingerprint(value)
compile_flags(names)
```

JSON helpers reject duplicate object keys and non-JSON constants. Fingerprints
use the existing ASCII-escaped, sorted-key, compact JSON recipe. Schema-specific
validation belongs in each compiler. Helpers raise `ConfigurationError` from
`tokenizer.model`; grammar errors should preserve source, field, and production
context. Use `tokenizer.serialize.checked_atom` for emitted atoms and the existing
fingerprint-half convention.

Read these helpers before starting the compiler. If an interface is missing, report that
dependency and continue Task A or compiler fixtures; do not copy private lexer
functions or silently implement another fingerprint recipe.

Validate all compiler inputs before emitting MM2. Never interpolate unchecked
grammar names, kinds, or metadata into executable facts. Tests must reject
duplicate JSON keys, unsupported versions/types, unknown fields, undefined
nonterminals, duplicate production names, and undeclared terminals. Preserve
the documented grammar fingerprint fixture.

## Later work: do not overlap it prematurely

`grammarc/runner.py` depends on the version-2 bundle reader contract. Forest
traversal depends on the complete alternative identity from the revised plan.
After Tasks A/B, propose a concrete next assignment before editing either side
of the shared bundle boundary.

The future forest consumer must distinguish symbol nodes, prefix nodes, and
packed alternatives. A child `(nt A R2)` expands only production `R2`; indexing
alternatives without the child descriptor loses valid choices. Enumerating all
productions at such an edge produces duplicate trees. Keep the review's two- and
four-tree fixtures when that consumer is implemented.

## Environment and commands

Use the existing Python environment and real MORK binary. From `parsing/`:

```bash
export PYTHONPATH="$PWD/lexer:$PWD/earley"
lexer/.venv/bin/python --version
/home/ni/repos/m/MORK/target/release/mork --help
```

Prefer the unambiguous absolute runtime path in test discovery:
`/home/ni/repos/m/MORK/target/release/mork`, with the existing `MORK` environment
override supported. The invocation is:

```text
mork run INPUT.mm2 OUTPUT.mm2 --aux-path ENGINE.mm2
```

Read the dump file; do not treat stdout as a fact stream. Give subprocess tests
timeouts and put their temporary files under ignored `earley/output/`.

Run the existing lexer suite from `parsing/lexer/`:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Baseline before this implementation work: all 45 lexer tests passed, including
the actual MORK integration tests. Since both projects use `tests/`, run their
test discovery separately to avoid importing the wrong `tests.support` package.
No new third-party Python packages are required. The interpreter currently lacks
`_sqlite3`; the adopted capped-ID design does not need it.

## Report back in a file or the shared conversation

Give Codex/user the following handoff information when a task is ready:

1. Exact files changed and what works now.
2. Commands run, test counts/results, and any pre-existing failures.
3. Engine and fixture assumptions, including how completion was checked.
4. Public helper interfaces used or proposed changes to them.
5. Remaining dependencies, limitations, and the next independent assignment.

Do not state that work has been sent to or completed by another agent solely
because this handoff file exists.
