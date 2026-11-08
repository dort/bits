# Detailed plan: reusable Python tokenization

## Purpose and scope

Build a reusable Python 3.14 lexer that accepts input text and a separate lexical specification, produces a deterministic sequence of tokens, and exports those tokens as facts for a future Earley parser written in MM2.

This document plans the first step only. It does not implement the lexer or the Earley parser. All implementation, examples, tests, documentation, and generated development artifacts will initially live under `/home/ni/repos/m/bits/mm2/parsing/`.

The engine must have no knowledge of particular document formats. Input structure, token categories, whitespace handling, delimiters, and keywords belong in specifications. Format-specific specifications and processing will be added after the lexer and parser software work. The small specifications below are engine test cases, not application requirements.

The initial implementation will provide:

- A library accepting Python text independently of files or file extensions.
- A command-line interface accepting a file or standard input with an explicit text encoding.
- A declarative lexical specification with precise matching and precedence rules.
- Token records with exact lexemes and source locations.
- JSON Lines output for inspection and MM2 facts for parser consumption.
- Behavioral tests, including ingestion by the actual MORK runtime.

Earley prediction, completion, grammar loading, parse forests, semantic evaluation, and application-specific extraction are subsequent work. The Python lexer will not perform grammatical parsing or numerical evaluation.

## Working assumptions and design choices

These are proposed implementation decisions, with their limits stated explicitly.

1. **The first input domain is Unicode text.** Any text format can supply input without changes to the engine. Byte sources need a declared decoding; arbitrary binary grammars are outside this first text-lexer contract. Keep the source reader separate so adding a byte-oriented lexer later does not require changes to format-specific code inside this engine.
2. **A specification determines what counts as a token.** There is no built-in treatment of words, numbers, comments, punctuation, or whitespace.
3. **Tokenization is deterministic.** Each successful input produces one token sequence. Lexical ambiguity represented as a graph of alternatives is deferred; the future Earley parser can still handle grammatical ambiguity over the selected sequence.
4. **The first version processes finite inputs.** It reads one complete logical input into memory and yields token records incrementally. It does not promise bounded-memory tokenization of an indefinitely growing input.
5. **Python 3.14 and its standard library are the implementation and test baseline.** Use the user's source-built CPython 3.14 executable as the reference runtime. Record the full interpreter version and Unicode database version with output because regular-expression and Unicode behavior are part of reproducibility. Do not infer the target interpreter from the system's `python3` command.
6. **Input stays unchanged.** Do not normalize Unicode, case, whitespace, line endings, or numeric spelling implicitly. Matching flags may affect recognition but never rewrite a token's lexeme.

### Alternatives considered

| Decision | Recommended approach and benefit | Alternative and tradeoff |
| --- | --- | --- |
| Rule representation | JSON with a versioned schema; available in the standard library and straightforward to validate. | Python callbacks allow arbitrary recognition and actions, but make specifications executable and harder to inspect. A custom rule language adds another parser before the main tools work. |
| Recognition engine | Compile rules once using Python `re`; reuse a mature matcher and support useful text patterns immediately. | A finite-automaton implementation can provide genuine longest-match and incremental-input semantics, but requires a regex language, compiler, and execution engine. Reconsider when incremental input or predictable matching cost becomes a requirement. |
| Selection between rules | Choose the longest candidate returned by each rule, then declaration order on ties. Longer operators and identifiers do not lose to shorter prefixes. | First matching rule is simpler and can stop earlier, but rule order can accidentally split longer tokens. |
| Input buffering | Buffer one finite logical input; preserve exact Python regex behavior, including lookaround and end-of-input assertions. | Online input consumption reduces initial latency but cannot safely emit arbitrary regex matches just because the current read buffer ends. It needs a separately specified matching model. |
| Output interface | One neutral record model, with JSON Lines and MM2 serializers. Python consumers and MORK share the same tokenization semantics. | Writing MM2 strings directly from matching code saves an abstraction initially but couples recognition, diagnostics, and transport. |
| Lexeme storage in MM2 | Separate short token facts from reversibly encoded lexeme chunks. Parser scanning avoids traversing payloads. | Inline raw text is readable, but can become MM2 syntax; the inspected local runtime silently truncates input atoms beyond 63 bytes. Sidecar-only values prevent MM2 from accessing lexemes. |

Do not introduce multiple recognition backends, a plugin registry, or compatibility modes in this first implementation. If profiling or later requirements justify replacing the matcher, preserve or explicitly revise the documented lexical semantics and migrate its callers together.

### Python 3.14 environment

The source-built interpreter is installed at `/usr/local/bin/python3.14`; on 2026-11-08 it reported CPython 3.14.10 and Unicode database 16.0.0. Create the project-local environment from that executable when implementation starts. In the following planned commands, `PYTHON314` is its absolute path; update it if the installation moves, and run the commands from `parsing/`:

```bash
PYTHON314=/usr/local/bin/python3.14
"$PYTHON314" --version
"$PYTHON314" -m venv --without-pip .venv
.venv/bin/python --version
```

The first implementation needs only the standard library, so environment creation does not require installing packages. Keep `.venv/` inside this project and ignore it in version control. A virtual environment uses the interpreter that created it; subsequent run, test, and measurement commands will use `.venv/bin/python` explicitly. See the [Python 3.14 virtual-environment documentation](https://docs.python.org/3.14/library/venv.html).

Check for Python 3.14 at the library and CLI entry points before processing specifications or input. Report a clear version error under another minor version; do not add compatibility branches for older regex behavior. Use `sys.executable` when tests launch Python subprocesses so those checks exercise the same build.

Record `sys.implementation.name`, the full `sys.version` string, and `unicodedata.unidata_version` in output metadata. Python 3.14 uses Unicode 16.0.0; use the runtime's reported value rather than hard-coding metadata. Include the executable path and build configuration with benchmark results so measurements from different source builds can be compared. See the [Python 3.14 Unicode documentation](https://docs.python.org/3.14/library/unicodedata.html).

Runtime acceptance tests and performance measurements must run on the selected 3.14 build. Targeted probes of the documented regex behavior and specification fingerprint passed on the installed 3.14.10 interpreter. These verify the plan's examples; the lexer acceptance suite remains a deliverable of implementation.

## Architecture and ownership

```text
lexical specification -> validation -> compiled rules
                                          |
text / file / standard input -> text -> lexer -> record iterator
                                                 |        |
                                            JSON Lines   MM2 facts
                                                           |
                                                   future Earley parser
```

The source reader owns decoding and input limits. The rule loader owns configuration validation. The lexer owns recognition and source positions. Serializers own escaping, framing, and output representation. The future parser owns grammatical meaning.

Use ordinary functions and small data records. A separate module for each responsibility is sufficient; no service framework or abstract adapter hierarchy is needed.

### Proposed directory layout

```text
parsing/
  plan                                      # Existing project note, retained
  detailed_plan_python_tokenization.md       # This document
  README.md                                 # Usage and supported semantics
  .venv/                                    # Ignored environment from CPython 3.14
  tokenizer/
    __init__.py                             # Public library functions
    __main__.py                             # Command-line entry point
    spec.py                                 # Schema validation and compilation
    source.py                               # Text input and decoding
    model.py                                # Tokens, skipped spans, diagnostics
    lexer.py                                # Recognition and location tracking
    serialize.py                            # JSON Lines and MM2 serialization
  specs/
    expression_demo.json                    # Synthetic lexical test example
    characters_demo.json                    # Every character is significant
  examples/
    expression.txt
    characters.txt
  tests/
    test_spec.py
    test_lexer.py
    test_sources.py
    test_serialization.py
    test_mork.py
    fixtures/
      consume_tokens.mm2                    # Small handoff probe, not a parser
  output/                                   # Ignored generated development output
```

These are planned files, not additional deliverables of the present planning task. Use the standard-library test runner initially. Add a local ignore entry when generated output first exists.

## Input contract

### Library and command-line boundaries

The library's primary operation will have the conceptual shape `tokenize(text, compiled_spec, *, namespace, stream_id)`. Here `text` is a complete Python string, `compiled_spec` is a validated lexical specification, and `namespace` plus `stream_id` identify one input occurrence. The result is an iterator of stream-start, token, skipped-span, and successful stream-end records.

The command-line wrapper will read bytes from a file or standard input, then decode them with a named encoding. Use UTF-8 by default and strict decoding errors. A caller with a different encoding supplies it explicitly. Do not guess an encoding, replace undecodable bytes, or retry with a second encoding.

Read without automatic newline conversion. Python text I/O can translate newlines, so preserve the original decoded characters by reading binary input and decoding explicitly. A Python string supplied by a caller is already decoded; its offsets refer to exactly that string. See the [Python 3.14 I/O documentation](https://docs.python.org/3.14/library/io.html).

No file extension, content prefix, or source name selects a specification. The caller supplies the specification. File boundaries are input boundaries unless a future caller deliberately provides a different logical input.

### Positions and preservation

- Source offsets are zero-based Python string indices measured in Unicode code points. Every span is half-open: `char_start` is included and `char_end` is excluded.
- These are not byte offsets, grapheme-cluster indices, or screen columns. Do not derive original byte positions by re-encoding substrings under an arbitrary codec.
- Human-facing line and column numbers start at one. Count CRLF as one line break and lone CR or LF as one line break; retain both CRLF characters in offsets and lexemes. A position between CR and LF remains on the preceding line. Tabs and other characters advance the code-point column by one. Document that these are diagnostic conventions, not lexical whitespace rules.
- Reject isolated surrogate code points in directly supplied strings, so exact UTF-8 transport of every accepted lexeme is defined.
- Retain skipped spans in JSON Lines. Combining emitted and skipped lexemes in source order must reconstruct the accepted input exactly.
- Numbers remain text. For example, `001`, `1`, and `1.0` retain their distinct spellings. Numeric interpretation belongs to a later specification or semantic layer.

Track locations in one forward pass. Advance the line after consuming LF, or after consuming CR whose following character is not LF. Inspect the complete source when deciding whether CR begins a pair, even if two different lexical matches consume the CR and LF. Test locations before CR, between CR and LF, and after LF explicitly.

### Finite-input and resource contract

Reading chunks from a file must not create lexical boundaries. The first implementation assembles the complete decoded text before matching; a rule can span any number of physical lines.

The command line will expose a maximum input byte count and maximum decoded character count, with documented finite defaults selected during initial measurements. Reject excess input with a clear limit diagnostic. A large input must never be silently truncated or split at an arbitrary read boundary. The direct-string API checks the character limit before matching, although its caller has already allocated the string.

Memory use includes the complete text, compiled rules, the current match, and serialization buffers. Yield records rather than retaining every token in a list. Do not describe this as constant-memory input streaming. A future online lexer would need a separate decision about partial matches, longest possible tokens, and end-of-input behavior.

## Lexical specification

### Initial schema

Require a top-level `version` whose decoded value has exact Python type `int` and equals `1`, and a nonempty ordered `rules` array. Reject Boolean values, floating-point spellings such as `1.0` and `1e0`, and the string `"1"`. Numeric equality to `1` alone is insufficient validation. Each rule has:

| Field | Meaning |
| --- | --- |
| `name` | Unique rule identifier used in diagnostics and trace records. |
| `literal` or `pattern` | Exactly one nonempty literal string or Python regular-expression string. |
| `kind` or `skip` | Exactly one emitted terminal name or `skip: true`. |
| `flags` | Optional regex flag names from a documented allowlist: `ASCII`, `IGNORECASE`, `MULTILINE`, `DOTALL`, and `VERBOSE`. Omit for case-sensitive default matching. |

Reject flags on literal rules; literals mean exact character equality. Multiple rules may emit the same terminal kind. Rule identifiers must be unique; terminal kinds need not be.

Use short identifiers so the same terminal names can be used directly in MM2: rule names match `[A-Za-z][A-Za-z0-9_]{0,31}`, and terminal kinds match `[A-Z][A-Z0-9_]{0,31}`. These restrictions apply to labels, never to the source text or lexemes.

Reject unknown fields, duplicate JSON object keys, unsupported versions, invalid field types, conflicting actions, empty literals, invalid regex syntax, and unsupported flags. Report the rule name and field involved. Compile all rules before reading the input.

Use `json.load` with an `object_pairs_hook` that checks each object's key/value pairs for repeated keys before constructing its dictionary. A normal dictionary has already lost the evidence needed to reject duplicates. Apply this at every nesting level, and reject non-JSON constants such as `NaN` and `Infinity` through `parse_constant`. Validate exact field types before checking their allowed values. These hooks are described in the [Python 3.14 JSON documentation](https://docs.python.org/3.14/library/json.html#json.load).

### Synthetic example

```json
{
  "version": 1,
  "rules": [
    {"name": "spacing", "pattern": "[ \\t\\r\\n]+", "skip": true},
    {"name": "equals", "literal": "==", "kind": "EQ"},
    {"name": "assign", "literal": "=", "kind": "ASSIGN"},
    {"name": "plus", "literal": "+", "kind": "PLUS"},
    {"name": "integer", "pattern": "[0-9]+", "kind": "INT"},
    {"name": "identifier", "pattern": "[A-Za-z_][A-Za-z0-9_]*", "kind": "IDENT"}
  ]
}
```

The engine does not know what `INT` or `PLUS` means. Another specification can emit whitespace or use a rule with pattern `.` and flag `DOTALL` to emit every character as `CHAR`. Running both specifications without changing Python code is an early acceptance test.

### Matching semantics

At each current source offset:

1. Evaluate every rule at exactly that offset. Use `compiled_pattern.match(text, offset)` for regex rules, without slicing away the preceding text. Never use a search operation that skips unmatched input.
2. Each matching rule supplies its complete match as one candidate. Capture groups do not create additional tokens.
3. Select the candidate that consumes the most code points. Break equal-length ties by the rule's order in the specification. Skip rules participate in the same selection.
4. Emit a token or skipped-span record, then advance the source offset to the match end.
5. If no rule matches, report a lexical error at that offset and fail the input.

This is **longest candidate across rules**, with Python 3.14 regex semantics inside each rule. Python alternation tries branches in order: a pattern `a|ab` can return `a` when the input begins with `ab`. The lexer does not search for a longer alternative inside that pattern. Use separate rules, or write the pattern accordingly, when that distinction matters. Non-greedy quantifiers also retain their Python meaning. Document these semantics with examples rather than calling the algorithm unrestricted maximal munch. See the [Python 3.14 regular-expression documentation](https://docs.python.org/3.14/library/re.html).

Keeping the complete string also preserves lookbehind and word-boundary context. The `^` anchor still denotes the start of the string, or a position after LF with `MULTILINE`; it does not denote the current lexer offset. Diagnostic handling of lone CR does not change Python's regex anchor behavior. Include these distinctions in rule-author examples and tests.

For example, separate `=` and `==` rules choose `==` regardless of declaration order. A literal keyword rule placed before an identifier rule wins when both match the same complete word; a longer identifier wins over its keyword prefix.

Reject patterns for which `compiled_pattern.match("")` returns a match during validation. This check is not a complete proof against context-dependent empty matches. At runtime, any zero-length match encountered at a source position is a specification error, including a skipped match; fail the input with the rule name and source location. Do not allow it to cause a loop. Stop matching at the end of the source. No lexer rule emits an empty token or an end marker. A fixed collection of validation probes cannot replace the runtime guard.

Pin these Python 3.14 behaviors in the rule documentation and regression cases:

- `\B` now matches empty input. A standalone `\B` rule must therefore fail the validation-time empty-match check.
- `\z` matches only at the end of the string. A consuming pattern such as `[0-9]+\z` is allowed; a standalone `\z` rule is rejected for matching empty input. Test that `[0-9]+\z` fails on `12\n` while `[0-9]+$` can match its numeric prefix. JSON specifications escape each regex backslash, for example `"[0-9]+\\z"`.
- Catch `re.PatternError` for invalid patterns and attach its pattern location to the rule diagnostic. Test Unicode-sensitive matching against the 3.14 runtime rather than importing expectations from an older interpreter.

These are the native semantics of the [Python 3.14 regex engine](https://docs.python.org/3.14/library/re.html); the lexer must not rewrite patterns to emulate earlier versions.

Treat specifications as trusted local configuration initially. Python regex matching does not provide a general linear-time guarantee; input-size limits do not guarantee a bound on pathological matching time. Keep performance fixtures bounded by a process timeout. Do not add an undocumented regex rewrite that changes rule meaning.

## Record model and completion

Use explicit record types, serialized as one JSON object per line:

| Record | Required information |
| --- | --- |
| Stream start | Contract version, namespace, stream ID, source label, encoding if applicable, Python implementation and full version, Unicode database version, specification fingerprint, sorted distinct terminal kinds declared by emitting rules. |
| Token | Namespace, stream ID, zero-based token index, terminal kind, matching rule name, exact lexeme, source start/end offsets, start/end line and column. |
| Skipped span | Namespace, stream ID, matching rule name, exact lexeme, and the same source-location fields; no token index. |
| Stream end | Namespace, stream ID, emitted token count, decoded source length, successful completion. |

Pin the specification fingerprint to the following recipe. Here `spec` is the validated JSON object before inserting defaults, `canonical_bytes` is its canonical ASCII serialization, and `fingerprint` is the full lowercase SHA-256 hexadecimal digest:

```python
import hashlib
import json

canonical_bytes = json.dumps(
    spec,
    ensure_ascii=True,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
).encode("ascii")
fingerprint = hashlib.sha256(canonical_bytes).hexdigest()
```

Object-key order and JSON formatting do not affect this digest; array order, including rule order, is preserved. Explicitly supplying an optional field versus omitting it may produce a different digest even when behavior is equivalent. This identifies the validated specification representation, not an equivalence class of regex behavior. Interpreter and Unicode versions remain separate metadata; the same specification fingerprint alone does not establish identical behavior across runtimes. Store the algorithm name `sha256` and all 64 digest characters in JSON records and the manifest. Document the same recipe in the README. See the [Python 3.14 hashing documentation](https://docs.python.org/3.14/library/hashlib.html).

Keep source labels and arbitrary diagnostic text in JSON rather than interpolating them into MM2 atoms.

Token indices count emitted tokens only. If the lexer skips spaces between two tokens, their source offsets have a gap but their token indices remain consecutive. Never use token text as token identity: repeated identical tokens remain separate occurrences.

The direct iterator may yield a prefix before a later lexical error. Such a prefix is incomplete and has no stream-end record. Callers must consume through successful completion before treating the input as accepted. The command-line wrapper will stage output and publish a completed bundle only after successful tokenization and serialization.

## MM2 handoff contract

### Ordered input in a fact space

MORK stores facts in a set, so physical output order does not preserve a token sequence. Encode each token as an edge between consecutive parser input positions. These positions use ordinary decimal integers; they are independent of source character offsets.

The following placeholders describe the proposed fact schema; generated files substitute ground values for all of them:

| Placeholder | Meaning |
| --- | --- |
| `NS` | Caller-supplied namespace for a loaded dataset. |
| `S` | Input occurrence identifier, unique within that namespace. |
| `P` | Token's zero-based starting parser position and token index. |
| `Q` | The next parser position, computed in Python as `P + 1`. |
| `K` | Terminal kind from the lexical specification. |
| `A`, `B` | Inclusive source character start and exclusive source character end. |
| `N`, `C` | Final emitted token count and decoded source character count. |
| `J`, `H` | Zero-based lexeme chunk index and encoded chunk atom. |
| `U`, `V` | Lexeme UTF-8 byte count and total chunk count. |
| `D0`, `D1` | First and second halves of the specification digest, each encoded as `h` followed by 32 lowercase hexadecimal characters. |

```scheme
(lex-stream NS S 1)
(lex-spec NS S sha256 D0 D1)
(lex-kind NS S K)
(lex-token NS S P Q K)
(lex-span NS S P A B)
(lex-value-size NS S P U V)
(lex-value-part NS S P J H)
(lex-end NS S N C)
```

The `1` in `lex-stream` is the transport contract version. Put namespace, stream, and position before the less selective payload fields so a future scanner with a known input position can bind that prefix. The future grammar will use exactly the emitted terminal names.

Emit one `lex-spec` fact per stream. Split the full SHA-256 digest into two 33-byte atoms, retaining all digest bits within the atom limit. A shortened digest prefix would be smaller but could conflate distinct specification identifiers unnecessarily.

Emit one `lex-kind` fact per distinct terminal kind **declared by an emitting rule in the specification**, including kinds absent from this particular input. Derive this catalog from compiled rules and include it for empty and all-skipped streams too. Skip rules contribute no kind. Emit catalog facts in sorted order for deterministic files.

The catalog lets future grammar validation distinguish an undeclared terminal name from a declared terminal that simply does not occur in an input. For example, an input containing only `IDENT` tokens need not contain `INT` or `PLUS` to be valid. An observed-kind catalog would misdiagnose those absences as specification mismatches. Observed kinds remain derivable from `lex-token` without another stored relation. Grammar compatibility checks belong to the later parser step; catalog availability alone is not a missing-terminal detector.

`lex-end` appears only after complete successful processing. It supplies the accepting input boundary and distinguishes successful empty input from an incomplete stream. Empty input has token count zero and no token edges. All-skipped input also has zero token edges, but its source character count is nonzero. Do not create an `EOF` token or an epsilon token; any empty grammar production is the parser's responsibility.

The future Earley scanner needs to join its expected terminal with `lex-token`, then use the recorded next position. It need not calculate successors or inspect lexeme payloads to advance. This plan does not implement that scanner.

### Safe, reversible values

The local [MORK data description](../../../MORK.wiki/Data-in-MORK.md) and [frontend parser](../../../MORK/frontend/src/bytestring_parser.rs) show that parentheses, dollar-prefixed variables, comments, and quoted atoms have syntax-level meaning. The [kernel tokenizer](../../../MORK/kernel/src/space.rs) distinguishes interning and non-interning builds; the latter silently truncates external symbols beyond 63 bytes. A local runtime probe on 2026-11-08 confirmed that `MORK/target/release/mork` aliases distinct long bare symbols and distinct long quoted symbols when their retained prefixes match. A second probe preserved the distinct values exactly using the proposed 24-byte chunk encoding.

Truncation can make distinct values compare equal and can collapse otherwise identical facts under set semantics. Counting loaded expressions is insufficient to verify payload preservation. Bounded chunk transport and checked atom lengths are requirements for this runtime. Do not assume JSON string escaping is an MM2 string codec or rely on interning to preserve arbitrarily long atoms.

Use this transport rule:

1. Validate namespace and stream identifiers against `[A-Za-z][A-Za-z0-9_]{0,31}`. The caller must avoid reusing their pair for different inputs loaded into the same space.
2. Use the validated terminal names from the specification and decimal nonnegative positions. Enforce the maximum of 63 ASCII bytes for every generated atom, including metadata and integers, in a shared serializer check. Raise an output error before publication if the check fails. Use an explicit condition that remains active under `.venv/bin/python -O`; a removable Python `assert` is insufficient.
3. Encode each token's exact lexeme as UTF-8 bytes, split into fixed chunks of 24 bytes, with only the last chunk possibly shorter.
4. Encode each chunk as `h` followed by lowercase hexadecimal. Each chunk atom is at most 49 ASCII bytes, has no MM2 structural characters, and can be decoded without ambiguity.
5. Emit a `lex-value-size` fact and one `lex-value-part` fact per chunk. Chunk indices preserve ordering in the fact set. The Python consumer validates chunk indices and declared sizes, then reassembles all bytes before UTF-8 decoding because a chunk boundary may split a multibyte character.

Every fact has fixed, small arity. No giant atom, arbitrary-width expression, or deeply nested list is required for long lexemes. Do not intern a growing global lexeme dictionary in Python in this version. The cost is extra payload facts and approximately doubled payload character size from hexadecimal encoding; measure that cost separately from scanning.

MM2 facts contain emitted tokens and their source spans. JSON Lines additionally retains skipped text and detailed diagnostics. Exact input reconstruction uses the JSON records; full token-value reconstruction from exported payload facts occurs in Python. Inside MM2, rules can compare encoded chunks while retaining the chunked representation. This contract does not promise to reconstruct an arbitrarily long lexeme as one MM2 symbol.

The inspected [pure-function implementation](../../../MORK/kernel/src/pure.rs) rejects results longer than 63 bytes in `collapse_symbol`; that is distinct from silent truncation during text ingestion. Its `decode_hex` also expects bare hexadecimal, so the transport's leading `h` must be removed before any future chunk-decoding call. Decoding and arbitrary-byte export inside MM2 are outside this initial transport contract. A future specification needing literal-sensitive terminals can give those literals distinct kinds. More elaborate semantic use of lexeme values is later parser work.

### Worked example

For the exact input `x + 12`, using the synthetic specification, namespace `demo`, and stream ID `s0`, the complete MM2 data is:

```scheme
(lex-stream demo s0 1)
(lex-spec demo s0 sha256 habcfb5fed40800240f2db2a33558d2a4 he0c7010c6b165172b8554beda8ddcbc3)
(lex-kind demo s0 ASSIGN)
(lex-kind demo s0 EQ)
(lex-kind demo s0 IDENT)
(lex-kind demo s0 INT)
(lex-kind demo s0 PLUS)
(lex-token demo s0 0 1 IDENT)
(lex-span demo s0 0 0 1)
(lex-value-size demo s0 0 1 1)
(lex-value-part demo s0 0 0 h78)
(lex-token demo s0 1 2 PLUS)
(lex-span demo s0 1 2 3)
(lex-value-size demo s0 1 1 1)
(lex-value-part demo s0 1 0 h2b)
(lex-token demo s0 2 3 INT)
(lex-span demo s0 2 4 6)
(lex-value-size demo s0 2 2 1)
(lex-value-part demo s0 2 0 h3132)
(lex-end demo s0 3 6)
```

Here `demo` names the dataset, `s0` names the input occurrence, and the last fact records three tokens from six source characters. The `lex-spec` halves reproduce the exact synthetic specification's digest using the recipe above. The catalog includes `ASSIGN` and `EQ` even though this input emits neither. Spaces are represented by skipped-span records in JSON Lines. Source offset four and parser position two refer to different coordinates.

Keep this worked example synchronized with the synthetic specification through a regression check that recomputes its fingerprint and compares both documented digest atoms. Any change to the example specification must update its expected facts and the documentation together.

## Library, CLI, and failure behavior

Expose a small public API: load and compile a specification, tokenize a string, and serialize records. Keep file handling out of the lexer. Do not require MORK to run the Python-only lexer or inspect its JSON output.

The proposed command below will run from the `parsing/` directory once implementation exists:

```bash
.venv/bin/python -m tokenizer \
  --spec specs/expression_demo.json \
  --input examples/expression.txt \
  --encoding utf-8 \
  --namespace demo \
  --stream-id s0 \
  --output-dir output/expression
```

Use `--input -` for standard input. Require explicit namespace and stream identifiers when exporting MM2. The caller, not a content hash, defines input identity so two identical inputs can remain distinct occurrences.

Produce `tokens.jsonl`, `tokens.mm2`, and a small `manifest.json` containing the contract version, Python implementation and full version, Unicode database version, counts, identifiers, and the specification fingerprint. Build them in a temporary sibling directory and rename that directory into place only after every output closes successfully. Initially refuse to overwrite an existing output directory. Keep all development outputs under `parsing/`.

Diagnostics go to standard error and Python callers receive structured exceptions. Distinguish configuration, source/decode, lexical, resource-limit, and output errors. Include the source label and source location where available, and the rule name for a rule failure. Escape and bound any source excerpt so control characters or very long lines do not corrupt diagnostics.

Use exit status zero only for complete success; document nonzero statuses for invalid configuration and processing failures. A failure must not leave a final output bundle or success marker. If publication fails after scanning succeeds, report an output failure rather than claiming success.

## Implementation sequence and verification

Each milestone below has a concrete result. Do not start application-specific specifications between these milestones.

### 1. Establish the contracts and rule loader

- Create the local environment from the completed CPython 3.14 build, verify its version, and implement the runtime version check.
- Implement the data records and versioned JSON validation, including duplicate-key detection before dictionary construction.
- Compile regex rules once and preserve declaration order.
- Derive the declared-kind catalog and compute the specification fingerprint using the pinned recipe.
- Add tests for malformed rules, unknown fields, duplicate keys/names, conflicting actions, empty literals, invalid flags, and obvious empty matches. Explicitly test rejection of `version: true`, `version: 1.0`, `version: 1e0`, and `version: "1"`, while accepting the JSON integer `version: 1`.
- Add two synthetic specifications showing different treatment of the same input.

**Done when:** under CPython 3.14, valid specifications compile deterministically and invalid specifications fail before input reading begins, including standalone `\B` and `\z` rules. Other Python minor versions receive a clear version error.

### 2. Implement the generic lexer

- Match at the current source offset and select candidates using the documented ordering.
- Produce emitted and skipped records with exact spans, lexemes, and line/column locations.
- Fail on unmatched input and context-dependent empty matches.
- Test the direct-string API without filesystem or MORK dependencies.

**Done when:** the same lexer handles both synthetic specifications, skipped plus emitted text reconstructs the input, and every successful iteration consumes the complete source.

### 3. Add source handling and JSON Lines output

- Implement file and standard-input reading, strict decoding, input limits, and newline preservation.
- Implement stream-start and stream-end records and staged output publication.
- Record the actual Python and Unicode versions and specification identity.

**Done when:** a string, file, and standard input containing the same decoded text produce the same token kinds, values, and positions, apart from source metadata. Failure cases publish no completed bundle.

### 4. Implement MM2 serialization and the MORK probe

- Generate only the ground facts specified above.
- Implement and test the lexeme chunk codec independently of the matcher, with atom-length checks active in optimized Python as well as normal execution.
- Load generated facts into the actual MORK runtime with a minimal MM2 fixture that joins adjacent token edges and checks stream boundaries and kinds.
- Include two long distinct lexemes sharing at least their first 70 ASCII bytes. Reassemble each from the loaded/exported chunks in Python and require exact equality to its original value. Checking only token or expression counts would miss aliased payloads.
- Check declared kinds absent from the input, including empty input, and verify both fingerprint halves survive loading unchanged. Recompute the worked example's fingerprint from its documented specification and compare its expected atoms before loading the example into MORK.
- Follow the neighboring MM2 projects' `MORK` environment-variable override and repository-relative binary discovery. Keep the probe inside this project.
- Verify the loaded/exported payload facts as well as the token facts; a Python S-expression reader alone cannot establish MORK compatibility.

**Done when:** MORK preserves repeated tokens, separate streams, declared terminal names, full fingerprints, and distinct long payloads, and the fixture derives the expected adjacency facts. If the runtime is unavailable, report that integration check as blocked; do not substitute a Python parser and mark it passed.

### 5. Complete regression coverage, measurements, and usage documentation

| Area | Required cases and evidence |
| --- | --- |
| Selection | `=` versus `==`; keyword versus identifier; equal-length ties; competing skip and emit rules; regex alternation and non-greedy behavior; lookbehind and word boundaries at nonzero offsets; `^` with and without `MULTILINE`. |
| Python 3.14 semantics | Standalone `\B` and `\z` fail empty-match validation; consuming patterns with `\z` work and differ from `$` before a final newline; invalid patterns report `re.PatternError` details; Unicode-sensitive cases run under the selected 3.14 build. |
| Coverage and progress | Empty input; all-skipped input; no matching rule in the middle; context-dependent zero-length match; multiline tokens; no implicit whitespace treatment. |
| Locations | LF, CRLF, lone CR, tabs, combining characters, non-ASCII text, and non-BMP characters; locations before, inside, and after CRLF, including when separate rules consume CR and LF; spans index the original string exactly. |
| Source handling | Explicit non-UTF-8 encoding; invalid bytes; split multibyte sequences across reader chunks; different reader chunk sizes; byte and character limit failures. |
| Preservation | Reconstruct input from JSON token/skipped records; round-trip each lexeme through the MM2 chunk codec; preserve distinct numeric spellings. |
| MM2 syntax boundaries | Lexemes containing parentheses, quotes, backslashes, semicolons, dollar signs, newlines, NUL, and apparent executable forms remain payload data. |
| MM2 size boundaries | Payloads of 23, 24, 25, and many more bytes; Unicode split across chunks; distinct long values sharing a 70-byte prefix remain distinct after loading; atom guard accepts 63 ASCII bytes and rejects 64, including under `.venv/bin/python -O`. |
| Specification identity | Duplicate keys at multiple nesting levels fail; Boolean, float, exponent-form float, and string versions fail before hashing; JSON formatting and object-key order leave the fingerprint unchanged; changing rule order changes it; both MM2 digest halves reproduce the full JSON fingerprint; the documented worked example stays synchronized with its specification. |
| Declared kinds | Catalog contains all distinct emitting-rule kinds, including absent kinds and empty inputs; skip rules contribute none; observed token kinds are a subset of the catalog. |
| Identity and completion | Repeated identical tokens at different positions; two streams containing the same text; empty completed stream; interrupted or failed serialization has no final bundle. |
| Runtime handoff | Real MORK load and fixture execution; exact edge and chunk counts; expected adjacency results; no accidental variables or additional facts from payload text. |

Use `unittest` with fixed fixtures and a deterministic randomized round-trip test using a fixed seed. Test observable behavior, not private method calls. Keep a small manually calculated token oracle separate from the selection implementation.

Run the complete suite with the project interpreter once implementation exists:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests that check optimized execution must launch `sys.executable` with `-O`. Report the exact 3.14 patch/build and Unicode database version alongside results. A run under the system interpreter is not acceptance evidence for this target unless it is the selected 3.14 build.

Measure representative synthetic inputs of increasing size, varying rule count, average token length, skipped-text fraction, and Unicode content. Record lexer-only time, serialization time, MORK load time, output size, and peak memory separately. The initial algorithm attempts each rule at each consumed segment; regex cost itself depends on the pattern. Do not claim linear performance for arbitrary rules.

Profile before optimizing. Possible later improvements include literal-prefix indexing or batching output, provided the same regression cases preserve selection semantics. Do not combine patterns into one alternation merely for speed: that can change rule selection and regex group behavior.

**Done when:** the Python suite and actual MORK handoff check pass using the selected CPython 3.14 build, both demonstrations run from documented commands, resource defaults are justified by measurements from that build, and the limitations are written in the README.

## Boundary for the next project step

The first step is complete when a caller can supply arbitrary supported text plus a lexical specification, inspect exact tokens and locations, and load an explicitly ordered, complete token sequence into MORK.

The next plan can then define the MM2 Earley grammar representation and parser rules against this token contract. Decisions about online input, lexical state machines, ambiguous token graphs, binary input, and application-specific specifications remain explicit future requirements. None should be inferred from a file type or embedded in the generic lexer now.

## Review decisions

The [review](review_detailed_plan_python_tokenization.md) was incorporated on 2026-11-08 after checking the relevant local sources and probing the runtime. Accepted changes strengthen payload-preservation checks, add terminal and specification metadata, pin JSON validation and hashing, and clarify regex anchors and reconstruction boundaries.

Two schema recommendations were refined: `lex-kind` describes declared terminal kinds, because a kind absent from one input is not a configuration error; `lex-spec` preserves the full digest in two short atoms instead of using a truncated digest prefix. The plan also distinguishes external-symbol truncation from the checked size error in `collapse_symbol`. Parser-side mismatch diagnostics remain part of the future parser design.

The [second review](review2_detailed_plan_python_tokenization.md) endorsed the revised design and requested no structural changes. Its useful clarifications are incorporated: exact integer validation now explicitly excludes floating-point versions; the worked example's specification and fingerprint become a synchronized regression fixture; and the environment instructions use the verified installed interpreter path. Targeted checks on CPython 3.14.10 reproduced the documented fingerprint, regex behaviors, and Unicode database version.

No substantive design recommendation from the second review was rejected. Its observation about a debug print in MORK's `collapse_symbol` remains a separate runtime-maintenance issue: the planned lexer, transport, and handoff probe do not invoke that function, so changing it would not validate or improve this first-step implementation.
