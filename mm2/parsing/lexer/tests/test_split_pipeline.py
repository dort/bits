import io
import tracemalloc

from tokenizer import (BundleReader, DecodedStream, LexicalError, LimitError, SourceError,
                       Token, Skipped, Gap, UnitStart, source_records, write_bundle)
from tokenizer.model import advance_location
from tokenizer.split_spec import compile_split_spec
from tokenizer.splitter import split_chunks
from tests.support import TempCase, chars_spec, spec


class SplitPipelineTests(TempCase):
    def records(self, text, split, lexical=None, **options):
        chunks = (text[i:i + 1] for i in range(len(text)))
        return source_records(split_chunks(chunks, split, source="input.txt"), lexical or chars_spec(),
                              namespace="demo", source_id="input", source="input.txt",
                              max_unit_chars=split.max_unit_chars, split_fingerprint=split.fingerprint,
                              **options)

    def test_bundle_reconstruction_positions_fingerprint_and_index(self):
        text = "λ\r\n😀\r\n\r\nend"
        for literal in ["\r", "\n", "\r\n"]:
            for retain in ["end", "gap"]:
                for empties in ["keep", "drop"]:
                    split = compile_split_spec({"version": 1, "separator": {"literal": literal},
                                                "retain": retain, "empty_units": empties, "max_unit_chars": 16})
                    path = self.directory / f"bundle-{len(list(self.directory.iterdir()))}"
                    manifest = write_bundle(self.records(text, split), path)
                    reader = BundleReader(path)
                    records = list(reader.iter_records())
                    reconstructed = "".join(r.lexeme if isinstance(r, (Token, Skipped)) else r.text
                                            for r in records if isinstance(r, (Token, Skipped, Gap)))
                    self.assertEqual(reconstructed, text)
                    self.assertEqual(manifest["split_fingerprint"], split.fingerprint)
                    for record in records:
                        if isinstance(record, (UnitStart, Gap)):
                            span = record.span
                            self.assertEqual((span.line_start, span.column_start),
                                             advance_location(text, 0, span.char_start, 1, 1))
                            self.assertEqual((span.line_end, span.column_end),
                                             advance_location(text, 0, span.char_end, 1, 1))
                            self.assertEqual(record.following, text[span.char_end:span.char_end + 1])
                    for index, entry in enumerate(reader.iter_entries()):
                        unit = reader.read_stream(entry)
                        self.assertEqual(unit.unit.stream_id, f"input_u{index}")
                        self.assertEqual(unit.end.source_length, unit.unit.span.char_end - unit.unit.span.char_start)

    def test_lexical_errors_have_absolute_and_local_coordinates(self):
        lexical = spec({"name": "letters", "pattern": "[a-z]+", "kind": "WORD"},
                       {"name": "space", "pattern": r"\s+", "skip": True})
        for separator, text, expected in [(";", "a\r\nb;xx@", (7, 2, 5, 2, 1, 3)),
                                           ("\r", "ok\r\nx@", (5, 2, 2, 2, 2, 2))]:
            split = compile_split_spec({"version": 1, "separator": {"literal": separator},
                                        "retain": "gap", "max_unit_chars": 32})
            with self.assertRaises(LexicalError) as caught:
                list(self.records(text, split, lexical))
            error = caught.exception
            self.assertEqual((error.offset, error.line, error.column,
                              error.local_offset, error.local_line, error.local_column), expected)
            self.assertEqual((error.unit_index, error.stream_id), (1, "input_u1"))
            self.assertIn("local", str(error))

    def test_late_failures_publish_nothing_and_remove_staging(self):
        split = compile_split_spec({"version": 1, "separator": {"literal": "\n"}, "max_unit_chars": 4})
        lexical = spec({"name": "text", "pattern": "[a-z\\n]+", "kind": "TEXT"})
        cases = [(self.records("a\nb\nc@", split, lexical), LexicalError),
                 (self.records("a\nb\nccccc", split), LimitError),
                 (self.records("a\nb\nc", split, max_units=2), LimitError)]
        decoded = DecodedStream(io.BytesIO(b'a\nb\n\xf0\x9f'), chunk_size=1)
        cases.append((source_records(split_chunks(decoded, split), lexical,
                                     namespace="demo", source_id="input"), SourceError))
        for records, error_type in cases:
            output = self.directory / "never-published"
            with self.assertRaises(error_type):
                write_bundle(records, output)
            self.assertFalse(output.exists())
            self.assertEqual(list(self.directory.glob(".never-published.*")), [])

    def test_splitter_memory_does_not_grow_with_unit_count(self):
        split = compile_split_spec({"version": 1, "separator": {"literal": "\n"}, "max_unit_chars": 128})
        chunk = ("x" * 63 + "\n") * 64
        peaks = []
        for count in [8, 256]:
            tracemalloc.start()
            try:
                total = sum(len(piece.text) for piece in split_chunks((chunk for _ in range(count)), split))
                self.assertEqual(total, count * len(chunk))
                peaks.append(tracemalloc.get_traced_memory()[1])
            finally:
                tracemalloc.stop()
        self.assertLess(max(peaks), 256 * 1024, peaks)
