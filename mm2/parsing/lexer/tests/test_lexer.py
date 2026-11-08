import random
import unittest

from tokenizer import (ConfigurationError, LexicalError, LimitError, Skipped, SourceError,
                       StreamEnd, StreamStart, Token, load_spec, tokenize)
from tests.support import HERE, chars_spec, spec


def records(text, compiled):
    return list(tokenize(text, compiled, namespace="demo", stream_id="s0"))


def tokens(text, compiled):
    return [r for r in records(text, compiled) if isinstance(r, Token)]


class LexerTests(unittest.TestCase):
    def test_manual_expression_oracle(self):
        result = records("x + 12", load_spec(HERE / "specs/expression_demo.json"))
        selected = [r for r in result if isinstance(r, Token)]
        self.assertEqual([(r.index, r.kind, r.lexeme, r.span.char_start, r.span.char_end) for r in selected],
                         [(0, "IDENT", "x", 0, 1), (1, "PLUS", "+", 2, 3), (2, "INT", "12", 4, 6)])
        self.assertEqual("".join(r.lexeme for r in result if isinstance(r, (Token, Skipped))), "x + 12")
        self.assertEqual((result[-1].token_count, result[-1].source_length), (3, 6))
        self.assertEqual(result[0].kinds, ("ASSIGN", "EQ", "IDENT", "INT", "PLUS"))

    def test_same_input_different_specification(self):
        text = "x + 12"
        self.assertEqual(len(tokens(text, chars_spec())), 6)
        self.assertEqual(len(tokens(text, load_spec(HERE / "specs/expression_demo.json"))), 3)

    def test_longest_and_tie_order(self):
        compiled = spec({"name": "eq", "literal": "=", "kind": "ONE"},
                        {"name": "eqeq", "literal": "==", "kind": "TWO"},
                        {"name": "other", "literal": "==", "kind": "OTHER"})
        self.assertEqual([r.kind for r in tokens("===", compiled)], ["TWO", "ONE"])

    def test_keyword_prefix_and_skip_competition(self):
        compiled = spec({"name": "keyword", "literal": "if", "kind": "IF"},
                        {"name": "word", "pattern": "[a-z]+", "kind": "WORD"},
                        {"name": "space", "literal": " ", "skip": True})
        self.assertEqual([r.kind for r in tokens("if iff", compiled)], ["IF", "WORD"])
        compiled = spec({"name": "skip", "literal": "a", "skip": True},
                        {"name": "emit", "literal": "ab", "kind": "AB"})
        self.assertEqual([r.lexeme for r in tokens("ab", compiled)], ["ab"])
        compiled = spec({"name": "skip", "literal": "a", "skip": True},
                        {"name": "emit", "literal": "a", "kind": "A"})
        self.assertEqual(tokens("a", compiled), [])

    def test_regex_internal_order_and_nongreedy(self):
        compiled = spec({"name": "alt", "pattern": "a|ab", "kind": "ALT"},
                        {"name": "b", "literal": "b", "kind": "B"})
        self.assertEqual([r.lexeme for r in tokens("ab", compiled)], ["a", "b"])
        compiled = spec({"name": "lazy", "pattern": "a+?", "kind": "A"})
        self.assertEqual([r.lexeme for r in tokens("aaa", compiled)], ["a", "a", "a"])

    def test_context_and_anchors_are_not_sliced(self):
        compiled = spec({"name": "a", "literal": "a", "kind": "A"},
                        {"name": "look", "pattern": "(?<=a)b", "kind": "B"})
        self.assertEqual([r.kind for r in tokens("ab", compiled)], ["A", "B"])
        for pattern in [r"\bb", "^b"]:
            compiled = spec({"name": "a", "literal": "a", "skip": True},
                            {"name": "b", "pattern": pattern, "kind": "B"})
            with self.subTest(pattern=pattern), self.assertRaises(LexicalError):
                records("ab", compiled)
        compiled = spec({"name": "newline", "literal": "\n", "skip": True},
                        {"name": "b", "pattern": "^b", "flags": ["MULTILINE"], "kind": "B"})
        self.assertEqual([r.lexeme for r in tokens("\nb", compiled)], ["b"])

    def test_end_anchor_and_exact_lexemes(self):
        end = spec({"name": "number", "pattern": r"[0-9]+\z", "kind": "N"})
        self.assertEqual(tokens("001", end)[0].lexeme, "001")
        with self.assertRaises(LexicalError):
            records("12\n", end)
        dollar = spec({"name": "number", "pattern": "[0-9]+$", "kind": "N"},
                      {"name": "newline", "literal": "\n", "skip": True})
        self.assertEqual(tokens("12\n", dollar)[0].lexeme, "12")
        case = spec({"name": "case", "pattern": "abc", "flags": ["IGNORECASE"], "kind": "WORD"})
        self.assertEqual(tokens("AbC", case)[0].lexeme, "AbC")

    def test_multiline_and_unicode(self):
        compiled = spec({"name": "all", "pattern": ".+", "flags": ["DOTALL"], "kind": "TEXT"})
        text = "é e\u0301 😀\r\nλ\t\x00"
        result = tokens(text, compiled)
        self.assertEqual([r.lexeme for r in result], [text])
        self.assertEqual(result[0].span.char_end, len(text))
        self.assertEqual((result[0].span.line_end, result[0].span.column_end), (2, 4))

    def test_crlf_split_across_matches(self):
        result = tokens("a\r\nb\rc\nd\t😀", chars_spec())
        boundaries = [(r.span.line_start, r.span.column_start) for r in result]
        boundaries.append((result[-1].span.line_end, result[-1].span.column_end))
        self.assertEqual(boundaries,
                         [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (3, 1),
                          (3, 2), (4, 1), (4, 2), (4, 3), (4, 4)])

    def test_empty_and_all_skipped_input(self):
        compiled = spec({"name": "space", "pattern": " +", "skip": True},
                        {"name": "word", "literal": "x", "kind": "X"})
        for text in ["", "   "]:
            result = records(text, compiled)
            self.assertIsInstance(result[0], StreamStart)
            self.assertEqual(result[0].kinds, ("X",))
            self.assertEqual((result[-1].token_count, result[-1].source_length), (0, len(text)))

    def test_failure_has_position_and_no_end(self):
        compiled = spec({"name": "a", "literal": "a", "kind": "A"})
        stream = tokenize("a\x1b", compiled, namespace="demo", stream_id="s0")
        self.assertIsInstance(next(stream), StreamStart)
        self.assertIsInstance(next(stream), Token)
        with self.assertRaises(LexicalError) as caught:
            next(stream)
        self.assertEqual((caught.exception.offset, caught.exception.line, caught.exception.column), (1, 1, 2))
        self.assertNotIn("\x1b", str(caught.exception))
        self.assertEqual(list(stream), [])

    def test_zero_width_losing_candidate_is_an_error(self):
        compiled = spec({"name": "a", "literal": "a", "kind": "A"},
                        {"name": "empty", "pattern": "(?=a)", "skip": True})
        with self.assertRaises(ConfigurationError) as caught:
            records("a", compiled)
        self.assertEqual((caught.exception.rule, caught.exception.offset), ("empty", 0))

    def test_preflight_limits_identifiers_and_surrogates(self):
        with self.assertRaises(LimitError):
            tokenize("ab", chars_spec(), namespace="n", stream_id="s", max_chars=1)
        with self.assertRaises(SourceError):
            tokenize("a\ud800", chars_spec(), namespace="n", stream_id="s")
        with self.assertRaises(ConfigurationError):
            tokenize("a", chars_spec(), namespace="$bad", stream_id="s")

    def test_random_lossless_reconstruction(self):
        rng = random.Random(713)
        compiled = spec({"name": "space", "pattern": r"\s+", "skip": True},
                        {"name": "rest", "pattern": r"\S+", "kind": "TEXT"})
        alphabet = "ab01 \t\r\nλ😀e\u0301\x00$();\\\""
        for _ in range(100):
            text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(150)))
            result = records(text, compiled)
            pieces = [r for r in result if isinstance(r, (Token, Skipped))]
            self.assertEqual("".join(r.lexeme for r in pieces), text)
            for piece in pieces:
                self.assertEqual(text[piece.span.char_start:piece.span.char_end], piece.lexeme)
            self.assertIsInstance(result[-1], StreamEnd)
