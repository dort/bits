# Python 3.14 lexer for MM2

A reusable lexer driven by JSON lexical specifications. It accepts a complete
Unicode string, file, or standard input and produces JSON Lines records and
ordered token facts for a future MM2 Earley parser. Recognition has no built-in
document format, whitespace policy, or numeric interpretation.

The implementation follows the [reviewed plan](../detailed_plan_python_tokenization.md).
The executable package, specifications, examples, tests, and development output
are all inside this `lexer/` directory, as requested when implementation began.

## Run

Run these commands from `/home/ni/repos/m/bits/mm2/parsing/lexer/`.
The local environment has been created from `/usr/local/bin/python3.14`
(CPython 3.14.10). To create it in a fresh checkout:

```bash
/usr/local/bin/python3.14 -m venv --without-pip .venv
```

There are no third-party Python dependencies. Explicitly use this interpreter
for commands; the system `python3` may be an older version.

```bash
.venv/bin/python -m tokenizer \
  --spec specs/expression_demo.json \
  --input examples/expression.txt \
  --namespace demo --stream-id s0 \
  --output-dir output/expression

.venv/bin/python -m tokenizer \
  --spec specs/characters_demo.json \
  --input examples/characters.txt \
  --namespace demo --stream-id chars \
  --output-dir output/characters
```

The first example emits three tokens: `IDENT("x")`, `PLUS("+")`, `INT("12")`.
The file's two spaces and trailing newline remain in skipped-span records.
The second specification emits every character, including whitespace, Unicode,
and characters that have special meaning in MM2.

Use `--input -` to read standard input, `--encoding NAME` for a declared text
encoding, and a new output directory for each run. Existing output destinations
are refused, including empty directories and symbolic links.

Each successful directory contains:

| File | Contents |
| --- | --- |
| `tokens.jsonl` | Stream start, emitted tokens, skipped spans, and stream end. Exact lexemes and source locations are retained. |
| `tokens.mm2` | Ground MM2 facts: token edges, spans, chunked values, specification identity, declared kinds, and completion boundary. |
| `manifest.json` | Counts, stream identity, source label, Python and Unicode versions, specification fingerprint, and completion status. |

The CLI stages all three files in a sibling directory, closes them, then
publishes the directory with Linux `renameat2(RENAME_NOREPLACE)`. This prevents
an existing destination from being overwritten even if another process creates
it during tokenization. Bundle publication requires a Linux filesystem supporting
that operation; failure is reported explicitly. The library's record iterators
can also be consumed directly. See the [rename system-call documentation](https://man7.org/linux/man-pages/man2/rename.2.html).

## Library API

```python
from tokenizer import Token, load_spec, tokenize, write_bundle

compiled = load_spec("specs/expression_demo.json")
for record in tokenize("x + 12", compiled, namespace="demo", stream_id="inspect"):
    if isinstance(record, Token):
        print(record.index, record.kind, record.lexeme, record.span)

write_bundle(
    tokenize("x + 12", compiled, namespace="demo", stream_id="saved"),
    "output/from-library",
)
```

- `compile_spec(mapping)` validates an in-memory specification.
- `loads_spec(json_text)` and `load_spec(path)` reject duplicate keys before
  dictionary construction, including nested duplicates.
- `read_stream(binary_reader, ...)` and `read_source(path, ...)` return a
  `TextSource` with `.text`, `.label`, and canonical `.encoding`.
- `tokenize(text, compiled_spec, *, namespace, stream_id, ...)` returns a
  single-pass iterator of immutable `StreamStart`, `Token`, `Skipped`, and
  `StreamEnd` records.
- `iter_jsonl(records)` and `iter_mm2(records)` yield serialized lines for one
  stream. Create a fresh token iterator for another pass, or explicitly retain
  records if the caller needs multiple passes.
- `write_bundle(records, output_dir)` publishes a complete bundle and returns
  the manifest mapping.
- `encode_lexeme(text)` returns a UTF-8 byte count and an iterator of
  `(chunk_index, encoded_atom)` pairs. `decode_lexeme(parts, *, byte_count,
  chunk_count)` validates and reassembles exported parts, accepting any order.

A direct iterator can yield tokens before a later lexical error. Consume it
through `StreamEnd` to establish completion. Serializers reject incomplete
record streams and inconsistent counts; bundle publication discards staging
output on a processing error. Caller-owned streams used with the line iterators
can contain a prefix after failure, so their callers own publication policy.

## Specifications and recognition

See [expression_demo.json](specs/expression_demo.json) and
[characters_demo.json](specs/characters_demo.json). The top level contains exactly
`version` (the JSON integer `1`) and a nonempty `rules` array. Boolean, string,
and floating-point versions are rejected, including `true`, `"1"`, `1.0`, and
`1e0`. Unknown fields and non-JSON constants are errors.

Each rule has a unique `name`, exactly one of `literal` and `pattern`, and exactly
one of `kind` and `skip: true`. Optional regex `flags` are a list drawn from
`ASCII`, `IGNORECASE`, `MULTILINE`, `DOTALL`, and `VERBOSE`; duplicates are errors.
Literal rules accept no flags. Several rules may emit the same kind.

Rule names, namespace names, and stream IDs match
`[A-Za-z][A-Za-z0-9_]{0,31}`. Terminal kinds match `[A-Z][A-Z0-9_]{0,31}`.
Lexemes have no such naming restriction.

At the current source offset, each rule produces at most one candidate. The
longest candidate wins; declaration order resolves ties. Skip rules compete by
the same rules. Python regex behavior applies inside each pattern: `a|ab` may
return `a`, and non-greedy quantifiers remain non-greedy. Matches use the complete
string and current offset, preserving lookbehind and boundary context. `^` does
not mean the current offset. There is no implicit whitespace handling or search
past unmatched text.

Patterns matching empty input are rejected at compilation. Python 3.14's `\B`
and `\z` both match empty input when used alone. A consuming pattern such as
`[0-9]+\z` is allowed. Any context-dependent zero-length match encountered at
runtime is also an error, even if another rule supplies a longer candidate.
No EOF or epsilon tokens are emitted.

Specifications are trusted local configuration. Python's regex engine does not
guarantee linear matching time; source-size limits are not regex timeouts.

## Source locations and limits

Source spans use half-open, zero-based Unicode code-point offsets. They are
separate from token indices, byte offsets, grapheme counts, and display columns.
Line and column numbers start at one; tabs advance one column. CRLF counts as
one break at LF, and lone CR or LF counts as one break. The boundary between
CR and LF stays on the preceding line, even when separate tokens consume them.

No implicit Unicode normalization, case conversion, newline conversion, numeric
conversion, or encoding guessing occurs. Byte sources default to strict UTF-8;
an explicitly selected codec determines decoding. Isolated surrogate code points
in text are rejected because the payload transport requires strict UTF-8.

The first implementation buffers the complete logical input and yields records
incrementally. Reader chunk boundaries do not create token boundaries.
The defaults are **16 MiB of input bytes** and **4,194,304 decoded characters**.
Change them with `--max-bytes` and `--max-chars`, or the corresponding library
arguments. Zero is permitted for empty-only input; negatives and Boolean limits
are rejected. Limits are checked while reading and decoding, before excess
decoded text is appended. The direct-string API checks the character limit.

These are source limits, not output-size or constant-memory guarantees. The
benchmark below includes the default boundary with four-byte Unicode characters.
Per-character tokenization produces substantially more metadata than a single
long token.

## MM2 contract

The following placeholders denote ground values in generated files:

| Placeholder | Meaning |
| --- | --- |
| `NS`, `S` | Dataset namespace and input occurrence ID. The caller keeps their pair unique within a shared space. |
| `P`, `Q`, `K` | Token index, its successor (`P + 1`, calculated in Python), and terminal kind. |
| `A`, `B` | Source character start and exclusive end. |
| `U`, `V` | Lexeme UTF-8 byte count and number of chunks. |
| `J`, `H` | Chunk index and its `h`-prefixed lowercase hexadecimal atom. |
| `D0`, `D1` | First and second 32-character halves of the specification's SHA-256 digest, each prefixed with `h`. |
| `N`, `C` | Final token count and source character count. |

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

`lex-kind` lists every kind declared by an emitting rule, including kinds absent
from an input. Position-bearing edges preserve repeated tokens in MORK's fact
set. `lex-end` marks successful completion; empty input ends at `0 0`, while
all-skipped input ends at `0` followed by its nonzero source length.

Lexeme chunks contain at most 24 UTF-8 bytes, encoded as atoms of at most 49 ASCII
characters. Every emitted atom is checked against MORK's 63-byte limit, including
under optimized Python execution. Raw lexemes never become MM2 syntax. Reassemble
chunks in Python before decoding UTF-8; a chunk boundary may split a character.

The fingerprint is SHA-256 over this representation of the validated specification
mapping `spec`, before inserting defaults:

```python
json.dumps(spec, ensure_ascii=True, sort_keys=True,
           separators=(",", ":"), allow_nan=False).encode("ascii")
```

Rule order is preserved. The digest identifies the specification representation;
runtime versions are recorded separately. It is not a proof that two different
representations behave differently or that the same specification behaves
identically on different Python versions.

## Verification

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The suite covers matching precedence, Python 3.14 anchors, decoding, source
locations, exact reconstruction, strict configuration, publication failures and
concurrent destination creation, and atom guards under `-O`.

MORK integration uses the actual repository runtime and
[consume_tokens.mm2](tests/fixtures/consume_tokens.mm2). It verifies adjacency,
completion, declared kinds, full fingerprints, repeated tokens, distinct long
values with a common prefix, and structural characters transported as data.
Set `MORK=/absolute/path/to/mork` to select another executable. An unavailable
runtime makes integration fail with an explicit message; Python checks are not
substituted for it.

To run the probe directly after creating `output/expression`:

```bash
"${MORK:-../../../../MORK/target/release/mork}" run \
  output/expression/tokens.mm2 output/expression-space.mm2 \
  --aux-path tests/fixtures/consume_tokens.mm2
```

To run only the Python tests when MORK is unavailable:

```bash
.venv/bin/python -m unittest tests.test_spec tests.test_lexer tests.test_sources \
  tests.test_serialization tests.test_cli -v
```

## Measurements

```bash
.venv/bin/python -m benchmarks.measure
.venv/bin/python -m benchmarks.measure --cases unicode-token --sizes 4194304 \
  --stages source lexer bundle --report output/limit-benchmark.json
```

Each measurement runs in a fresh process with a timeout. Reports include the
interpreter, build configuration, Unicode version, input sizes, rule counts,
elapsed time, output size, and Linux peak resident memory. Serialization time
uses prebuilt records; its memory includes those records. Bundle measurements
stream records. MORK timing includes process startup, loading, and dumping,
with no parser rules.

Observed locally on CPython 3.14.10, 2026-11-08, for 32,768 source characters:

| Case | Rules | Tokens | Lexer | Serialization | Complete bundle | MORK load/dump |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Expression | 6 | 10,923 | 0.042 s | 0.230 s | 0.263 s | 0.019 s |
| Many literal rules | 42 | 4,681 | 0.034 s | 0.099 s | 0.133 s | 0.009 s |
| Every character | 1 | 32,768 | 0.046 s | 0.446 s | 0.516 s | 0.063 s |
| One Unicode token | 1 | 1 | 0.002 s | 0.012 s | 0.013 s | 0.004 s |

Bundle peak memory was about 22 MiB for these inputs. At the default boundary,
4,194,304 emoji characters occupied 16 MiB in UTF-8. Reading/decoding took
0.040 s, lexing took 0.202 s, and publishing their single-token bundle took
1.636 s with about 134 MiB peak memory and 105 MiB of output. These measurements
support the initial finite source limits; they are synthetic observations,
not throughput guarantees or bounds for arbitrary rules. Generated reports are
under ignored `output/` directories.

## Diagnostics

Errors expose their category and, where applicable, source label, rule, field,
source offset, line/column, or regex pattern offset. Terminal excerpts are bounded
and escaped. The CLI uses exit status `0` for success, `2` for configuration or
Python-version errors, `1` for source/lexical/limit/output failures, and `130` for
an interrupted run. Encoding errors identify byte positions in their message;
lexical offsets identify decoded code points.

This release implements the lexer and its MM2 handoff. Earley parsing, application
specifications, online unbounded input, and ambiguous token graphs are subsequent
work.
