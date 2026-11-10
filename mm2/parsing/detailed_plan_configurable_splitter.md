# Detailed plan: configurable stream splitter for gigabyte inputs

## Purpose and scope

Make multi-gigabyte files processable by the existing pipeline by adding a
**splitter**: a streaming stage that reads a large file front to back in
bounded memory, cuts it into bounded logical units according to a declarative
split specification, and feeds each unit through the existing lexer as its
own token stream. The downstream Earley parser then parses units, never the
whole file — which is what keeps every stage inside its complexity envelope
(the parser's item bound is quadratic in tokens per stream, so bounded units
are the difference between feasible and impossible; see the scale section of
`detailed_plan_mm2_earley_parser.md`).

The splitter is format-agnostic in exactly the sense the lexer is: the
engine knows nothing about logs, CSV, or JSONL. What constitutes a unit
boundary lives in a versioned JSON specification. This plan covers the split
specification, the streaming engine, multi-stream serialization, provenance,
and CLI integration. It does not cover parallel execution (designed for, not
implemented), binary input, or formats whose unit boundaries need unbounded
context (limits stated below).

## Working assumptions

1. **Units are recognizable in a bounded window.** Every real bulk format
   (log lines, JSONL, record-per-line CSV, multi-line log entries headed by
   a timestamp) has unit boundaries decidable from a bounded amount of local
   text. The specification must declare that bound, and the engine holds
   only a window of that order in memory.
2. **The splitter streams; the lexer still buffers one unit.** The lexer's
   whole-input assumption is untouched — it now receives one unit at a time,
   each capped by the specification's `max_unit_chars`. Peak memory is
   O(window + one unit), independent of file size.
3. **Reconstruction stays exact.** Concatenating all units and recorded gaps
   in order must reproduce the decoded input byte-for-byte after re-encoding,
   extending the lexer's reconstruction guarantee one level up. Nothing is
   silently dropped.
4. **Python 3.14, same environment, same JSON discipline** (duplicate-key
   rejection, exact types, the pinned SHA-256 fingerprint recipe) as the
   lexical specification.

## Alternatives considered

| Decision | Chosen approach and benefit | Alternative and tradeoff |
| --- | --- | --- |
| Where it lives | New module(s) in the existing `lexer/tokenizer` package, reusing the incremental decoder, record model, error hierarchy, and `checked_atom`. One toolchain, one environment. | A sibling package duplicates the transport guards (the 63-byte check would exist twice) or imports across directories for no benefit; the splitter is a front-end to the lexer, not a peer project. |
| Boundary model | Declarative: exactly one of `separator` (a unit ends at each match) or `boundary` (a unit starts at each match), literal or regex with a declared maximum match length. Covers line-delimited and header-delimited formats, the two shapes of bulk data. | Python callback plugins: arbitrary power, but executable configuration was already rejected for the lexer and the same reasons hold. Grammar-driven unit detection: circular — the parser is downstream of the splitter. |
| Split domain | Decoded characters, consistent with the lexer's offsets and the incremental strict decoder already in `source.py`. | Byte-domain splitting is ill-defined mid-stream for stateful codecs (UTF-16, shift encodings) and would give the pipeline two offset vocabularies. A byte-mode splitter for binary formats stays future work, as binary input already is for the lexer. |
| Unit output | One output bundle containing many complete streams, written in one pass (`tokens.jsonl`, `tokens.mm2`, one manifest). Requires extending the serializer from "exactly one stream" to "a sequence of complete streams" — a shared-infrastructure change made in place, with the existing single-stream callers migrated (a single stream is a sequence of one). | One bundle per unit: a gigabyte of log lines is ~10⁷ directories — unusable. Sharding k units per bundle is a later option for parallel workers, noted, not built. |
| Unit identity | Derived stream IDs `<stream_id>_u<index>` under the existing identifier regime, validated for total length against the expected digit count up front, so overflow is a loud configuration error at start, not at unit nine million. | Content-hash IDs break the "caller defines identity" contract and collide on repeated units, which bulk data is full of. |
| Cross-unit order | `split-*` facts mirroring the token-edge design: unit successors stored as data, so MM2 queries can walk units in order without arithmetic. | Leaving order only in the manifest keeps the space smaller but makes any cross-unit MM2 query impossible; two small facts per unit is the cheap end of the tradeoff. |

Out of scope, explicitly: a stateful boundary scanner (needed for formats
like CSV with quoted embedded newlines, where a newline's meaning depends on
quote parity — a small state-machine mode is the designed extension point if
that format actually arrives); payload-free transport profiles (skipping
`lex-value-*` facts to shrink gigabyte outputs — a real lever at scale, but
a contract change to decide separately, not smuggle in here).

## Split specification

Version `1`. Exactly one of `separator` / `boundary`, following the lexer's
exactly-one-of field style:

```json
{
  "version": 1,
  "separator": {"literal": "\n"},
  "max_unit_chars": 65536
}
```

```json
{
  "version": 1,
  "boundary": {"pattern": "^\\d{4}-\\d\\d-\\d\\d ", "max_length": 11,
               "flags": ["MULTILINE"]},
  "max_unit_chars": 1048576,
  "preamble": "unit"
}
```

| Field | Meaning |
| --- | --- |
| `separator` | A unit ends at each match; the match belongs to the unit it ends (`retain: "end"`, the default) or is recorded as a gap entry (`retain: "gap"`). Never silently dropped. |
| `boundary` | A unit starts at each match; a unit runs from one match start to the next. `preamble` says whether text before the first match is a unit (`"unit"`, default) or an error (`"reject"`). |
| `literal` / `pattern` | Exactly one. Literals mean exact character equality and derive their own length; regex patterns require `max_length`, the maximum characters a match may span, and accept the lexer's flag allowlist. |
| `max_unit_chars` | Required. A unit exceeding it is a loud limit error naming the unit index and its char offset — never a silent cut. Also becomes the per-unit lexer limit. |
| `empty_units` | `"keep"` (default: an empty unit is a valid empty stream) or `"drop"` (recorded as a gap, preserving reconstruction). |

Validation mirrors the lexical specification: duplicate keys, unknown
fields, exact types, flag allowlist, patterns that match empty input
rejected at compile time with a runtime guard behind it, and one new check —
at runtime, a match longer than its declared `max_length` is a specification
error, because the window guarantee depends on that declaration being true.
The fingerprint uses the identical pinned recipe and is recorded in the
manifest and the `split-spec` fact.

Stated limitation: patterns see a bounded window, so assertions about text
further than `max_length` beyond a candidate match start are unsupported and
documented as such. This is the honest boundary of the declarative model.

## Streaming engine

Mechanism, in one pass:

1. The incremental decode loop currently inside `read_stream` is extracted
   into an iterator yielding decoded text chunks (the one existing caller,
   `read_stream`, is migrated to consume it — same behavior, now shared).
2. The splitter appends decoded chunks to a working buffer and searches it
   for the separator or next boundary, never concluding "no match" within
   the final `max_length` characters of the buffer until end of input — the
   holdback that makes matches invisible to chunk edges. The existing
   source tests' chunk-size sweep (1 byte upward) is the model for proving
   boundary matches are chunking-invariant.
3. Each completed unit is emitted with its provenance — unit index, char
   offset, and start line in the original file (a cumulative line counter
   over the same forward pass; the lexer's within-unit lines are then
   relative, and absolute = unit start line + local line − 1). Byte offsets
   are deliberately not recorded in v1: stateful codecs make mid-stream byte
   positions ill-defined, and char offsets are exact.
4. The buffer retains only the unconsumed tail. Peak memory is
   O(`max_unit_chars` + decode chunk), asserted by a measurement test, not
   just claimed.
5. Each unit goes straight through `tokenize()` with the derived stream ID
   and into the multi-stream writer — split, lex, and serialize in one
   process, one pass, one output bundle.

A lexical error inside unit k fails the run loudly with the unit's
provenance attached (file offset and line, not just unit-local position).
Publication stays atomic: a failed run publishes no bundle, exactly as now.

## Multi-stream serialization (shared-infrastructure change)

`_checked_records` currently enforces exactly one stream per iteration. It
is extended, in place, to accept a sequence of complete streams: after a
`stream-end`, the next record may be a `stream-start` with a distinct
`(namespace, stream_id)` pair within the output (repeats rejected), and
every per-stream invariant applies unchanged within each stream. All three
consumers (`iter_mm2`, `iter_jsonl`, `write_bundle`) get this by
construction since they share the checker; existing single-stream callers
are valid sequences of one and need no changes beyond their tests asserting
that multi-stream inputs now pass instead of raising. The bundle manifest
becomes a file-level manifest: split-spec fingerprint, unit count, total
source chars, and a per-stream table (stream ID, unit index, char offset,
start line, token count).

## MM2 facts for the split level

`F` is the caller's base stream ID (now naming the whole file), `I` a
zero-based unit index, `I2` its successor, `S` the unit's derived stream ID,
`N` the unit count, and `D0`/`D1` the split-spec fingerprint halves:

```scheme
(split-stream NS F 1)
(split-spec NS F sha256 D0 D1)
(split-unit NS F I S)
(split-next NS F I I2)
(split-end NS F N)
```

Successors as data, per the standing doctrine: a cross-unit MM2 query walks
`split-next` and joins `split-unit` to reach each unit's `lex-*` facts with
no arithmetic. `split-end` distinguishes a completely split file from a
partial load, mirroring `lex-end`. All atoms pass `checked_atom`; the only
unbounded-looking one, the derived stream ID, was length-validated at start.

## CLI

One new pair of flags on the existing entry point, not a second tool:

```bash
.venv/bin/python -m tokenizer \
  --spec specs/loglines.json \
  --split-spec specs/split_lines.json \
  --input /data/huge.log \
  --namespace logs --stream-id day7 \
  --output-dir output/day7
```

Without `--split-spec`, behavior is byte-identical to today. With it, the
input bypasses the whole-file character limit (the per-unit limit governs),
`--max-bytes` defaults to unlimited, and the output is one multi-stream
bundle plus the `split-*` facts.

## Milestones

### 1. Multi-stream serializer

Extend `_checked_records` and the writers; migrate existing tests; add
multi-stream round-trip tests (JSONL and MM2), including two streams with
identical text, an empty stream between nonempty ones, and rejection of a
repeated stream ID. **Done when:** single-stream behavior is unchanged
byte-for-byte and multi-stream bundles load into MORK with per-stream fact
counts exact.

### 2. Split specification and streaming engine

Spec loading/validation/fingerprint; the decode-iterator extraction with
`read_stream` migrated; the windowed splitter with both modes. Tests: the
chunk-size sweep over boundaries that straddle every chunk edge; CRLF
separators split across reads; `max_length` runtime violation; oversized
unit; empty units kept and dropped; preamble both ways; a randomized
reconstruction fuzz (units + gaps reproduce the input, fixed seed) in the
style of the lexer's. **Done when:** both demo specifications split the same
synthetic file differently with no engine change, and reconstruction holds
on the fuzz.

### 3. Pipeline integration, provenance, and split facts

CLI flag, derived stream IDs with up-front length validation, per-unit
provenance in records and manifest, `split-*` fact emission, failure
provenance (lexical error inside unit k names the absolute offset), MORK
fixture joining `split-next`/`split-unit`/`lex-token` across unit
boundaries. **Done when:** the real MORK run answers an ordered cross-unit
query (first token kind of each of three units, in order) from the loaded
facts alone.

### 4. Scale measurement and documentation

A generated multi-hundred-MB synthetic file behind an opt-in environment
variable (too slow for the routine suite): assert peak RSS stays within a
fixed budget independent of file size, record end-to-end throughput, and
extrapolate the gigabyte cost honestly in the README (at the measured
~1 MB/s pure-Python lexing of token-dense input, a gigabyte is hours —
naming that number is the motivation gate for any matcher optimization,
which remains profile-first per the lexer plan). Document the window
guarantee, the stateful-boundary limitation with the CSV example, and the
parallel-sharding design note. **Done when:** the RSS bound is measured
fact, the README states the gigabyte arithmetic, and both demo split
specifications run from documented commands.

## Relation to the parser step

Nothing in `detailed_plan_mm2_earley_parser.md` changes. Units arrive as
ordinary bounded streams, each independently inside the parser's envelope;
`(parse NS S G)` demand facts can be emitted per unit (the grammar compiler's
demand generator takes the split manifest instead of a single-stream
manifest — a milestone-1-sized addition there once this plan lands). What
the splitter removes is the temptation to ever hand the parser an unbounded
stream.
