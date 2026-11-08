import io

from tokenizer import ConfigurationError, LimitError, SourceError, read_source, read_stream
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
