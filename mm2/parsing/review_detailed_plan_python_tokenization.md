# Review: detailed plan for reusable Python tokenization

Reviewed: `detailed_plan_python_tokenization.md` (bits/mm2/parsing/), 2026-11-08.
Review method: read the plan against the MORK sources it cites, then probed the
actual local runtime (`MORK/target/release/mork`) where the plan's claims decide
the design. Probe transcripts are reproduced below.

## Verdict

The plan is sound and ready to implement. Its single most consequential design
decision — never put a lexeme into an MM2 atom directly, transport it as
bounded hex chunks instead — rests on a claim about symbol truncation that I
verified empirically against the local binary, and the claim is **true and
worse than the plan's hedged wording suggests**. The findings below are
ordered by importance: one verified fact that strengthens the plan (and has a
consequence outside this project), two small additions to the fact schema,
and a handful of mechanism-level notes for implementation. Nothing requires
restructuring the plan.

## 1. Verified: the 63-byte symbol limit is real, silent, and applies to this binary

The plan says the non-interning build "currently truncates external symbols
beyond 63 bytes" and phrases the risk as "some MORK builds." Both halves
checked out, and the local build is one of those builds.

Source: `MORK/kernel/src/space.rs:233` — in the `not(feature="interning")`
path, a symbol longer than 63 bytes has its length clamped to 63; a
`truncated` counter increments and the panic that would have reported it is
commented out. Nothing reaches the user.

Runtime probe (two quoted strings and two bare symbols, each 80 bytes,
identical through byte 63, differing after):

```
(s A1 "0123...6789-TAIL-ONE")   ; 80 bytes inside the quotes
(s A2 "0123...6789-TAIL-TWO")
(b B1 L0123...6789TAILONE)
(b B2 L0123...6789TAILTWO)
(exec (q1) (, (s $i $v) (s $j $v)) (, (qpair $i $j)))
(exec (q2) (, (b $i $v) (b $j $v)) (, (bpair $i $j)))
```

Result: the join produced all four cross pairs — `(qpair A1 A2)`,
`(qpair A2 A1)`, and likewise for the bare symbols. The two distinct 80-byte
values became one 63-byte symbol inside the space. The dump also shows the
quoted symbol cut mid-string with its closing quote gone: a truncated quoted
symbol is no longer even re-parseable output. Three consequences:

1. **The plan's chunk transport is mandatory, not cautious.** With 24-byte
   chunks encoding to 49-byte atoms (`h` + 48 hex digits), every generated
   atom clears the limit with headroom. Keep the planned "check that every
   generated atom fits 63 ASCII bytes" as an assertion in the serializer, not
   just a documentation line — the runtime will not report a violation.
2. **Truncation is a collapse, not just a loss.** Two distinct lexemes sharing
   a 63-byte prefix would become one fact under set semantics, corrupting
   joins and counts, not merely shortening payloads. Milestone 4's fixture
   should include exactly the probe above as a regression guard: two long
   distinct lexemes must remain distinct after a round trip through MORK.
3. **Outside this plan's scope but discovered by its probe:** the existing
   `bits/mm2/git/load-into-mm2-from-git.py` converter emits quoted symbols up
   to 10,000 bytes (`blob-text`, `commit-message`, long paths). Under this
   binary every one of those over 63 bytes loads truncated, and distinct
   blobs sharing a 63-byte prefix collapse. The earlier load verification
   counted expressions parsed, which truncation does not change. The git
   converter should eventually adopt this plan's chunk codec; that is a
   point in favor of building the codec as a reusable module
   (`serialize.py`), which the plan already does.

## 2. Schema addition: make terminal-kind mismatch detectable

MM2 has no negation: a join that binds nothing produces nothing, silently.
The failure mode this invites for the next step is a grammar whose terminal
name differs from an emitted kind (`IDENT` vs `ID`) — the Earley scanner
simply derives no items and the parse "fails" with no diagnostic anywhere.

Recommend one additional fact per distinct kind that a stream actually
emitted:

```
(lex-kind NS S K)
```

Cost: a handful of facts per stream, computed from a set the lexer already
has. Benefit: the future parser can ship a one-rule probe — join each grammar
terminal against `lex-kind` and emit a `missing-terminal` fact for
enumerated grammar terminals with no match (by the enumerated-complement
idiom, since the grammar's terminal list is finite data). This converts the
worst silent failure of the whole pipeline into a visible fact.

For the same reason, consider carrying the specification fingerprint into the
space as a short prefix atom, e.g. `(lex-spec NS S <16 hex chars>)`. The
manifest already records the full fingerprint; this merely lets a space
holding several streams say which specification produced each, within the
63-byte atom budget.

## 3. Correct and worth keeping exactly as planned

Affirming these so they survive implementation pressure:

- **Token edges `(lex-token NS S P Q K)` with Q stored rather than computed.**
  In MM2 the alternative is a `pure` `sum_i64` evaluation per scan step to
  compute P+1. Storing the successor makes the Earley scanner a pure join:
  bind the expected kind K at position P, read Q, continue. It also leaves
  the door open to token lattices later (edges that advance more than one
  position) without a schema change. Right call.
- **Field order NS, S, P before K.** MORK matches against a trie; a scanner
  that knows its namespace, stream, and position binds a selective prefix.
  The plan states this rationale; it is correct.
- **Longest candidate across rules, declaration order on ties, with Python
  regex semantics inside each rule — documented honestly.** The plan's
  refusal to call this "maximal munch" and its explicit `a|ab` example is the
  right contract: it is implementable with one `pattern.match(text, offset)`
  per rule and is what rule authors can actually reason about.
- **`match(text, offset)` instead of slicing.** This preserves lookbehind and
  `\b` at the match boundary (the matcher sees the preceding character). One
  caveat to put in the rule-author documentation when it is written: with a
  nonzero offset, `^` still means start-of-string or after-newline, not
  "wherever matching resumes" — a rule using `^` without `MULTILINE` can
  never match after position 0. That is Python's documented behavior, not a
  defect, but a spec author will trip on it.
- **Rejecting isolated surrogates.** The chunk codec is defined over UTF-8
  bytes; a lone surrogate has no UTF-8 encoding, so this rejection is what
  makes "every accepted lexeme has exact UTF-8 transport" a theorem rather
  than a hope. The two decisions stand or fall together — good coherence.
- **Hex over base64url for chunks.** Both would fit (24 bytes → 48 hex vs 32
  base64 characters), and the runtime has `decode_base64url` as well as
  `decode_hex` among its pure functions (`kernel/src/pure.rs`). Hex is the
  right default anyway: no `-`/`_` characters to reason about, trivially
  eyeballable, and the 49-byte atom is well under the limit. Not worth
  revisiting unless payload volume measurably matters.
- **Scope discipline.** No plugin registry, no multiple backends, no
  speculative streaming, explicit refusal to guess encodings, staged output
  published only on success. The module split (spec/source/model/lexer/
  serialize) matches one responsibility per module without a framework.

## 4. One wording correction: MM2-side lexeme reconstruction

The plan says "MM2 token-value reconstruction uses the payload facts." Under
the verified truncation behavior that sentence needs narrowing: an MM2 rule
could `decode_hex` a single chunk (producing a ≤24-byte symbol, safe) or
compare chunk atoms directly, but it cannot reassemble a long lexeme into one
symbol — the reassembled symbol would itself be truncated at 63 bytes on
write. Reassembly of full lexemes is a Python-side operation over the ordered
`lex-value-part` facts. Suggested wording: "MM2 can match and decode
individual chunks; full-lexeme reassembly is done by the consumer outside the
space." The design is unaffected — the Earley parser scans kinds, not
payloads — but the contract should not promise what the runtime cannot hold.

## 5. Implementation mechanics worth pinning now

Small items where the plan states a requirement and the implementation has
exactly one correct mechanism; naming it avoids a silent gap:

- **Duplicate JSON key rejection.** Python's `json.load` silently keeps the
  last duplicate key. Detecting duplicates requires `object_pairs_hook`
  (raise on repeated keys in the pair list). Without it, that validation
  requirement is unimplementable with the standard parser.
- **Specification fingerprint recipe.** Pin it exactly: e.g. SHA-256 over
  `json.dumps(spec, ensure_ascii=True, sort_keys=True, separators=(",", ":"))`
  — note `sort_keys` sorts object keys only; the `rules` array keeps its
  order, which is what "preserves rule order" needs. Whatever recipe is
  chosen, write it in the README next to the fingerprint field, since two
  implementations of the fingerprint must agree byte-for-byte.
- **Empty-match validation.** The practical check is `compiled.match("")`
  plus a match at each rule against a probe during validation; the plan
  already concedes it is not a proof and backs it with the runtime
  zero-length guard. That two-layer structure is right; just make the runtime
  guard fail the input with the rule name, same as other lexical errors.
- **Line counting for CRLF.** The stated convention (CRLF is one break, a
  position between CR and LF stays on the preceding line) is implementable in
  one pass by counting breaks at the LF of CRLF and at any CR not followed by
  LF. Worth a dedicated fixture since off-by-one here corrupts every
  diagnostic silently.

## 6. Checked and fine without changes

- Identifier regimes (`[A-Za-z][A-Za-z0-9_]{0,31}` for names/namespaces,
  uppercase for kinds): all generated label atoms are ≤32 bytes, no MM2
  structural characters, no `$` prefix. Positions are decimal atoms, short by
  construction.
- `lex-end` as the completion marker distinguishing empty input (N=0, C=0)
  from all-skipped input (N=0, C>0) from an incomplete stream (no fact):
  correct, and the "no EOF token" decision matches Earley practice, where
  acceptance is an item spanning 0..N, not a sentinel terminal.
- Evaluating every rule at every offset is O(rules × positions) match
  attempts. Fine for the stated scale; the plan already defers optimization
  behind measurements and names the one optimization (combined alternation)
  that must NOT be taken because it changes selection semantics.
- Skip rules competing in the same longest-match selection (rather than a
  separate pre-pass): correct, otherwise a skip rule could eat the prefix of
  a longer emitted token.
- The milestone ordering (contracts → lexer → sources/JSONL → MM2+MORK probe
  → regression/measurement) puts the MORK integration before any
  format-specific work, and milestone 4's "report blocked rather than
  substitute a Python parser" is the honest failure mode.

## Summary of requested changes

1. Add the long-lexeme distinctness probe (§1) to the milestone-4 fixture and
   make the 63-byte atom check a serializer assertion.
2. Add `(lex-kind NS S K)` facts, and optionally `(lex-spec NS S <hex16>)`
   (§2).
3. Narrow the MM2-side reconstruction sentence (§4).
4. Pin duplicate-key detection and the fingerprint recipe in the plan's
   validation section (§5).

Everything else: proceed as written.
