"""Version-2 source archives with a streamed index and bounded unit reads."""

from dataclasses import asdict, dataclass, fields
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .config import loads_json
from .envelope import (IdentityTracker, UnitValidator, check_piece,
                       check_source_start, checked_source_records)
from .model import (BUNDLE_VERSION, DEFAULT_MAX_CHARS, ConfigurationError,
                    LimitError, OutputError, Skipped, SourceEnd, SourceStart,
                    StreamEnd, StreamStart, UnitStart, require_python314,
                    validate_limit)
from .serialize import (DIGEST, _count, _fact, _json_line, _mm2_lines,
                        _publish_directory, record_from_json)


MAX_METADATA_BYTES = 65536
MAX_RECORD_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_TOKENS = 1_000_000
PAYLOAD_FILES = ("tokens.jsonl", "tokens.mm2", "streams.jsonl")
UNIT_FIELDS = {field.name for field in fields(UnitStart)}
INDEX_FIELDS = UNIT_FIELDS | {"token_count", "source_length", "skipped_span_count",
                             "spec_fingerprint", "kinds", "jsonl", "mm2"}


def _source_mm2_lines(record):
    if isinstance(record, SourceStart):
        yield _fact("split-stream", record.namespace, record.source_id, 1)
        if record.split_fingerprint is not None:
            digest = record.split_fingerprint
            yield _fact("split-spec", record.namespace, record.source_id, "sha256",
                        "h" + digest[:32], "h" + digest[32:])
    elif isinstance(record, UnitStart):
        yield _fact("split-unit", record.namespace, record.source_id, record.unit_index, record.stream_id)
        yield _fact("split-next", record.namespace, record.source_id, record.unit_index, record.unit_index + 1)
        yield _fact("split-span", record.namespace, record.source_id, record.unit_index,
                    record.span.char_start, record.span.char_end)
    elif isinstance(record, SourceEnd):
        yield _fact("split-end", record.namespace, record.source_id, record.unit_count)
    elif hasattr(record, "stream_id"):
        yield from _mm2_lines(record)


def _record_bytes(record):
    raw = _json_line(record).encode("ascii")
    ceiling = MAX_METADATA_BYTES if isinstance(record, (SourceStart, UnitStart, StreamStart)) else MAX_RECORD_BYTES
    if len(raw) > ceiling:
        raise LimitError(f"serialized record exceeds {ceiling} bytes", field="record_bytes")
    return raw


def iter_jsonl(records):
    require_python314()
    for record in checked_source_records(records):
        yield _record_bytes(record).decode("ascii")


def iter_mm2(records):
    require_python314()
    for record in checked_source_records(records):
        yield from _source_mm2_lines(record)


def _summary(start, end):
    result = asdict(start) | asdict(end)
    del result["type"]
    return result


def _index_entry(unit, start, end, skipped, json_start, json_end, mm2_start, mm2_end):
    return dict(asdict(unit), type="stream-index", token_count=end.token_count,
                source_length=end.source_length, skipped_span_count=skipped,
                spec_fingerprint=start.spec_fingerprint, kinds=list(start.kinds),
                jsonl=dict(start=json_start, end=json_end), mm2=dict(start=mm2_start, end=mm2_end))


def _metadata_bytes(value):
    raw = (json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")
    if len(raw) > MAX_METADATA_BYTES:
        raise LimitError(f"metadata record exceeds {MAX_METADATA_BYTES} bytes", field="metadata_bytes")
    return raw


class _Output:
    def __init__(self, file):
        self.file = file
        self.size = 0
        self.digest = hashlib.sha256()

    def write(self, raw):
        self.file.write(raw)
        self.size += len(raw)
        self.digest.update(raw)

    def metadata(self):
        return dict(bytes=self.size, sha256=self.digest.hexdigest())


def write_bundle(records, output_dir):
    """Publish one complete source as four files, without retaining its index."""
    require_python314()
    destination = Path(output_dir).absolute()
    try:
        if os.path.lexists(destination):
            raise OutputError("output directory already exists", source=str(destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f".{destination.name}.", dir=destination.parent) as temporary:
            staging = Path(temporary)
            with (staging.joinpath("tokens.jsonl").open("wb") as json_file,
                  staging.joinpath("tokens.mm2").open("wb") as mm2_file,
                  staging.joinpath("streams.jsonl").open("wb") as index_file):
                jsonl, mm2, index = _Output(json_file), _Output(mm2_file), _Output(index_file)
                for record in checked_source_records(records):
                    if isinstance(record, SourceStart):
                        source_start = record
                    elif isinstance(record, UnitStart):
                        unit, json_start, skipped = record, jsonl.size, 0
                    elif isinstance(record, StreamStart):
                        stream_start, mm2_start = record, mm2.size
                    elif isinstance(record, Skipped):
                        skipped += 1
                    jsonl.write(_record_bytes(record))
                    for line in _source_mm2_lines(record):
                        mm2.write(line.encode("ascii"))
                    if isinstance(record, StreamEnd):
                        entry = _index_entry(unit, stream_start, record, skipped,
                                             json_start, jsonl.size, mm2_start, mm2.size)
                        index.write(_metadata_bytes(entry))
                    elif isinstance(record, SourceEnd):
                        manifest = _summary(source_start, record)
                manifest["files"] = {name: output.metadata() for name, output in
                                     zip(PAYLOAD_FILES, (jsonl, mm2, index))}
            staging.joinpath("manifest.json").write_bytes(_metadata_bytes(manifest))
            _publish_directory(staging, destination)
        return manifest
    except OSError as error:
        raise OutputError(str(error), source=str(destination)) from error


def _object(raw, label):
    try:
        value = loads_json(raw, source=label)
    except (ConfigurationError, ValueError, RecursionError) as error:
        raise OutputError(f"invalid bundle JSON: {error}", source=label) from error
    if not isinstance(value, dict):
        raise OutputError("bundle metadata must be a JSON object", source=label)
    return value


@dataclass(frozen=True, slots=True)
class BundleStream:
    unit: UnitStart
    start: StreamStart
    end: StreamEnd
    records: tuple
    mm2: bytes


class BundleReader:
    """Read completed v2 metadata; validate each requested bounded payload."""

    def __init__(self, path):
        require_python314()
        self.path = Path(path)
        try:
            with self.path.joinpath("manifest.json").open("rb") as file:
                raw = file.read(MAX_METADATA_BYTES + 1)
            if len(raw) > MAX_METADATA_BYTES:
                raise LimitError("bundle manifest exceeds metadata limit", field="metadata_bytes")
            self.manifest = _object(raw, str(self.path / "manifest.json"))
            version = self.manifest.get("bundle_version")
            if type(version) is not int or version != BUNDLE_VERSION:
                raise ConfigurationError("requires bundle version 2", field="bundle_version")
            start_fields = {field.name for field in fields(SourceStart)} - {"type"}
            end_fields = {field.name for field in fields(SourceEnd)} - {"type"}
            if set(self.manifest) != start_fields | end_fields | {"files"}:
                raise OutputError("invalid bundle manifest fields")
            self.start = record_from_json(json.dumps(dict(
                {name: self.manifest[name] for name in start_fields}, type="source-start")))
            self.end = record_from_json(json.dumps(dict(
                {name: self.manifest[name] for name in end_fields}, type="source-end")))
            check_source_start(self.start)
            for name in end_fields - {"namespace", "source_id", "complete"}:
                if not _count(self.manifest[name]):
                    raise OutputError(f"invalid manifest count {name}")
            if self.end.line_end < 1 or self.end.column_end < 1 or self.end.unit_count > self.start.max_units:
                raise OutputError("invalid manifest coordinates or unit count")
            file_info = self.manifest["files"]
            if not isinstance(file_info, dict) or set(file_info) != set(PAYLOAD_FILES):
                raise OutputError("invalid manifest payload files")
            for name in PAYLOAD_FILES:
                info = file_info[name]
                if (not isinstance(info, dict) or set(info) != {"bytes", "sha256"} or
                        not _count(info["bytes"]) or not isinstance(info["sha256"], str) or
                        DIGEST.fullmatch(info["sha256"]) is None):
                    raise OutputError("invalid payload size or digest")
                self._check_file_size(name)
        except OSError as error:
            raise OutputError(str(error), source=str(self.path)) from error

    def _check_file_size(self, name):
        if self.path.joinpath(name).stat().st_size != self.manifest["files"][name]["bytes"]:
            raise OutputError(f"payload size disagrees with manifest: {name}")

    def _range(self, entry, key, name):
        value = entry[key]
        if (not isinstance(value, dict) or set(value) != {"start", "end"} or
                not _count(value["start"]) or not _count(value["end"]) or
                not 0 <= value["start"] < value["end"] <= self.manifest["files"][name]["bytes"]):
            raise OutputError(f"invalid {key} byte range")
        return value["start"], value["end"]

    def _entry(self, entry):
        if not isinstance(entry, dict) or set(entry) != INDEX_FIELDS or entry["type"] != "stream-index":
            raise OutputError("invalid stream index fields")
        unit = record_from_json(json.dumps(dict({name: entry[name] for name in UNIT_FIELDS}, type="unit-start")))
        check_piece(self.start, unit)
        if unit.unit_index >= self.end.unit_count or unit.piece_index >= self.end.piece_count:
            raise OutputError("index ordinal exceeds source counts")
        if unit.span.char_end > self.end.source_length:
            raise OutputError("indexed span exceeds source length")
        if self.start.identity_policy == "generated" and unit.stream_id != f"{self.start.stream_base}_u{unit.unit_index}":
            raise OutputError("indexed generated ID disagrees with base and index")
        if (entry["spec_fingerprint"] != self.start.spec_fingerprint or
                entry["kinds"] != list(self.start.kinds)):
            raise OutputError("indexed fingerprint or kind catalog disagrees with source")
        for name in ("token_count", "source_length", "skipped_span_count"):
            if not _count(entry[name]):
                raise OutputError(f"invalid indexed count {name}")
        if (entry["source_length"] != unit.span.char_end - unit.span.char_start or
                entry["token_count"] + entry["skipped_span_count"] > entry["source_length"]):
            raise OutputError("indexed counts disagree with source span")
        self._range(entry, "jsonl", "tokens.jsonl")
        self._range(entry, "mm2", "tokens.mm2")
        return unit

    def _check_digest(self, name, size, digest):
        if dict(bytes=size, sha256=digest.hexdigest()) != self.manifest["files"][name]:
            raise OutputError(f"payload digest or length disagrees with manifest: {name}")

    def iter_entries(self):
        """Stream metadata; exhaustion also verifies index digest and aggregate counts."""
        tracker = IdentityTracker(self.start.identity_policy, namespace=self.start.namespace,
                                  stream_base=self.start.stream_base, max_units=self.start.max_units)
        previous_piece = -1
        previous_char = json_end = mm2_end = token_count = skipped = size = 0
        digest = hashlib.sha256()
        try:
            with self.path.joinpath("streams.jsonl").open("rb") as file:
                while raw := file.readline(MAX_METADATA_BYTES + 1):
                    if len(raw) > MAX_METADATA_BYTES or not raw.endswith(b"\n"):
                        raise OutputError("oversized or unterminated index row")
                    size += len(raw)
                    digest.update(raw)
                    entry = _object(raw, "streams.jsonl")
                    unit = self._entry(entry)
                    tracker.add(unit.namespace, unit.stream_id, unit.unit_index)
                    if (unit.piece_index <= previous_piece or unit.span.char_start < previous_char or
                            entry["jsonl"]["start"] < json_end or entry["mm2"]["start"] < mm2_end):
                        raise OutputError("stream index order or byte ranges overlap")
                    previous_piece, previous_char = unit.piece_index, unit.span.char_end
                    json_end, mm2_end = entry["jsonl"]["end"], entry["mm2"]["end"]
                    token_count += entry["token_count"]
                    skipped += entry["skipped_span_count"]
                    yield entry
            self._check_digest("streams.jsonl", size, digest)
            if (tracker.count, token_count, skipped) != (self.end.unit_count, self.end.token_count,
                                                        self.end.skipped_span_count):
                raise OutputError("stream index totals disagree with manifest")
        except OSError as error:
            raise OutputError(str(error), source=str(self.path)) from error

    def _read_range(self, name, bounds):
        try:
            self._check_file_size(name)
            with self.path.joinpath(name).open("rb") as file:
                file.seek(bounds["start"])
                raw = file.read(bounds["end"] - bounds["start"])
            if len(raw) != bounds["end"] - bounds["start"]:
                raise OutputError("truncated payload range")
            return raw
        except OSError as error:
            raise OutputError(str(error), source=str(self.path / name)) from error

    def read_stream(self, entry, *, max_tokens=DEFAULT_MAX_TOKENS, max_chars=DEFAULT_MAX_CHARS,
                    max_payload_bytes=DEFAULT_MAX_PAYLOAD_BYTES):
        """Check limits before reads, then validate one unit and its exact lexical facts."""
        for name, value in (("max_tokens", max_tokens), ("max_chars", max_chars),
                            ("max_payload_bytes", max_payload_bytes)):
            validate_limit(value, name)
        unit = self._entry(entry)
        for name, actual, limit in (("max_tokens", entry["token_count"], max_tokens),
                                    ("max_chars", entry["source_length"], max_chars),
                                    ("max_payload_bytes", sum(entry[key]["end"] - entry[key]["start"]
                                                               for key in ("jsonl", "mm2")), max_payload_bytes)):
            if actual > limit:
                raise LimitError(f"unit exceeds {name}={limit}", field=name)
        raw_json = self._read_range("tokens.jsonl", entry["jsonl"])
        if not raw_json.endswith(b"\n"):
            raise OutputError("unit JSON range is not newline terminated")
        records = tuple(record_from_json(line) for line in raw_json.splitlines())
        if not records or records[0] != unit:
            raise OutputError("unit JSON provenance disagrees with index")
        checker = UnitValidator(self.start, unit)
        for record in records[1:]:
            checker.push(record)
        if checker.stream.end is None:
            raise OutputError("indexed stream is incomplete")
        if (checker.stream.token_count, checker.stream.char_count, checker.stream.skipped_count) != (
                entry["token_count"], entry["source_length"], entry["skipped_span_count"]):
            raise OutputError("indexed counts disagree with stream records")
        mm2 = self._read_range("tokens.mm2", entry["mm2"])
        offset = 0
        for record in records[1:]:
            for line in _mm2_lines(record):
                expected = line.encode("ascii")
                if mm2[offset:offset + len(expected)] != expected:
                    raise OutputError("MM2 slice disagrees with validated token records")
                offset += len(expected)
        if offset != len(mm2):
            raise OutputError("extra facts in MM2 stream slice")
        return BundleStream(unit, checker.stream.start, checker.stream.end, records[1:], mm2)

    def iter_records(self):
        """Validate the entire archive incrementally, including gaps and all three digests."""
        json_digest, mm2_digest = hashlib.sha256(), hashlib.sha256()
        json_size = mm2_size = 0
        entries = self.iter_entries()
        try:
            with (self.path.joinpath("tokens.jsonl").open("rb") as json_file,
                  self.path.joinpath("tokens.mm2").open("rb") as mm2_file):
                def records():
                    while raw := json_file.readline(MAX_RECORD_BYTES + 1):
                        if len(raw) > MAX_RECORD_BYTES or not raw.endswith(b"\n"):
                            raise OutputError("oversized or unterminated source record")
                        record = record_from_json(raw)
                        if raw != _record_bytes(record):
                            raise OutputError("source records must use canonical JSON Lines encoding")
                        yield record

                for record in checked_source_records(records()):
                    if isinstance(record, SourceStart) and record != self.start:
                        raise OutputError("source header disagrees with manifest")
                    if isinstance(record, UnitStart):
                        entry = next(entries, None)
                        if entry is None or self._entry(entry) != record:
                            raise OutputError("source unit disagrees with stream index")
                        unit, json_start, skipped = record, json_size, 0
                    elif isinstance(record, StreamStart):
                        stream_start, mm2_start = record, mm2_size
                    elif isinstance(record, Skipped):
                        skipped += 1
                    raw = _record_bytes(record)
                    json_digest.update(raw)
                    json_size += len(raw)
                    for line in _source_mm2_lines(record):
                        expected = line.encode("ascii")
                        actual = mm2_file.read(len(expected))
                        if actual != expected:
                            raise OutputError("MM2 payload disagrees with source records")
                        mm2_digest.update(actual)
                        mm2_size += len(actual)
                    if isinstance(record, StreamEnd):
                        expected = _index_entry(unit, stream_start, record, skipped,
                                                json_start, json_size, mm2_start, mm2_size)
                        if entry != expected:
                            raise OutputError("stream index disagrees with payload byte ranges or counts")
                    elif isinstance(record, SourceEnd):
                        if record != self.end:
                            raise OutputError("source completion disagrees with manifest")
                        if next(entries, None) is not None or mm2_file.read(1):
                            raise OutputError("extra stream index entries or MM2 facts")
                        self._check_digest("tokens.jsonl", json_size, json_digest)
                        self._check_digest("tokens.mm2", mm2_size, mm2_digest)
                    yield record
        except OSError as error:
            raise OutputError(str(error), source=str(self.path)) from error
        finally:
            entries.close()
