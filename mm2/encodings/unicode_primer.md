# Unicode Primer: UTF-8 Text in a Byte-Oriented MORK World

This primer is a companion to the raw-byte encoding notes. The central idea is:

MORK symbols are byte strings. UTF-8 is one possible interpretation of those bytes.

That distinction matters. A symbol containing Greek, Sanskrit, emoji, or math letters is not a "Unicode object" inside MORK unless a specific operation treats it as UTF-8 text. At the storage and matching level, it is bytes.

## 1. The Layers

It helps to separate four layers that people often collapse into one word: "character."

| Layer | Meaning | Example |
| --- | --- | --- |
| byte | A value from `0..255` | `ce` |
| code point | A Unicode scalar value | `U+03B1` |
| encoded bytes | How a code point is stored | `U+03B1 -> ce b1` in UTF-8 |
| grapheme cluster | What a reader often sees as one character | `é` can be `e` plus combining accent |
| glyph | The drawn shape selected by a font | The rendered form on screen |

MORK mostly lives at the byte layer. Rust `&str` lives at the valid-UTF-8 layer. Human readers usually think in grapheme clusters or glyphs.

## 2. Unicode vs UTF-8

Unicode assigns abstract numbers called code points:

```text
Greek alpha:       α  U+03B1
Devanagari sa:     स  U+0938
brain emoji:       🧠 U+1F9E0
mathematical lambda: 𝛌 U+1D6CC
```

UTF-8 is an encoding of those code points into bytes.

UTF-8 has a useful property: ASCII stays exactly the same.

```text
A -> 41
( -> 28
) -> 29
space -> 20
```

Non-ASCII code points use multiple bytes.

```text
α -> ce b1
स -> e0 a4 b8
🧠 -> f0 9f a7 a0
```

So "number of bytes" is not the same as "number of Unicode code points", and neither is necessarily the same as "number of visible glyphs."

## 3. UTF-8 Byte Length Examples

Here are concrete examples.

| Text | Code points | UTF-8 bytes | Byte count |
| --- | --- | --- | ---: |
| `a` | `U+0061` | `61` | 1 |
| `α` | `U+03B1` | `ce b1` | 2 |
| `λ` | `U+03BB` | `ce bb` | 2 |
| `क` | `U+0915` | `e0 a4 95` | 3 |
| `🧠` | `U+1F9E0` | `f0 9f a7 a0` | 4 |
| `𝛌` | `U+1D6CC` | `f0 9d 9b 8c` | 4 |

A Greek word:

```text
κόσμος
```

UTF-8 bytes:

```text
ce ba cf 8c cf 83 ce bc ce bf cf 82
```

That is 6 Greek letters, but 12 bytes.

A Sanskrit word in Devanagari:

```text
संस्कृतम्
```

UTF-8 bytes:

```text
e0 a4 b8 e0 a4 82 e0 a4 b8 e0 a5 8d e0 a4 95 e0 a5 83 e0 a4 a4 e0 a4 ae e0 a5 8d
```

That is 27 bytes. It is not 27 human-visible letters.

## 4. What About UTF-16 and UTF-32?

UTF-8, UTF-16, and UTF-32 are different byte encodings for Unicode code points.

| Encoding | Basic idea | Practical note |
| --- | --- | --- |
| UTF-8 | 1 to 4 bytes per code point | Best default for files, Rust `str`, MORK source text |
| UTF-16 | 2 or 4 bytes per code point | Common in JavaScript internals, Windows APIs, and older systems |
| UTF-32 | 4 bytes per code point | Simple indexing by code point, but large |

For MORK source files and Rust-facing text, UTF-8 is the right default. It is what Rust strings use, it preserves ASCII bytes exactly, and it works naturally with byte-oriented parsing.

Use UTF-16 or UTF-32 only when interoperating with an external system that requires them. If those bytes are stored in MORK as a `Symbol`, treat them as binary data, not as normal MORK-readable text.

## 5. Why Grapheme Clusters Matter

Some visible characters can be represented more than one way.

For example, the character `é` can be:

```text
precomposed:        é  U+00E9
UTF-8 bytes:        c3 a9
```

Or it can be:

```text
decomposed:         e + ◌́
code points:        U+0065 U+0301
UTF-8 bytes:        65 cc 81
```

These may look the same:

```text
é
é
```

But they are different byte strings:

```text
c3 a9
65 cc 81
```

In MORK, those are different symbols unless some normalization step converts them to a canonical form before insertion or comparison.

This is one of the most important Unicode facts for byte-oriented systems.

## 6. MORK Symbols and UTF-8

The local MORK parser is byte-oriented. It scans bytes and treats these ASCII bytes as syntax:

```text
space:   20
tab:     09
newline: 0a
(:       28
):       29
;:       3b, for comments
$:       24, for variables
":       22, for quoted-token scanning
\:       5c, for quote escape scanning
```

UTF-8 continuation bytes are not treated as syntax by themselves. So a source token like:

```text
κόσμος
```

can be read as one symbol because none of its UTF-8 bytes are ASCII whitespace or parentheses.

Conceptually:

```text
source token: κόσμος
symbol bytes: ce ba cf 8c cf 83 ce bc ce bf cf 82
```

Similarly:

```text
source token: संस्कृतम्
symbol bytes: e0 a4 b8 e0 a4 82 e0 a4 b8 e0 a5 8d e0 a4 95 e0 a5 83 e0 a4 a4 e0 a4 ae e0 a5 8d
```

That is fine as long as you remember that matching is byte matching.

## 7. Good Practice in MORK

Use UTF-8 for human-readable symbols when all producers and consumers agree that the bytes are text.

Good candidates:

```text
person
κόσμος
नाम
संस्कृतम्
```

Use raw bytes, hex, or base64url when the data is not naturally text.

Good candidates:

```text
(encode_hex (hash_expr κόσμος))
(encode_base64url some_binary_symbol)
```

Validate UTF-8 at the boundary when an operation semantically requires text. In Rust, prefer:

```rust
let text = std::str::from_utf8(bytes)?;
```

Do not use unchecked UTF-8 conversion unless you have already proved the bytes are valid UTF-8:

```rust
let text = unsafe { std::str::from_utf8_unchecked(bytes) };
```

In MORK terms: a `Symbol` may contain valid UTF-8, but `Symbol` does not mean `String`.

## 8. Normalization Policy

If your MORK data uses Unicode text as identifiers, choose a normalization policy before data enters MORK.

The common choices are:

| Form | Rough meaning | When useful |
| --- | --- | --- |
| NFC | canonical composed form | General text identifiers |
| NFD | canonical decomposed form | Some text processing workflows |
| NFKC | compatibility composed form | Search/index keys, cautiously |
| NFKD | compatibility decomposed form | Search/index keys, cautiously |

For identifiers, NFC is usually the least surprising default.

Example problem:

```text
é      bytes c3 a9
é      bytes 65 cc 81
```

Without normalization:

```text
é != é
```

After NFC normalization:

```text
é == é
```

MORK itself should not silently normalize symbols at the storage layer. Silent normalization would change byte identity. Instead, normalize at ingestion, or add explicit pure operations if you want text-normalized comparisons.

## 9. Greek Examples

Greek letters are straightforward in UTF-8, but each letter is usually two bytes.

```text
α        ce b1
β        ce b2
γ        ce b3
λ        ce bb
π        cf 80
ω        cf 89
```

A MORK expression might use Greek symbols directly:

```text
(meaning λ lambda)
(word κόσμος world)
```

Byte-wise, these are not ASCII symbols. They just happen to be valid UTF-8 symbols.

If you need to debug what is actually stored:

```text
(encode_hex λ)
```

Expected output bytes, viewed as text:

```text
cebb
```

For:

```text
(encode_hex κόσμος)
```

Expected hex text:

```text
ce ba cf 8c cf 83 ce bc ce bf cf 82
```

As compact hex text:

```text
cebacf8ccf83cebccebfcf82
```

## 10. Sanskrit and Devanagari Examples

Sanskrit is often written in Devanagari. Devanagari uses combining marks and virama signs, so visible units are often multi-code-point grapheme clusters.

Examples:

```text
नमस्ते
```

UTF-8 bytes:

```text
e0 a4 a8 e0 a4 ae e0 a4 b8 e0 a5 8d e0 a4 a4 e0 a5 87
```

The sequence `स्` inside `नमस्ते` is not just one simple byte or one ASCII-style character. It includes:

```text
स  U+0938
्  U+094D  devanagari sign virama
```

Another example:

```text
संस्कृतम्
```

Breakdown:

```text
स   U+0938
ं   U+0902
स   U+0938
्   U+094D
क   U+0915
ृ   U+0943
त   U+0924
म   U+092E
्   U+094D
```

This means byte slicing is risky. Cutting the first 5 bytes of `संस्कृतम्` does not mean "first 5 letters"; it may cut in the middle of a code point.

Bad idea:

```text
take first N bytes of a UTF-8 symbol and call it text
```

Better idea:

```text
validate as UTF-8, then use Unicode-aware string operations outside raw MORK storage
```

## 11. Emoji and Non-BMP Characters

Some Unicode code points are outside the Basic Multilingual Plane. In UTF-8 they use four bytes.

```text
🧠 -> f0 9f a7 a0
𝛌 -> f0 9d 9b 8c
```

These are valid UTF-8 symbols. MORK can store the bytes.

But display, sorting, width, and user editing can be difficult:

```text
(tag 🧠 concept)
(symbol 𝛌 mathematical-lambda)
```

If these are user-facing labels, UTF-8 is fine.

If these are stable machine identifiers, consider whether ASCII identifiers plus a display label would be more robust:

```text
(label lambda "λ")
(label brain "🧠")
```

## 12. Sorting and Ordering

Byte order is not human collation order.

UTF-8 has useful technical properties, but sorting by raw bytes does not mean sorting according to Greek dictionary order, Sanskrit collation, locale-specific case rules, or user expectations.

For MORK internals, byte ordering may be acceptable and efficient.

For human-facing sorted output, use a Unicode collation algorithm outside the raw symbol layer, or define an explicit normalized sort key.

## 13. Case Mapping

Unicode case conversion is not a simple byte operation.

Examples:

```text
λ -> Λ
σ -> Σ
ς -> Σ
```

Greek has final sigma `ς`, which differs from ordinary sigma `σ`.

Some case mappings can change length or depend on language context. So avoid implementing case-insensitive matching by lowercasing ASCII bytes only unless you explicitly only support ASCII.

For MORK:

```text
ASCII-only case operation: say so explicitly.
Unicode case operation: validate UTF-8 and use a Unicode-aware library.
```

## 14. Escapes and Source Files

A `.mm2` source file containing Unicode should itself be saved as UTF-8.

Direct Unicode:

```text
(word κόσμος)
(word संस्कृतम्)
```

Escaped byte representation:

```text
(word (decode_hex cebacf8ccf83cebccebfcf82))
```

The direct form is easier to read. The hex form is more explicit and robust for debugging exact bytes.

When exact bytes matter, include a hex check nearby:

```text
(example greek-kosmos (encode_hex κόσμος))
(example sanskrit (encode_hex संस्कृतम्))
```

## 15. Recommended Mental Model

Use this rule:

```text
MORK Symbol = bytes
UTF-8 text = one disciplined interpretation of those bytes
Unicode glyph = what a font draws after text shaping
```

Then ask:

1. Is this symbol supposed to be human text?
2. Are the bytes guaranteed to be valid UTF-8?
3. Has the text been normalized?
4. Am I counting bytes, code points, or grapheme clusters?
5. Is byte equality the right equality for this operation?

For many MORK use cases, byte equality is exactly what you want. For human language text, it is often only the first layer.

## 16. Practical Guidelines

Prefer UTF-8 for readable labels and identifiers:

```text
(name person-1 Σωκράτης)
(term sanskrit संस्कृतम्)
```

Normalize at ingestion if logically equivalent text should match:

```text
NFC("e" + combining acute) -> "é"
```

Use hex/base64url for opaque binary values:

```text
(encode_hex (hash_expr संस्कृतम्))
```

Do not byte-slice UTF-8 unless you are deliberately working at the byte layer.

Do not assume visual sameness implies byte equality.

Do not assume byte length equals character count.

When writing Rust around MORK:

```rust
fn symbol_as_text(symbol: &[u8]) -> Result<&str, std::str::Utf8Error> {
    std::str::from_utf8(symbol)
}
```

Keep the fallible conversion. The fallibility is the point: not every MORK symbol is text.
