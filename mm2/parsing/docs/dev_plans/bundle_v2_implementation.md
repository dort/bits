# Version-2 source bundles: implementation and Claude boundary

Started 2026-11-10 by Codex, following the user's instruction to continue work
independently of Claude's engine and grammar compiler assignments. The
[pipeline plan](stream_splitter_and_earley_pipeline.md) remains authoritative.

## Ownership

Codex implemented source records, the bundle checker/writer/reader, and
migrated lexer serializers, CLI, examples, tests, and documentation. This work
stays in `lexer/`. Claude retains `earley/`; no engine or compiler files are
modified here. `tokenizer.config`, `validate_identifier`, and
`tokenizer.serialize.checked_atom` retain their existing public interfaces.

The reader API below is implemented and tested in the working tree as of
2026-11-10. Claude's Task A/B progress entries report both assignments complete;
their 19 tests also pass with this migration. Claude's proposed runner assignment
can now use these interfaces. Codex's next independent work remains boundary
matching and splitter integration in `lexer/`.

## Concrete contracts

- `tokenize()` continues producing one stream's ordinary records. Its lexical
  behavior, fingerprint recipe, and `lex-*` version-1 facts remain unchanged.
- `source_records(pieces, compiled_spec, *, namespace, source_id, ...)` wraps
  bounded `SourcePiece` inputs in a source envelope. A piece is a unit, gap, or
  dropped empty; its `following` character supplies original-source CRLF
  context. Unsplit input uses one caller-named unit. A future splitter produces
  pieces incrementally using the same builder.
- Source records are `SourceStart`, `UnitStart`, ordinary stream records,
  `Gap`, `DroppedEmpty`, and `SourceEnd`. Unit/gap spans partition decoded text;
  piece ordinals also order zero-length pieces. Token spans remain local.
- One lexical specification, kind catalog, runtime identity, and text encoding
  apply to the source. The source fixes generated or caller-owned identities.
  Generated IDs use the exact base/index formula; caller-owned namespace/stream
  pairs are capped at 100,000. Unit-count and identifier-length checks remain
  separate. There is no per-unit table in the manifest.
- `iter_jsonl`, `iter_mm2`, and `write_bundle` accept source envelopes. All
  existing callers migrate together; raw stream records are not interpreted
  as an old bundle format. `write_bundle` publishes four files atomically:
  `tokens.jsonl`, `tokens.mm2`, `streams.jsonl`, and `manifest.json`.
- Index ranges use half-open byte offsets. Each JSON range contains one unit's
  provenance and complete stream records. Each MM2 range contains only that
  stream's ordinary `lex-*` facts. Source/split facts live outside those slices.
- The checker withholds each `StreamEnd` until a valid outer boundary and
  withholds `SourceEnd` until normal producer exhaustion. The directory writer
  publishes only after the whole source validates.

## Reader contract for the future parser

Import `BundleReader` from `tokenizer`. `BundleReader(path)` accepts only version
2. `iter_entries()` streams index
metadata. `read_stream(entry, ...)` checks limits before loading that entry's
payload, then validates record ordering, identity, counts, catalog, fingerprint,
provenance, and exact agreement between JSON records and the MM2 slice. It
returns a bounded `BundleStream` with unit metadata, stream metadata, records,
completion, and MM2 bytes. The exact call is:

```python
stream = reader.read_stream(entry, max_tokens=512, max_chars=4_194_304,
                            max_payload_bytes=64 * 1024 * 1024)
compiled_grammar.check_terminals(stream.start.kinds)
# Feed stream.mm2 (bytes) to MORK with this unit's demand/grammar/round facts.
```

The parser passes its own token limit explicitly. Index entries expose
`namespace`, `source_id`, `stream_id`, `unit_index`, `piece_index`, `span`,
`following`, `token_count`, `source_length`, `skipped_span_count`,
`spec_fingerprint`, `kinds`, and `jsonl`/`mm2` dictionaries with `start`/`end`
byte positions. Their fixed `type` is `stream-index`.

`BundleStream.unit` is the `UnitStart` provenance record. `.start` and `.end`
are ordinary `StreamStart`/`StreamEnd` records; `.records` is the complete tuple
of ordinary stream records, and `.mm2` contains their lexical facts only.
Source metadata and aggregate counts are in `reader.manifest`; it has no
`streams` array. All units share its kind catalog and lexical fingerprint.

The reader defaults to 1,000,000 tokens, 4,194,304 characters, and 64 MiB combined
JSON/MM2 bytes per selected unit. Limits must be finite nonnegative integers.
`LimitError` identifies the exhausted budget before payload reads based on the
index; inconsistent payloads subsequently raise `OutputError`. Unknown versions
raise `ConfigurationError`. The shared error classes remain in `tokenizer.model`.

`iter_records()` validates the full source record sequence for reconstruction
and archive checks, including gaps and dropped empties. Consuming selected units
does not prove that every unselected unit has been validated. Reader metadata
and payload allocations have explicit finite limits. Index exhaustion verifies
its digest and aggregate counts. Full record exhaustion verifies source/gap
coverage, index ranges, and all three payload digests. A runner claiming a
completed whole-source result must validate the whole archive, including gaps;
it can exhaust `iter_records()` as a streaming preflight without retaining those
records. Reading selected streams alone is deliberately a narrower check.

All four archive filenames are fixed. Metadata rows are capped at 64 KiB and
ordinary JSON records at 64 MiB; gaps are capped at 65,536 characters per piece.
Callers may split larger gaps into consecutive bounded gap pieces. `following`
must be the next source character even across zero-length pieces; `""` means EOF.

## Decisions and alternatives

Use a sequential JSON Lines index with bounded entry reads. An in-memory map
would grow with source length; a database adds a dependency not needed for the
sequential parser. Selected payloads are checked against canonical serialization
of their JSON records, avoiding a second permissive MM2 parser and rejecting
extra executable facts. This requires the writer's canonical bytes, which is
appropriate for this versioned interchange format.

The implementation reuses shared record/atom/chunk validators in `serialize.py`,
with archive orchestration in `bundle.py` and source construction/checking in
`envelope.py`. Every serializer caller has migrated to the source envelope.

## Validation

Results on Python 3.14.10 and the local release MORK binary:

- Lexer: **83 tests pass**, up from the 63-test baseline. They include multiple
  units, empty sources/units, exact gap reconstruction, dropped empties, random
  source boundaries and CRLF, byte-range extraction, identity caps/policies,
  corrupted archives, parser resource errors, late failures, and publication races.
- Real MORK checks retain the exact lexical projection and validate cross-unit
  ordering, the final successor sentinel, and independent indexed-unit loading.
- Claude's Earley suite: **19 tests pass**; no `earley/` files were edited.
- The existing benchmark's source/lexer/serialization/bundle/MORK stages all run
  after migration. The README's complete MM2 example is checked against output.
- `git diff --check` passes.

Commands from `parsing/lexer/`:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m benchmarks.bundles --units 100 10000
.venv/bin/python -m benchmarks.measure --cases expression --sizes 128 \
  --stages source lexer serialize bundle mork \
  --report output/bundle-v2-migration-smoke.json
```

For Claude's tests, run the absolute interpreter
`/home/ni/repos/m/bits/mm2/parsing/lexer/.venv/bin/python -m unittest discover -s tests -v`
from `parsing/earley/`.

The generated-ID archive benchmark uses one-character units, fresh processes,
and consumes rows/records without collecting them:

| Units | Write | Read index | Verify full archive | Peak RSS | Output bytes |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 0.009 s | 0.003 s | 0.020 s | 23,052 KiB | 186,341 |
| 10,000 | 0.822 s | 0.244 s | 1.910 s | 22,952 KiB | 19,169,229 |

Peak RSS includes both writing and reading. Separate allocation tracing for
100,000 IDs measured 15,881,080 bytes for caller-owned identities and 1,267 bytes
for generated IDs. This replaces the earlier informal "few megabytes" estimate
with measured evidence. Full archive validation uses both source and index
identity checks, so caller-owned inputs may hold two capped sets. These small
synthetic runs establish the intended metadata behavior, not a throughput claim
for arbitrary lexemes or gigabyte archives. Raw reports are under ignored
`lexer/output/`.

This work does not implement boundary matching, the splitter CLI, Earley
orchestration, or forest traversal.
