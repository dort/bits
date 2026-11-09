# Review: lexer implementation (Codex, 2026-11-08)

Reviewed: everything under `bits/mm2/parsing/lexer/` against the accepted
plan (`detailed_plan_python_tokenization.md`) and its two review rounds.
Review method: read all seven package modules and all six test files in
full; ran the complete suite with the project interpreter; then ran my own
end-to-end check that does not reuse any test fixture input.

## Verdict

**Accepted. All five milestones are complete and the contract is implemented
faithfully.** I found no defects. The deviations from the plan are small,
deliberate, and documented. Details and evidence below.

## Evidence

- **Suite:** `.venv/bin/python -m unittest discover -s tests` — 45 tests,
  all passing, under CPython 3.14.10 (the venv is built from the installed
  3.14, as the README documents).
- **Independent end-to-end run (not a fixture):** I tokenized a fresh
  two-line input (`total = alpha + 41` / `count == total`, 8 tokens) through
  the CLI and loaded the bundle into the real `mork` binary with the
  adjacency probe. The dumped space held exactly the 7 correct
  `(adjacent ...)` edges — `==` resolved to `EQ`, not two `ASSIGN`s, so
  longest-match selection survives transport — and
  `(completed indep t1 8 34)` matches 8 tokens over 34 source characters.
- **Plan synchronization is tested, not asserted:** `test_exact_plan_example`
  compares the serializer's output byte-for-byte against the plan's worked
  example, and `test_plan_fixture_is_synchronized` re-derives the documented
  fingerprint from the shipped specification. The plan document is now a
  verified fixture; if either drifts, the suite fails.
- **The truncation regression guard exists and passes:** the MORK test loads
  two lexemes sharing a 70-byte prefix plus a payload full of MM2 syntax
  (`$(exec ...)`, quotes, backslashes, NUL, non-BMP characters) and
  reassembles each exactly from the loaded chunk facts.

## Quality observations

Things the implementation does right that the plan only implied:

- `checked_atom` is an explicit runtime condition (`serialize.py:21`), not an
  `assert`, and a test launches `sys.executable -O` to prove it survives
  optimized mode.
- The version guard rejects booleans and floats for `version` by exact type —
  the round-2 note about `1` versus `1.0` fingerprinting differently is
  closed: only one spelling of a valid specification exists.
- `decode_lexeme` validates chunk indices, per-chunk lengths against the
  declared byte count, and duplicates before reassembly, so a corrupted
  export fails loudly instead of decoding to plausible garbage.
- The incremental decoder in `source.py` reports the absolute byte offset of
  a decode failure even when a multibyte sequence splits across read chunks,
  and the chunk-size sweep test (1 through 65536) proves chunking is
  invisible.
- `_checked_records` enforces the whole stream contract at serialization
  time (consecutive spans covering the input from zero, consecutive token
  indices, kinds inside the declared catalog, completion counts): the
  serializer re-verifies the lexer rather than trusting it.
- Location counting handles a CRLF pair split across two different token
  matches (`advance_location` looks at the full text, not the lexeme), with
  a dedicated boundary-walk test.

## Deviations from the plan, all acceptable

1. **Layout:** the implementation lives in `lexer/` with `tokenizer/` inside
   it, instead of `tokenizer/` directly under `parsing/`. Documented in the
   README as requested at implementation start. Better than the plan: it
   leaves `parsing/` free for the sibling Earley project.
2. **Publication uses Linux `renameat2` with `RENAME_NOREPLACE` via ctypes**
   rather than a plain rename. Stronger than the plan asked (it closes the
   race where the destination appears between the existence check and the
   rename, and a test exercises exactly that race). The cost is Linux-only
   publication, acceptable for this repository; the error message says so if
   it ever matters.
3. **`mork run` invocation:** tests use `mork run <input> <output>
   --aux-path <fixture>` — a destination dump file plus an auxiliary loaded
   file, which the earlier MM2 projects did not use. Verified working in my
   independent run; this is the right invocation shape for the parser step
   (data as input, engine as aux, dump to a file instead of scraping stdout).

## Cosmetic only

- Stale `__pycache__/*.cpython-312.pyc` files sit next to the 3.14 caches
  (an early run under the system 3.12 before the venv existed). Harmless and
  git-ignored; delete at will.

Nothing else. The next project step can build on this contract as-is; the
companion document `detailed_plan_mm2_earley_parser.md` plans it.
