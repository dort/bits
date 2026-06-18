# Encoding Primer: Raw Bytes, Hex, Base64, and MORK Context

This primer is meant to make the first lines of the pure-sink gist feel concrete. Those lines introduce four connected ideas: values are raw bytes, numeric byte order is big endian, raw results might not be printable, and hex/base64 are useful debugging views.

The short version: MORK can carry values as bytes. Those bytes may represent text, an integer, a float, a hash, or something else. The bytes themselves do not say which meaning was intended. Encodings like hex and base64 are just readable ways to show arbitrary bytes.

## 1. What Is a Byte?

A byte is 8 bits.

A bit is one binary digit: `0` or `1`.

So one byte can hold 256 possible values:

```text
binary range: 00000000 through 11111111
decimal range: 0 through 255
hex range:     00 through ff
```

Examples:

| Byte meaning | Decimal | Binary     | Hex |
| --- | ---: | --- | --- |
| zero byte | 0 | `00000000` | `00` |
| ASCII letter `A` | 65 | `01000001` | `41` |
| ASCII letter `a` | 97 | `01100001` | `61` |
| ASCII digit `0` | 48 | `00110000` | `30` |
| max byte | 255 | `11111111` | `ff` |

The byte value `0` and the text character `"0"` are different:

```text
byte zero:       0x00
ASCII character: 0x30
```

In Rust notation:

```rust
b'\0' == 0x00
b'0'  == 0x30
```

That is why the gist says:

```text
the ascii b'0' is not the byte b'\0'
```

## 2. Raw Bytes Have No Built-In Meaning

Raw bytes are just a sequence of byte values:

```text
68 65 6c 6c 6f
```

Depending on the interpretation, those same bytes could mean different things.

If interpreted as UTF-8/ASCII text:

```text
68 65 6c 6c 6f -> "hello"
```

If interpreted as a big integer:

```text
68 65 6c 6c 6f -> 448378203247
```

If interpreted as part of a binary protocol, those bytes might mean something else entirely.

This is the central point behind "raw bytes have no header." A header would be extra metadata saying something like "the next 16 bytes are an `i128`" or "this is UTF-8 text." The gist says pure values have no such header in front of them.

So when a pure operation receives a `Symbol`, the operation itself must know how to interpret those bytes.

## 3. Why Some Values Are Not Printable

Many byte values are not printable text characters.

For example:

```text
00 01 02 03 ff
```

These are valid bytes, but they are not a useful terminal string. If a program blindly prints them as text, you may see nothing, odd control behavior, replacement characters, or corrupted-looking output.

This is why debugging often converts bytes into a text-safe encoding first.

## 4. Hex Encoding

Hexadecimal, or hex, is base 16.

It uses 16 digits:

```text
0 1 2 3 4 5 6 7 8 9 a b c d e f
```

One hex digit represents 4 bits. One byte is 8 bits, so one byte is shown as exactly two hex digits.

Examples:

| Raw byte | Hex |
| --- | --- |
| `00000000` | `00` |
| `00001111` | `0f` |
| `11110000` | `f0` |
| `11111111` | `ff` |

The text `"hello"` is five bytes in ASCII/UTF-8:

```text
h     e     l     l     o
68    65    6c    6c    6f
```

So:

```text
raw bytes:  68 65 6c 6c 6f
hex text:   68656c6c6f
```

Important distinction:

```text
"hello"      is 5 bytes:  68 65 6c 6c 6f
"68656c..."  is 10 bytes: 36 38 36 35 36 63 ...
```

The hex string is a printable representation of the original bytes. It is not the same byte sequence as the original.

In the gist:

```text
(encode_hex qwerty)
(decode_hex 68656c6c6f)
```

`encode_hex` turns arbitrary symbol bytes into printable hex digits. `decode_hex` turns those hex digits back into the original bytes.

Hex has a simple size rule:

```text
encoded length = 2 * original byte length
```

That means hex is very readable, but it doubles the size.

## 5. Base64 Encoding

Base64 is another way to represent arbitrary bytes as printable text.

Instead of using 16 symbols like hex, base64 uses 64 symbols. This makes it denser than hex.

Standard base64 commonly uses:

```text
A-Z a-z 0-9 + /
```

Base64url, which the gist mentions, uses URL-friendlier characters:

```text
A-Z a-z 0-9 - _
```

Padding may appear as `=`.

The text `"hello"` as bytes is:

```text
68 65 6c 6c 6f
```

Base64url-encoded, it is:

```text
aGVsbG8=
```

Often the trailing `=` padding is omitted in URL-safe contexts:

```text
aGVsbG8
```

That matches the gist example:

```text
(decode_base64url aGVsbG8)
```

Base64 is less visually direct than hex, but it is more compact:

```text
hex:    1 byte -> 2 text characters
base64: 3 bytes -> 4 text characters
```

So for larger byte strings, base64 is usually shorter than hex.

## 6. Encoding Is Not Encryption

Hex and base64 do not hide data. They only rewrite bytes into printable characters.

Anyone can decode:

```text
68656c6c6f -> hello
aGVsbG8=   -> hello
```

Use them for transport, storage, logs, and debugging. Do not treat them as security.

## 7. Big Endian and Little Endian

Endianness is about byte order for multi-byte numbers.

The number `0x01020304` needs four bytes:

```text
01 02 03 04
```

Big endian stores the most significant byte first:

```text
01 02 03 04
```

Little endian stores the least significant byte first:

```text
04 03 02 01
```

The gist says values are stored in big endian order. That matters when a pure operation converts raw bytes into a numeric type like `i128` or `f64`.

For example, if four bytes are:

```text
00 00 03 e8
```

Big endian interpretation:

```text
0x000003e8 == 1000
```

Little endian interpretation:

```text
0xe8030000 == 3892510720
```

Same bytes, different number. So a conversion must know the intended byte order.

In Rust, this is explicit:

```rust
let n = i32::from_be_bytes([0x00, 0x00, 0x03, 0xe8]);
assert_eq!(n, 1000);
```

`be` means big endian.

## 8. Text Digits vs Numeric Bytes

The text `"1000"` and the integer `1000` are different byte sequences.

ASCII/UTF-8 text:

```text
"1000" -> 31 30 30 30
```

A 32-bit big endian integer:

```text
1000 -> 00 00 03 e8
```

An `i128` is 16 bytes, so `1000` as a big endian `i128` is:

```text
00 00 00 00 00 00 00 00 00 00 00 00 00 00 03 e8
```

This distinction explains why the gist has functions like:

```text
i128_from_string
i128_to_string
f64_from_string
f64_to_string
```

Those functions bridge between printable text symbols and raw numeric byte representations.

## 9. How This Relates to MORK Symbols

In the MORK codebase, symbols are byte strings. The frontend parser reads source text, tokenizes it, and writes symbols as bytes. The expression layer uses byte tags for structure such as arity, variables, variable references, and symbol sizes.

For ordinary tutorial code, you mostly see friendly source syntax:

```text
(example (06 00) encode_hex (encode_hex qwerty))
```

But internally, MORK is designed around compact byte-level representations.

That creates two important habits:

1. Do not assume a symbol is printable text.
2. When debugging arbitrary symbol bytes, encode them as hex or base64url.

## 10. MORK Pure Functions and Raw Bytes

The gist is about "Pure sink" operations. A pure operation is written as an expression and produces an output value.

Example:

```text
(encode_hex qwerty)
```

Conceptually:

```text
input symbol bytes:   qwerty
raw bytes:            71 77 65 72 74 79
output symbol text:   717765727479
```

The output is printable because `encode_hex` deliberately produces ASCII hex digits.

Now compare:

```text
(hash_expr 0)
```

A hash is raw bytes. If printed directly, it may not be readable. So the gist wraps it:

```text
(encode_hex (hash_expr 0))
```

That says: compute raw hash bytes, then convert those bytes into printable hex text.

## 11. Quick Reference

| Term | Meaning |
| --- | --- |
| bit | One `0` or `1` |
| byte | 8 bits, value `0..255` |
| raw bytes | Bytes with no inherent display format or type |
| ASCII/UTF-8 | A way to interpret bytes as text |
| hex | Printable base-16 encoding, 2 chars per byte |
| base64 | Printable base-64 encoding, denser than hex |
| base64url | URL-safe base64 variant using `-` and `_` |
| endian | Byte order for multi-byte numbers |
| big endian | Most significant byte first |
| little endian | Least significant byte first |
| `b'0'` | ASCII digit zero, byte `0x30` |
| `b'\0'` | zero byte, byte `0x00` |

## 12. Useful Checks While Reading the Gist

When you see a pure operation, ask:

1. Is this input meant to be text bytes, numeric bytes, or an expression?
2. If the output is raw bytes, should I wrap it in `encode_hex` or `encode_base64url` to inspect it?
3. If this is a number, where does the conversion from text to numeric bytes happen?
4. If this is a multi-byte number, is it being read or written in big endian order?
5. Is the byte `0x00` being confused with the printable character `"0"`?

Those five questions cover most of the early confusion around raw bytes in the gist.
