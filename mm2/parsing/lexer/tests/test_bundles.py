from dataclasses import replace
import json
import random
import tracemalloc
from unittest.mock import patch

from tokenizer import (BundleReader, ConfigurationError, DroppedEmpty, Gap,
                       LimitError, OutputError, SourceEnd, SourcePiece, SourceStart,
                       StreamEnd, Token, UnitStart, iter_jsonl, iter_mm2,
                       source_records, write_bundle)
from tests.support import TempCase, chars_spec


class BundleTests(TempCase):
    def records(self, pieces=None, **options):
        if pieces is None:
            pieces = [SourcePiece("a", following="b"), SourcePiece("b")]
        return source_records(pieces, chars_spec(), namespace="demo", source_id="input",
                              max_units=100, **options)

    def bundle(self, pieces=None, **options):
        path = self.directory / "bundle"
        manifest = write_bundle(self.records(pieces, **options), path)
        return path, manifest

    def test_multiple_units_gaps_and_empties_reconstruct_and_index_exactly(self):
        pieces = [SourcePiece("a\r", following="\n"),
                  SourcePiece("", disposition="dropped-empty", following="\n"),
                  SourcePiece("\n", disposition="gap", following="λ"),
                  SourcePiece("λ😀"), SourcePiece("")]
        path, manifest = self.bundle(pieces)
        self.assertEqual(manifest["bundle_version"], 2)
        self.assertEqual((manifest["unit_count"], manifest["piece_count"],
                          manifest["source_length"], manifest["gap_count"],
                          manifest["dropped_empty_count"]), (3, 5, 5, 1, 1))
        self.assertNotIn("streams", manifest)
        self.assertEqual({p.name for p in path.iterdir()},
                         {"tokens.jsonl", "tokens.mm2", "streams.jsonl", "manifest.json"})
        reader = BundleReader(path)
        entries = list(reader.iter_entries())
        self.assertEqual([entry["stream_id"] for entry in entries],
                         ["input_u0", "input_u1", "input_u2"])
        self.assertEqual([entry["piece_index"] for entry in entries], [0, 3, 4])
        for entry, expected in zip(entries, ["a\r", "λ😀", ""]):
            stream = reader.read_stream(entry)
            self.assertEqual("".join(r.lexeme for r in stream.records if isinstance(r, Token)), expected)
            self.assertEqual(stream.end.token_count, len(expected))
            self.assertTrue(all(line.startswith(b"(lex-") for line in stream.mm2.splitlines()))
            self.assertEqual(stream.unit.stream_id, entry["stream_id"])
            with (path / "tokens.mm2").open("rb") as raw:
                raw.seek(entry["mm2"]["start"])
                self.assertEqual(raw.read(entry["mm2"]["end"] - raw.tell()), stream.mm2)
        records = list(reader.iter_records())
        self.assertEqual("".join(r.lexeme if isinstance(r, Token) else r.text
                                 for r in records if isinstance(r, (Token, Gap))), "a\r\nλ😀")
        units = [r for r in records if isinstance(r, UnitStart)]
        self.assertEqual((units[0].span.line_end, units[0].span.column_end), (1, 3))
        self.assertEqual((units[1].span.line_start, units[1].span.column_start), (2, 1))
        self.assertIsInstance(records[0], SourceStart)
        self.assertIsInstance(records[-1], SourceEnd)
        self.assertEqual(sum(isinstance(r, DroppedEmpty) for r in records), 1)

    def test_zero_units_and_kept_empty_unit_are_distinct(self):
        for name, pieces, count in [("none", [], 0), ("kept", [SourcePiece("")], 1),
                                    ("dropped", [SourcePiece("", disposition="dropped-empty")], 0)]:
            with self.subTest(name=name):
                path = self.directory / name
                manifest = write_bundle(self.records(pieces), path)
                self.assertEqual(manifest["unit_count"], count)
                reader = BundleReader(path)
                self.assertEqual(len(list(reader.iter_entries())), count)
                self.assertIsInstance(list(reader.iter_records())[-1], SourceEnd)
                mm2 = (path / "tokens.mm2").read_text()
                self.assertIn(f"(split-end demo input {count})", mm2)
                self.assertEqual("(lex-end " in mm2, bool(count))

    def test_caller_identity_is_preserved_and_duplicates_fail(self):
        path, _ = self.bundle([SourcePiece("x", stream_id="chosen")], identity_policy="caller")
        entry = next(BundleReader(path).iter_entries())
        self.assertEqual(entry["stream_id"], "chosen")
        duplicate = self.records([SourcePiece("x", stream_id="same", following="y"),
                                  SourcePiece("y", stream_id="same")], identity_policy="caller")
        with self.assertRaisesRegex(OutputError, "duplicate"):
            write_bundle(duplicate, self.directory / "duplicate")
        self.assertFalse((self.directory / "duplicate").exists())

    def test_mixed_identity_policies_and_generated_spelling_are_rejected(self):
        for pieces, options in [([SourcePiece("a", stream_id="input_u0")], {}),
                                ([SourcePiece("a")], {"identity_policy": "caller"})]:
            with self.subTest(options=options), self.assertRaises(OutputError):
                list(iter_mm2(self.records(pieces, **options)))
        original = list(self.records())
        unit_index = next(i for i, r in enumerate(original) if isinstance(r, UnitStart))
        for fields in [{"stream_id": "arbitrary"}, {"unit_index": 3}, {"namespace": "other"}]:
            changed = list(original)
            changed[unit_index] = replace(changed[unit_index], **fields)
            with self.subTest(fields=fields), self.assertRaises(OutputError):
                list(iter_jsonl(changed))

    def test_identity_and_unit_limits_are_checked_before_source_consumption(self):
        def untouched():
            self.fail("invalid source configuration consumed the producer")
            yield SourcePiece("x")
        for options in [{"max_units": 0}, {"max_units": True},
                        {"stream_base": "a" * 30, "max_units": 1000}]:
            with self.subTest(options=options), self.assertRaises(ConfigurationError):
                source_records(untouched(), chars_spec(), namespace="demo", source_id="s", **options)
        records = source_records([SourcePiece("a"), SourcePiece("b")], chars_spec(),
                                 namespace="demo", source_id="s", max_units=1)
        with self.assertRaisesRegex(LimitError, "unit"):
            write_bundle(records, self.directory / "too-many")

    def test_caller_identity_cap_and_memory(self):
        from tokenizer.envelope import IdentityTracker
        tracker = IdentityTracker("caller", namespace="demo", stream_base=None, max_units=200000)
        tracemalloc.start()
        try:
            for index in range(100000):
                tracker.add("demo", f"s{index}", index)
            peak = tracemalloc.get_traced_memory()[1]
            with self.assertRaisesRegex(LimitError, "100000"):
                tracker.add("demo", "overflow", 100000)
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 32 * 1024 * 1024)
        self.assertEqual(tracker.count, 100000)

    def test_generated_identity_tracking_does_not_retain_ids(self):
        from tokenizer.envelope import IdentityTracker
        tracker = IdentityTracker("generated", namespace="demo", stream_base="batch", max_units=200000)
        tracemalloc.start()
        try:
            for index in range(100000):
                tracker.add("demo", f"batch_u{index}", index)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 64 * 1024)
        self.assertEqual(tracker.count, 100000)

    def test_source_counts_spans_context_and_order_are_checked(self):
        original = list(self.records([SourcePiece("a\r", following="\n"), SourcePiece("\nb")]))
        unit_indices = [i for i, r in enumerate(original) if isinstance(r, UnitStart)]
        cases = [original[:-1], original + [original[-1]], original[1:],
                 original[:-1] + [replace(original[-1], unit_count=99)]]
        for fields in [{"piece_index": 3}, {"following": "x"},
                       {"span": replace(original[unit_indices[0]].span, char_end=99)},
                       {"span": replace(original[unit_indices[0]].span, line_end=2)}]:
            changed = list(original)
            changed[unit_indices[0]] = replace(changed[unit_indices[0]], **fields)
            cases.append(changed)
        changed = list(original)
        changed[unit_indices[1]] = replace(changed[unit_indices[1]],
                                          span=replace(changed[unit_indices[1]].span, char_start=1))
        cases.append(changed)
        for records in cases:
            emitted = []
            with self.subTest(records=records), self.assertRaises(OutputError):
                for line in iter_mm2(records):
                    emitted.append(line)
            self.assertFalse(any(line.startswith("(split-end ") for line in emitted))

    def test_local_coordinate_corruption_is_rejected(self):
        records = list(self.records([SourcePiece("a\r\nb")]))
        index = next(i for i, r in enumerate(records) if isinstance(r, Token))
        records[index] = replace(records[index], span=replace(records[index].span, column_end=99))
        with self.assertRaises(OutputError):
            list(iter_jsonl(records))

    def test_completion_is_held_through_boundary_and_producer_exhaustion(self):
        records = list(self.records([SourcePiece("a")]))
        def late_failure():
            yield from records
            raise OSError("late producer failure")
        emitted = []
        with self.assertRaises(OSError):
            for line in iter_mm2(late_failure()):
                emitted.append(line)
        self.assertTrue(any(line.startswith("(lex-end ") for line in emitted))
        self.assertFalse(any(line.startswith("(split-end ") for line in emitted))
        with self.assertRaises(OutputError):
            write_bundle(late_failure(), self.directory / "failed")
        self.assertEqual(list(self.directory.iterdir()), [])
        # An invalid outer boundary cannot release the previous stream end.
        emitted = []
        with self.assertRaises(OutputError):
            for line in iter_mm2(records[:-1] + [records[1]]):
                emitted.append(line)
        self.assertFalse(any(line.startswith("(lex-end ") for line in emitted))

    def test_reader_rejects_old_versions_bad_ranges_and_payload_injection(self):
        path, manifest = self.bundle()
        entry = next(BundleReader(path).iter_entries())
        reader = BundleReader(path)
        for value in [{"start": -1, "end": 2}, {"start": 0, "end": 10**12},
                      {"start": True, "end": 2}]:
            with self.subTest(value=value), self.assertRaises(OutputError):
                reader.read_stream(dict(entry, mm2=value))
        raw = (path / "tokens.mm2").read_bytes()
        corrupt = raw.replace(b"(lex-token", b"(exe-token", 1)
        (path / "tokens.mm2").write_bytes(corrupt)
        with self.assertRaises(OutputError):
            reader.read_stream(entry)
        (path / "tokens.mm2").write_bytes(raw)
        for version in [1, 3, True, 2.0]:
            with self.subTest(version=version):
                (path / "manifest.json").write_text(json.dumps(dict(manifest, bundle_version=version)))
                with self.assertRaises(ConfigurationError):
                    BundleReader(path)

    def test_reader_checks_declared_limits_before_loading_payload(self):
        path, _ = self.bundle([SourcePiece("abc")])
        reader = BundleReader(path)
        entry = next(reader.iter_entries())
        with patch.object(reader, "_read_range", side_effect=AssertionError("read too early")):
            with self.assertRaises(LimitError):
                reader.read_stream(entry, max_tokens=2)
            with self.assertRaises(LimitError):
                reader.read_stream(entry, max_chars=2)
            with self.assertRaises(LimitError):
                reader.read_stream(entry, max_payload_bytes=1)

    def test_reader_rejects_corrupt_index_and_json_metadata(self):
        path, _ = self.bundle([SourcePiece("ab")])
        entry = next(BundleReader(path).iter_entries())
        for fields in [{"stream_id": "other"}, {"token_count": 1},
                       {"kinds": ["UNDECLARED"]}, {"spec_fingerprint": "0" * 64}]:
            with self.subTest(fields=fields), self.assertRaises(OutputError):
                BundleReader(path).read_stream(dict(entry, **fields))
        raw = (path / "tokens.jsonl").read_bytes()
        (path / "tokens.jsonl").write_bytes(raw.replace(b'"rule":"char"', b'"rule":"$bad"', 1))
        with self.assertRaises(OutputError):
            BundleReader(path).read_stream(entry)

    def test_full_archive_reader_checks_summary_and_trailing_data(self):
        path, manifest = self.bundle()
        (path / "manifest.json").write_text(json.dumps(dict(manifest, token_count=99)))
        with self.assertRaises(OutputError):
            list(BundleReader(path).iter_records())
        (path / "manifest.json").write_text(json.dumps(manifest))
        with (path / "streams.jsonl").open("ab") as output:
            output.write(b'{}\n')
        with self.assertRaises(OutputError):
            list(BundleReader(path).iter_entries())

    def test_raw_stream_is_not_a_second_bundle_format(self):
        from tokenizer import tokenize
        records = tokenize("a", chars_spec(), namespace="n", stream_id="s")
        with self.assertRaisesRegex(OutputError, "source"):
            write_bundle(records, self.directory / "old")

    def test_random_piece_boundaries_preserve_source_coordinates_and_text(self):
        from tokenizer.model import advance_location
        rng = random.Random(9217)
        for case in range(20):
            text = "".join(rng.choice("ab\r\nλ😀") for _ in range(40))
            pieces = []
            offset = 0
            while offset < len(text):
                end = min(len(text), offset + rng.randrange(1, 6))
                if rng.randrange(3) == 0:
                    pieces.append(SourcePiece("", disposition="dropped-empty", following=text[offset]))
                pieces.append(SourcePiece(text[offset:end], following=text[end:end + 1],
                                          disposition=rng.choice(["unit", "gap"])))
                offset = end
            path = self.directory / f"random{case}"
            write_bundle(self.records(pieces), path)
            decoded = list(BundleReader(path).iter_records())
            self.assertEqual("".join(r.lexeme if isinstance(r, Token) else r.text
                                     for r in decoded if isinstance(r, (Token, Gap))), text)
            for record in decoded:
                if isinstance(record, (UnitStart, Gap, DroppedEmpty)):
                    self.assertEqual((record.span.line_start, record.span.column_start),
                                     advance_location(text, 0, record.span.char_start, 1, 1))
                    self.assertEqual((record.span.line_end, record.span.column_end),
                                     advance_location(text, 0, record.span.char_end, 1, 1))

    def test_index_order_ranges_and_duplicate_keys_are_validated(self):
        path, manifest = self.bundle()
        raw_index = (path / "streams.jsonl").read_bytes()
        entries = [json.loads(line) for line in raw_index.splitlines()]
        for changed in [[entries[1], entries[0]], [entries[0], entries[0]]]:
            (path / "streams.jsonl").write_text("".join(json.dumps(e) + "\n" for e in changed))
            # Preserve the expected size so order checks inspect the edited rows.
            (path / "manifest.json").write_text(json.dumps(dict(manifest, files=dict(
                manifest["files"], **{"streams.jsonl": dict(manifest["files"]["streams.jsonl"],
                    bytes=(path / "streams.jsonl").stat().st_size)}))))
            with self.assertRaises(OutputError):
                list(BundleReader(path).iter_entries())
        (path / "streams.jsonl").write_bytes(raw_index)
        (path / "manifest.json").write_text(json.dumps(manifest)[:-1] + ',"bundle_version":2}')
        with self.assertRaisesRegex(OutputError, "duplicate"):
            BundleReader(path)

    def test_json_parser_resource_errors_have_named_bundle_diagnostics(self):
        from tokenizer.serialize import record_from_json
        path, _ = self.bundle()
        cases = ['{"bundle_version":2,"value":' + '[' * 2000 + '0' + ']' * 2000 + '}',
                 '{"bundle_version":2,"value":' + '9' * 5000 + '}']
        for raw in cases:
            with self.subTest(kind=raw[:20]):
                (path / "manifest.json").write_text(raw)
                with self.assertRaises(OutputError):
                    BundleReader(path)
                with self.assertRaises(OutputError):
                    record_from_json(raw)

    def test_gap_limits_and_dropped_empty_text_are_explicit(self):
        for piece in [SourcePiece("x", disposition="dropped-empty"),
                      SourcePiece("", disposition="gap"),
                      SourcePiece("x", disposition="gap", stream_id="invalid")]:
            with self.subTest(piece=piece), self.assertRaises(OutputError):
                list(iter_jsonl(self.records([piece])))
        with self.assertRaises(LimitError):
            list(iter_jsonl(self.records([SourcePiece("x" * 65537, disposition="gap")])))
