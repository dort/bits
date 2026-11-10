import io
import tracemalloc

from tokenizer import (ConfigurationError, DecodedStream, LimitError, SourceError,
                       read_source, read_stream)
from tests.support import TempCase


class SourceTests(TempCase):
    def test_file_and_chunks_preserve_text(self):
        text = "é😀\r\nx\ry\nz\t"
        path = self.directory / "input"
        path.write_bytes(text.encode("utf-8"))
        self.assertEqual(read_source(path).text, text)
        for size in [1, 2, 3, 4, 16, 65536]:
            with self.subTest(size=size):
                self.assertEqual(read_stream(io.BytesIO(path.read_bytes()), chunk_size=size).text, text)

    def test_explicit_encoding(self):
        self.assertEqual(read_stream(io.BytesIO(b'caf\xe9'), encoding="latin-1").text, "café")
        encoded = "hello λ".encode("utf-16")
        self.assertEqual(read_stream(io.BytesIO(encoded), encoding="utf-16", chunk_size=1).text, "hello λ")
        with self.assertRaises(SourceError):
            read_stream(io.BytesIO(b'caf\xe9'))
        with self.assertRaises(ConfigurationError):
            read_stream(io.BytesIO(b'abc'), encoding="not-an-encoding")
        with self.assertRaises(ConfigurationError):
            read_stream(io.BytesIO(b'00'), encoding="hex")
        with self.assertRaises(SourceError):
            read_stream(io.BytesIO(b'a\x00'), encoding="utf-16")

    def test_truncated_multibyte_error_location(self):
        with self.assertRaises(SourceError) as caught:
            read_stream(io.BytesIO(b'abc\xf0\x9f'), chunk_size=1)
        self.assertIn("byte 3", str(caught.exception))

    def test_limits(self):
        raw = "😀".encode()
        self.assertEqual(read_stream(io.BytesIO(raw), max_bytes=4, max_chars=1).text, "😀")
        for options in [{"max_bytes": 3}, {"max_chars": 0}]:
            with self.subTest(options=options), self.assertRaises(LimitError):
                read_stream(io.BytesIO(raw), **options)
        self.assertEqual(read_stream(io.BytesIO(b''), max_bytes=0, max_chars=0).text, "")
        for options in [{"max_bytes": -1}, {"max_chars": True}, {"chunk_size": 0}]:
            with self.subTest(options=options), self.assertRaises(ConfigurationError):
                read_stream(io.BytesIO(b''), **options)

    def test_missing_file_and_wrong_reader(self):
        with self.assertRaises(SourceError):
            read_source(self.directory / "absent")
        with self.assertRaises(SourceError):
            read_stream(io.StringIO("text"))

    def test_incremental_decoder_is_lazy_and_preserves_metadata(self):
        reader = io.BytesIO(b'abcdef')
        decoded = DecodedStream(reader, label="letters", encoding="UTF8", chunk_size=2,
                                max_bytes=None, max_chars=None)
        self.assertEqual(reader.tell(), 0)
        self.assertFalse(decoded.complete)
        self.assertEqual(next(decoded), "ab")
        self.assertEqual(reader.tell(), 2)
        self.assertEqual((decoded.byte_count, decoded.char_count), (2, 2))
        self.assertEqual("".join(decoded), "cdef")
        self.assertEqual((decoded.label, decoded.encoding), ("letters", "utf-8"))
        self.assertEqual((decoded.byte_count, decoded.char_count, decoded.complete), (6, 6, True))
        self.assertEqual(list(decoded), [])
        self.assertFalse(reader.closed)

    def test_incremental_decoding_across_codec_and_chunk_boundaries(self):
        text = "Aλ😀\r\nZ\r"
        for encoding in ["utf-8", "utf-8-sig", "utf-16", "utf-16-be", "utf-32"]:
            raw = text.encode(encoding)
            for size in [1, 2, 3, 4, 7, 65536]:
                with self.subTest(encoding=encoding, size=size):
                    decoded = DecodedStream(io.BytesIO(raw), encoding=encoding, chunk_size=size)
                    self.assertEqual("".join(decoded), text)
                    self.assertEqual((decoded.byte_count, decoded.char_count), (len(raw), len(text)))
                    self.assertTrue(decoded.complete)

    def test_decoder_failure_never_marks_completion(self):
        decoded = DecodedStream(io.BytesIO(b'abc\xf0\x9f'), chunk_size=1, label="truncated")
        prefix = []
        with self.assertRaises(SourceError) as caught:
            prefix.extend(decoded)
        self.assertEqual("".join(prefix), "abc")
        self.assertIn("byte 3", str(caught.exception))
        self.assertEqual(caught.exception.source, "truncated")
        self.assertFalse(decoded.complete)
        self.assertEqual(list(decoded), [])

    def test_character_limit_applies_before_a_chunk_is_yielded(self):
        decoded = DecodedStream(io.BytesIO(b'abcd'), chunk_size=2, max_chars=3)
        self.assertEqual(next(decoded), "ab")
        with self.assertRaises(LimitError):
            next(decoded)
        self.assertFalse(decoded.complete)

    def test_final_flush_emits_text_and_enforces_character_limit(self):
        # UTF-7 emits the pending character only when this source reaches EOF.
        decoded = DecodedStream(io.BytesIO(b'+AEI'), encoding="utf-7", chunk_size=1)
        self.assertEqual(list(decoded), ["B"])
        self.assertEqual((decoded.byte_count, decoded.char_count, decoded.complete), (4, 1, True))
        limited = DecodedStream(io.BytesIO(b'+AEI'), encoding="utf-7", max_chars=0)
        with self.assertRaises(LimitError):
            next(limited)
        self.assertFalse(limited.complete)

    def test_read_failure_after_prefix_preserves_source_and_incomplete_status(self):
        class FailingReader:
            def __init__(self):
                self.first = True

            def read(self, size):
                if self.first:
                    self.first = False
                    return b'abc'
                raise OSError("input disconnected")

        decoded = DecodedStream(FailingReader(), label="broken-source")
        self.assertEqual(next(decoded), "abc")
        with self.assertRaises(SourceError) as caught:
            next(decoded)
        self.assertEqual(caught.exception.source, "broken-source")
        self.assertIn("input disconnected", str(caught.exception))
        self.assertFalse(decoded.complete)

    def test_decoder_pending_buffer_is_bounded(self):
        # UTF-7 retains this unfinished shift sequence without emitting text.
        raw = b'+' + b'A' * 65536
        for consume in [lambda stream: "".join(DecodedStream(stream, encoding="utf-7",
                                                            max_bytes=None, max_chars=None)),
                        lambda stream: read_stream(stream, encoding="utf-7")]:
            with self.assertRaisesRegex(LimitError, "decoder.*buffer"):
                consume(io.BytesIO(raw))

    def test_invalid_configuration_precedes_reading(self):
        for options in [{"max_bytes": True}, {"max_chars": -1}, {"chunk_size": False},
                        {"encoding": "hex"}, {"encoding": "rot_13"}]:
            reader = io.BytesIO(b'abc')
            with self.subTest(options=options), self.assertRaises(ConfigurationError):
                DecodedStream(reader, **options)
            self.assertEqual(reader.tell(), 0)
        self.assertEqual(read_stream(io.BytesIO(b'abc'), max_bytes=None, max_chars=None).text, "abc")

    def test_incremental_working_memory_does_not_retain_source(self):
        class RepeatingReader:
            def __init__(self, size):
                self.remaining = size

            def read(self, size):
                count = min(size, self.remaining)
                self.remaining -= count
                return b'x' * count

        peaks = []
        for size in [256 * 1024, 8 * 1024 * 1024]:
            tracemalloc.start()
            try:
                decoded = DecodedStream(RepeatingReader(size), chunk_size=4096,
                                        max_bytes=None, max_chars=None)
                self.assertEqual(sum(map(len, decoded)), size)
                peaks.append(tracemalloc.get_traced_memory()[1])
            finally:
                tracemalloc.stop()
        self.assertLess(max(peaks), 512 * 1024, peaks)
