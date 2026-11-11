import io
import random
import unittest

from tokenizer import (DecodedStream, LimitError, SourceError, SourcePiece,
                       source_records)
from tokenizer.split_spec import compile_split_spec
from tokenizer.splitter import split_chunks
from tests.support import chars_spec


def compile_split(matcher=None, *, mode="separator", **options):
    return compile_split_spec({"version": 1, mode: matcher or {"literal": "\n"},
                               "max_unit_chars": 1024, **options})


def reference(text, compiled):
    """Whole-string oracle: independent of streaming buffers and cursors."""
    import re
    pattern = compiled.pattern or re.compile(re.escape(compiled.literal))
    pieces = []
    cursor = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if compiled.mode == "separator":
            unit_end = end if compiled.retain == "end" else start
            pieces.append((text[cursor:unit_end], "unit", unit_end))
            if compiled.retain == "gap":
                pieces.append((text[start:end], "gap", end))
            cursor = end
        else:
            if start > cursor:
                pieces.append((text[cursor:start], "unit", start))
            cursor = start
    if cursor < len(text) or not text:
        pieces.append((text[cursor:], "unit", len(text)))
    return [SourcePiece(piece, "dropped-empty" if not piece and disposition == "unit"
                        and compiled.empty_units == "drop" else disposition,
                        following=text[end:end + 1]) for piece, disposition, end in pieces]


class SplitterTests(unittest.TestCase):
    def split(self, text, compiled, size=1):
        return list(split_chunks((text[i:i + size] for i in range(0, len(text), size)), compiled))

    def test_separator_policies_and_eof(self):
        for text in ["", "abc", "\n", "\n\n", "a\n\nb\n", "\na", "a\nb", "a\n"]:
            for retain in ["end", "gap"]:
                for empty in ["keep", "drop"]:
                    compiled = compile_split(retain=retain, empty_units=empty)
                    for size in [1, 2, 5, 1024]:
                        with self.subTest(text=text, retain=retain, empty=empty, size=size):
                            self.assertEqual(self.split(text, compiled, size), reference(text, compiled))

    def test_boundary_preamble_and_included_headers(self):
        matcher = {"pattern": "^UNIT [0-9]{4}: ", "max_length": 11, "flags": ["MULTILINE"]}
        for text in ["", "preamble", "UNIT 0001: ", "UNIT 0001: a\nUNIT 0002: b",
                     "pre\nUNIT 0001: a\r\nUNIT 0002: b\n"]:
            compiled = compile_split(matcher, mode="boundary")
            for size in range(1, 18):
                self.assertEqual(self.split(text, compiled, size), reference(text, compiled))
        reject = compile_split(matcher, mode="boundary", preamble="reject")
        for text in ["x", "x\nUNIT 0001: a"]:
            with self.assertRaises(SourceError) as caught:
                self.split(text, reject)
            self.assertEqual((caught.exception.offset, caught.exception.line, caught.exception.column),
                             (0, 1, 1))
        self.assertEqual(self.split("", reject), [SourcePiece("")])
        self.assertEqual(self.split("UNIT 0001: a", reject), [SourcePiece("UNIT 0001: a")])

    def test_python_alternation_greediness_and_anchor_context(self):
        for pattern, width, flags in [("a|ab", 2, []), ("ab|a", 2, []),
                                      ("a{1,3}", 3, []), ("a{1,3}?", 3, []),
                                      ("^a", 1, []), ("^a", 1, ["MULTILINE"]),
                                      ("(?m)^a", 1, []), ("A", 1, ["IGNORECASE"])]:
            compiled = compile_split({"pattern": pattern, "max_length": width, "flags": flags}, retain="gap")
            for text in ["aaabaa", "baaa\naa\na", "a\ra\r\na", "bbbbba"]:
                for size in range(1, 7):
                    with self.subTest(pattern=pattern, flags=flags, text=text, size=size):
                        self.assertEqual(self.split(text, compiled, size), reference(text, compiled))

    def test_decoder_boundaries_unicode_crlf_and_multichar_separators(self):
        text = "λ😀\r\nβ\r\n\r\n終"
        compiled = compile_split({"literal": "\r\n"}, retain="gap")
        for encoding in ["utf-8", "utf-16", "utf-32"]:
            for size in range(1, 19):
                decoded = DecodedStream(io.BytesIO(text.encode(encoding)), encoding=encoding, chunk_size=size)
                pieces = list(split_chunks(decoded, compiled))
                self.assertEqual(pieces, reference(text, compiled))
                self.assertEqual("".join(p.text for p in pieces), text)

    def test_size_is_a_limit_not_a_separator(self):
        for retain, text in [("end", "abc;"), ("gap", "abcd;")]:
            compiled = compile_split({"literal": ";"}, retain=retain, max_unit_chars=4)
            self.assertEqual(self.split(text, compiled), reference(text, compiled))
            with self.assertRaises(LimitError) as caught:
                self.split("abcde;", compiled)
            self.assertEqual((caught.exception.offset, caught.exception.line, caught.exception.column),
                             (4, 1, 5))
        # A delimiter may be larger than a unit when it is a gap.
        compiled = compile_split({"literal": "-----"}, retain="gap", max_unit_chars=1)
        self.assertEqual(self.split("a-----b", compiled), reference("a-----b", compiled))
        with self.assertRaises(LimitError):
            self.split("aa-----b", compiled)

    def test_early_overflow_without_exhausting_source(self):
        def chunks():
            yield "abcdef"
            self.fail("read past the known unit overflow")
        with self.assertRaises(LimitError):
            list(split_chunks(chunks(), compile_split(max_unit_chars=3)))

    def test_source_failure_preserves_only_partial_prefix(self):
        def broken():
            yield "a\nb\n"
            raise SourceError("late read failure")
        records = source_records(split_chunks(broken(), compile_split()), chars_spec(),
                                 namespace="demo", source_id="input")
        seen = []
        with self.assertRaises(SourceError):
            seen.extend(records)
        self.assertTrue(seen)
        self.assertNotIn("source-end", [r.type for r in seen])

    def test_empty_chunks_are_not_eof(self):
        self.assertEqual(list(split_chunks(["", "a", "", "\n", "", "b", ""], compile_split())),
                         [SourcePiece("a\n", following="b"), SourcePiece("b")])

    def test_randomized_chunk_invariance_and_reconstruction(self):
        rng = random.Random(7351)
        specs = [compile_split({"literal": "ab"}, retain="gap"),
                 compile_split({"pattern": "a{1,3}|b?;", "max_length": 3}, retain="end"),
                 compile_split({"pattern": "^a[ab]{0,2}", "max_length": 3, "flags": ["MULTILINE"]},
                               mode="boundary"), compile_split(empty_units="drop", retain="gap")]
        for _ in range(100):
            text = "".join(rng.choice("ab;\r\nλ") for _ in range(rng.randrange(100)))
            chunks = []
            start = 0
            while start < len(text):
                end = start + rng.randrange(1, 10)
                chunks.append(text[start:end])
                start = end
            for compiled in specs:
                pieces = list(split_chunks(chunks, compiled))
                self.assertEqual(pieces, reference(text, compiled))
                self.assertEqual("".join(p.text for p in pieces), text)
