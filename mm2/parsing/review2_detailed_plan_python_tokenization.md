# Review round 2: updated plan for reusable Python tokenization

Reviewed: `detailed_plan_python_tokenization.md` as revised on 2026-11-08
(Python 3.14 baseline; round-1 review incorporated per its closing section).
Review method: every new factual claim the revision introduced was verified
against the artifact it describes — the user's completed CPython 3.14.10
build, the MORK kernel sources, and the local `mork` runtime. Results below.

## Verdict

**Approved for implementation. Nothing further is required.** All four
round-1 requested changes are incorporated, two of them with refinements that
improve on what was asked. Every new verifiable claim in the revision is
true. The remaining notes are informational, not change requests.

## Round-1 changes: incorporated, two improved

1. **Payload distinctness and atom-length guard** — present. Milestone 4 now
   requires two long distinct lexemes sharing a 70-byte prefix, reassembled
   and compared for exact equality; the 63-byte atom check is specified as an
   explicit runtime condition that survives `python -O`, which closes a hole
   the round-1 review did not name (a bare `assert` is deleted by `-O`).
2. **`lex-kind` catalog** — present, and refined from "kinds the stream
   emitted" to "kinds declared by emitting rules." The refinement is correct
   and I endorse it: the catalog's purpose is to let a future grammar check
   distinguish a misspelled terminal from a terminal that legitimately does
   not occur in one input. An observed-kind catalog would flag `INT` as
   missing on an input of identifiers — a false alarm. Declared kinds answer
   the actual question (is this name part of the lexical contract at all?),
   and observed kinds remain derivable from `lex-token` for free.
3. **`lex-spec` fingerprint fact** — present, refined from a 16-hex-character
   prefix to the full digest split into two 33-byte atoms (`h` + 32 hex
   each). Also an improvement: no digest bits are discarded, both halves fit
   the atom limit with headroom, and milestone 4 verifies they survive
   loading.
4. **MM2-side reconstruction wording** — corrected as requested: full-lexeme
   reassembly is explicitly a Python consumer operation, chunk-level
   comparison stays available inside MM2, and the contract no longer implies
   reconstructing a long lexeme as one MM2 symbol.
5. **Duplicate-key detection and fingerprint recipe** — both pinned, with the
   exact `object_pairs_hook` mechanism (checking pairs before dictionary
   construction, at every nesting level) and a complete runnable recipe. The
   added `parse_constant` rejection of `NaN`/`Infinity` and the caveat that
   the digest identifies a representation, not a behavioral equivalence
   class, are both correct.

## New claims, verified

Each item below was checked on 2026-11-08, not taken from documentation.

- **The worked example's digest is genuine.** Running the plan's exact recipe
  on the synthetic specification under the built CPython 3.14.10 yields
  `abcfb5fed40800240f2db2a33558d2a4` + `e0c7010c6b165172b8554beda8ddcbc3` —
  byte-identical to the `lex-spec` halves in the worked example. A worked
  example that reproduces under the pinned recipe is itself a test fixture;
  keep it synchronized if the synthetic specification ever changes.
- **The 3.14 regex behaviors are as stated**, confirmed on 3.14.10:
  `re.compile(r"\B").match("")` returns a match (so a standalone `\B` rule
  fails the empty-match validation, as the plan requires);
  `re.compile(r"\z").match("")` likewise; `re.match(r"[0-9]+\z", "12\n")`
  returns None while `re.match(r"[0-9]+$", "12\n")` matches `12`;
  `re.PatternError is re.error` holds; `unicodedata.unidata_version` reports
  `16.0.0`, matching the plan's statement.
- **`decode_hex` expects bare hexadecimal** — confirmed at
  `MORK/kernel/src/pure.rs:722-728`: the function hex-decodes the whole
  symbol, so the transport's leading `h` must be stripped before any future
  chunk-decoding call, exactly as the plan now says. For the planned chunks
  this is safe arithmetic: stripping `h` from a full chunk atom leaves 48 hex
  characters, an even count decoding to 24 bytes, inside the function's
  64-byte output buffer.
- **The chunk-preservation probe holds.** I ran it against the local binary:
  two 80-byte lexemes sharing their first 70 bytes, encoded per the plan
  (24-byte chunks, `h`+hex atoms, `lex-value-size`/`lex-value-part` facts).
  All 8 part facts loaded distinct; a join on equal chunk content at equal
  index reported exactly chunks 0–2 as shared (the bytes genuinely common to
  both values, since `-TAIL-ONE-` and `-TAIL-TWO-` also share `-TAIL-`) and
  chunk 3 as distinct. The same two values as direct symbols aliased in the
  round-1 probe. The transport does precisely what the plan claims: identity
  is preserved where values differ, and sharing appears exactly where bytes
  are equal.

## Informational notes (no change requested)

- **Float `version` and the digest.** `json.dumps` renders `1` and `1.0`
  differently, so they would fingerprint differently; the schema validation
  ("validate exact field types, including rejecting a Boolean where the
  integer version is required") should also reject a float `1.0` for
  `version`, so only one spelling of a valid specification exists. Likely
  already intended by "exact field types" — stating it so the test for it
  gets written.
- **`collapse_symbol` has a stray debug print** (`pure.rs:789`, a `println!`
  on a wrong-typed argument). Irrelevant to this plan — it correctly keeps
  symbol collapse outside the transport contract — but worth knowing if any
  future MM2 fixture parses `mork` stdout while exercising that function.
- **The interpreter now exists.** The plan was written while the 3.14 build
  was in progress; `python3.14` built and installed (3.14.10, GCC 13.3, all
  optional modules present after the dependency install). The `PYTHON314`
  placeholder in the environment section can be filled in when milestone 1
  starts; nothing in the plan needs rewording for it.

## Summary

The revision did what a revision should: it incorporated the review without
weakening any contract, improved two of the suggestions, extended the
verification plan to cover the new metadata facts, and made no unverifiable
claims — everything it asserts about Python 3.14, the MORK sources, and the
runtime reproduces exactly. Proceed to milestone 1.
