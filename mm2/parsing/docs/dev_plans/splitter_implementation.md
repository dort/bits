# Streaming splitter implementation

Implemented by Codex on 2026-11-11, starting from `da559cf`. This completes the
splitter functionality in milestone 3 of the
[integrated plan](stream_splitter_and_earley_pipeline.md). Larger scale
measurements remain milestone 6. Claude's independent parser measurement work
is assigned in the [benchmark handoff](claude_parser_benchmark_handoff.md).

## Implemented interfaces

- `tokenizer.compile_split_spec`, `loads_split_spec`, and `load_split_spec`
  validate version-1 split specifications, using the shared strict JSON,
  flag, and SHA-256 fingerprint helpers.
- `tokenizer.split_chunks(chunks, compiled_split, *, source="<stream>")`
  accepts a lazy iterable of decoded strings and yields `SourcePiece` objects.
  It supports literal and bounded-regex separators and boundaries, retention,
  preamble, and empty-unit policies. Pieces include the next source character
  for exact CRLF handling.
- `tokenizer --split-spec ... --max-units ...` feeds the incremental decoder,
  splitter, existing lexer, and existing version-2 bundle writer. Split-mode
  total byte/character limits default to unlimited; the specification supplies
  a finite unit limit. The unsplit CLI retains its prior finite defaults and
  caller-supplied stream ID.
- Source records and bundle APIs retain their schemas. The source builder now
  translates positioned lexical errors into absolute source coordinates and
  retains `local_offset`, `local_line`, `local_column`, `unit_index`, and
  `stream_id` on the error. Direct lexer errors remain unit-local.

All production changes are under `lexer/`. No parser implementation files were
edited. The library APIs Claude's benchmark uses remain available unchanged.

## Matching algorithm and decisions

The matcher stores the undecided suffix, the actual preceding character, and
the current decoded chunk. Before source EOF, a candidate position must have
the full computed match width available plus one character of provenance
lookahead. At EOF the final suffix is resolved with its actual shorter length.

Searches use Python's literal search or compiled regex search. A match starting
beyond the decided prefix is deferred. Nonmatching text before that frontier
can be appended to the current unit permanently. After a match, search resumes
at its end, preserving earliest nonoverlapping semantics and Python's ordered
alternation and greedy/non-greedy choices. Buffer compaction retains the real
preceding character so `^` cannot mistake the buffer start for the source start.

Unit fragments accumulate separately from matching text. They are joined only
when a real boundary or EOF completes the unit. Unit-size checks happen when
new text is known to belong to the unit; exceeding the bound raises a positioned
limit error. The unit, match window, and decoded chunk bound working text
storage. Callers can still accumulate yielded pieces themselves.

The isolated regex validator walks CPython 3.14's normalized `re._parser` tree.
It validates every nested operation, computes minimum/maximum consumed widths,
and rejects unsupported assertions, unbounded repeats, and zero-width patterns
before source access. Literal/declaration widths are capped at 65,536 code
points. It uses the computed width when a declaration is looser. Common-prefix
normalization means `^a|^b` is accepted as one leading anchor plus a character
class; genuinely embedded anchors are rejected.

Alternatives considered: scanning each candidate individually would avoid
searching the small undecided suffix but add a Python call per source character.
Searching the bounded current buffer preserves the same decisions and releases
the decided prefix. Accepting arbitrary Python regexes would lose the finite
context guarantee; a second regex parser would duplicate the pinned runtime's
syntax handling. The selected private-parser dependency is isolated and fails
closed on unknown operations. This is a context bound, not a regex execution-time
guarantee; specifications remain trusted configuration.

## Verification

- **107 lexer tests passed**, including actual MORK load/dump queries and the
  new full source-to-parser integration test.
- **60 Earley tests passed** after the shared diagnostic integration.
- Fixed-seed randomized tests compare streaming output to an independent
  whole-string reference. Cases cover ordered alternatives, greedy and lazy
  repeats, leading anchors, source-start versus multiline semantics, empty
  chunks, and all separator/empty/preamble policies.
- UTF-8, UTF-16, and UTF-32 cases vary byte-read size from 1 through 18.
  Source pieces, gaps, and bundle spans reconstruct Unicode and CRLF exactly,
  including boundaries between CR and LF.
- Exact-limit units pass; oversized units fail without creating artificial
  boundaries. Known overflow stops reading additional chunks. Late lexical,
  decoder-finalization, and unit-count failures leave no final bundle or staging
  directory.
- Generated identities, split fingerprints, indexed unit retrieval, and
  cross-unit MM2 queries are checked through the existing transport mechanisms.
- A splitter allocation test consumes 32 KiB and 1 MiB synthetic sources with
  fixed 64-character units and 4 KiB chunks; peak traced splitter allocations
  stay below 256 KiB. This is a Python allocation regression, not a whole-process
  memory measurement or a claim about larger real workloads.
- The mixed-source CLI integration emits four streams and runs both parser
  implementations. Both report `accepted, rejected, rejected, accepted`, agree
  on item counts, and establish closure. Forest mode yields one tree for each
  accepted unit, none for rejected units, and complete graph/enumeration flags.
- The documented line and header demonstrations each produce three units and
  reconstruct exactly. All three expression units are accepted in forest mode
  with complete enumeration. Local generated results are under ignored
  `lexer/output/splitter-implementation-smoke/`.

These results cover Codex's splitter changes against the parser starting at
`da559cf`. Parallel changes in `earley/grammarc/runner.py` and
`earley/benchmarks/` appeared after this validation; they belong to Claude's
assignment and still need the final combined validation when that work is ready.

Run tests separately from each component directory to avoid their identically
named `tests` packages:

```bash
# From parsing/lexer/
.venv/bin/python -m unittest discover -s tests -q

# From parsing/earley/
../lexer/.venv/bin/python -m unittest discover -s tests -q
```

The [lexer README](../../lexer/README.md) contains the commands, specification
semantics, library example, limits, and source-to-parser demonstration. New
examples use generic lines and synthetic headers, with no application-specific
behavior.

## Remaining work and ownership

Claude can continue parser measurements entirely under `earley/` without
depending on this splitter implementation. Codex's next measurement work is
source decoding/splitting/lexing/writing at increasing total sizes and unit
counts, using fresh-process resident-memory and disk measurements. Integrate
those results with Claude's report when ready. Neither these small checks nor
the existing bundle measurements complete milestone 6's larger scale criteria.
