"""Source envelopes, bounded identity checks, and construction from text pieces."""

from dataclasses import dataclass
import sys
import unicodedata

from .lexer import tokenize
from .model import (BUNDLE_VERSION, DEFAULT_MAX_CHARS, DEFAULT_MAX_UNITS,
                    ConfigurationError, DroppedEmpty, Gap, LimitError, OutputError,
                    Skipped, SourceEnd, SourceStart, Span, StreamEnd, StreamStart,
                    Token, UnitStart, advance_location, require_python314,
                    validate_identifier, validate_limit)
from .serialize import (DIGEST, StreamValidator, TextPosition, _check_metadata,
                        _check_span, _check_text, _count, _identifier)
from .spec import CompiledSpec


MAX_CALLER_IDS = 100_000
MAX_GAP_CHARS = 65536
METADATA_FIELDS = ("source", "encoding", "python_implementation", "python_version",
                   "unicode_version", "spec_fingerprint", "kinds", "contract_version",
                   "fingerprint_algorithm")


class IdentityTracker:
    """Generated IDs use constant state; caller identities use a capped set."""

    def __init__(self, policy, *, namespace, stream_base, max_units):
        validate_identifier(namespace, "namespace")
        if type(max_units) is not int or max_units < 1:
            raise ConfigurationError("must be a positive integer", field="max_units")
        if policy == "generated":
            validate_identifier(stream_base, "stream_base")
            if len(stream_base) + 2 + len(str(max_units - 1)) > 32:
                raise ConfigurationError("generated IDs exceed 32 characters at the unit ceiling",
                                         field="stream_base")
        elif policy != "caller" or stream_base is not None:
            raise ConfigurationError("use generated IDs with a base or caller IDs without one",
                                     field="identity_policy")
        self.policy, self.namespace, self.stream_base = policy, namespace, stream_base
        self.max_units = max_units
        self.count = 0
        self.seen = set() if policy == "caller" else None

    def add(self, namespace, stream_id, index):
        _identifier(stream_id, "stream_id")
        if namespace != self.namespace or type(index) is not int or index != self.count:
            raise OutputError("unit namespace or consecutive unit index disagrees with source")
        if self.count >= self.max_units:
            raise LimitError(f"source exceeds {self.max_units} units", field="max_units")
        if self.policy == "generated":
            if stream_id != f"{self.stream_base}_u{index}":
                raise OutputError("generated stream ID disagrees with source base and index")
        else:
            key = (namespace, stream_id)
            if key in self.seen:
                raise OutputError("duplicate namespace/stream identity")
            if len(self.seen) >= MAX_CALLER_IDS:
                raise LimitError(f"source exceeds {MAX_CALLER_IDS} caller-owned IDs",
                                 field="max_caller_ids")
            self.seen.add(key)
        self.count += 1


def check_source_start(start):
    if not isinstance(start, SourceStart):
        raise OutputError("first record must start a source envelope")
    if type(start.bundle_version) is not int or start.bundle_version != BUNDLE_VERSION:
        raise ConfigurationError("unsupported bundle version", field="bundle_version")
    _identifier(start.source_id, "source_id")
    _check_metadata(start)
    if not _count(start.max_unit_chars):
        raise OutputError("max_unit_chars must be a nonnegative integer")
    if start.split_fingerprint is not None and (not isinstance(start.split_fingerprint, str) or
                                              DIGEST.fullmatch(start.split_fingerprint) is None):
        raise OutputError("split fingerprint must be a full SHA-256 digest")
    return IdentityTracker(start.identity_policy, namespace=start.namespace,
                           stream_base=start.stream_base, max_units=start.max_units)


def check_piece(start, piece):
    if (piece.namespace, piece.source_id) != (start.namespace, start.source_id):
        raise OutputError("piece identity disagrees with source")
    _check_span(piece.span)
    if not _count(piece.piece_index):
        raise OutputError("piece index must be a nonnegative integer")
    _check_text(piece.following)
    if len(piece.following) > 1:
        raise OutputError("following context must be one character or source EOF")
    if isinstance(piece, UnitStart):
        _identifier(piece.stream_id, "stream_id")
        if not _count(piece.unit_index):
            raise OutputError("unit index must be a nonnegative integer")
        if piece.span.char_end - piece.span.char_start > start.max_unit_chars:
            raise LimitError(f"unit exceeds {start.max_unit_chars} characters", field="max_unit_chars")


class UnitValidator:
    """Check local stream records and their absolute source provenance together."""

    def __init__(self, start, unit):
        check_piece(start, unit)
        self.source, self.unit = start, unit
        self.stream = StreamValidator()
        self.position = TextPosition(unit.span.line_start, unit.span.column_start)

    def push(self, record):
        self.stream.push(record)
        if (record.namespace, record.stream_id) != (self.unit.namespace, self.unit.stream_id):
            raise OutputError("stream identity disagrees with unit")
        if isinstance(record, StreamStart):
            if any(getattr(record, name) != getattr(self.source, name) for name in METADATA_FIELDS):
                raise OutputError("stream metadata disagrees with source")
        elif isinstance(record, (Token, Skipped)):
            if self.stream.char_count > self.unit.span.char_end - self.unit.span.char_start:
                raise OutputError("unit text exceeds declared source span")
            self.position.advance(record.lexeme)
        elif isinstance(record, StreamEnd):
            self.position.resolve(self.unit.following)
            if (record.source_length != self.unit.span.char_end - self.unit.span.char_start or
                    self.position.coordinates != (self.unit.span.line_end, self.unit.span.column_end)):
                raise OutputError("unit source span or coordinates disagree with text")


class SourceValidator:
    def __init__(self):
        self.start = self.end = self.unit = self.identities = None
        self.piece_count = self.token_count = self.skipped_span_count = 0
        self.gap_count = self.dropped_empty_count = self.source_length = 0
        self.line_end = self.column_end = 1
        self.following = None

    def _first_text(self, text, following):
        actual = text[0] if text else following
        if self.following is not None and actual != self.following:
            raise OutputError("piece following context disagrees with original source")

    def _finish_piece(self, piece):
        self.source_length = piece.span.char_end
        self.line_end, self.column_end = piece.span.line_end, piece.span.column_end
        self.following = piece.following
        self.piece_count += 1

    def push(self, record):
        if self.end is not None:
            raise OutputError("records follow source completion")
        if self.start is None:
            self.identities = check_source_start(record)
            self.start = record
            return
        if self.unit is not None:
            if isinstance(record, (Token, Skipped)) and self.unit.stream.char_count == 0:
                _check_text(record.lexeme, empty=False)
                self._first_text(record.lexeme, self.unit.unit.following)
            self.unit.push(record)
            if isinstance(record, StreamEnd):
                if record.source_length == 0:
                    self._first_text("", self.unit.unit.following)
                self.token_count += record.token_count
                self.skipped_span_count += self.unit.stream.skipped_count
                self._finish_piece(self.unit.unit)
                self.unit = None
            return
        if isinstance(record, SourceEnd):
            names = ("piece_count", "token_count", "skipped_span_count", "gap_count",
                     "dropped_empty_count", "source_length", "line_end", "column_end")
            if ((record.namespace, record.source_id) != (self.start.namespace, self.start.source_id) or
                    record.complete is not True or not _count(record.unit_count) or
                    record.unit_count != self.identities.count or
                    any(not _count(getattr(record, name)) or
                        getattr(record, name) != getattr(self, name) for name in names)):
                raise OutputError("source completion counts or coordinates disagree with records")
            if self.following not in (None, ""):
                raise OutputError("last piece claims text beyond source EOF")
            self.end = record
            return
        if not isinstance(record, (UnitStart, Gap, DroppedEmpty)):
            raise OutputError("expected a source piece or source end")
        check_piece(self.start, record)
        if (record.piece_index != self.piece_count or record.span.char_start != self.source_length or
                (record.span.line_start, record.span.column_start) != (self.line_end, self.column_end)):
            raise OutputError("source pieces must have consecutive ordinals and cover the source")
        if isinstance(record, UnitStart):
            self.identities.add(record.namespace, record.stream_id, record.unit_index)
            self.unit = UnitValidator(self.start, record)
            return
        text = record.text if isinstance(record, Gap) else ""
        _check_text(text)
        if isinstance(record, Gap):
            if not text:
                raise OutputError("gap text must be nonempty")
            if len(text) > MAX_GAP_CHARS:
                raise LimitError(f"gap record exceeds {MAX_GAP_CHARS} characters", field="gap_chars")
            self.gap_count += 1
        else:
            self.dropped_empty_count += 1
        self._first_text(text, record.following)
        end = advance_location(text, 0, len(text), self.line_end, self.column_end,
                               following=record.following)
        if (record.span.char_end != self.source_length + len(text) or
                (record.span.line_end, record.span.column_end) != end):
            raise OutputError("gap or dropped-empty span disagrees with text")
        self._finish_piece(record)


def checked_source_records(records):
    validator = SourceValidator()
    pending_stream_end = None
    for record in records:
        validator.push(record)
        if pending_stream_end is not None:
            yield pending_stream_end
            pending_stream_end = None
        if isinstance(record, StreamEnd):
            pending_stream_end = record
        elif not isinstance(record, SourceEnd):
            yield record
    if validator.end is None:
        raise OutputError("incomplete source: no successful source-end record")
    yield validator.end


@dataclass(frozen=True, slots=True)
class SourcePiece:
    """One bounded piece; following is the original source's next character."""

    text: str
    disposition: str = "unit"
    stream_id: str | None = None
    following: str = ""


def source_records(pieces, compiled_spec, *, namespace, source_id, source="<text>",
                   encoding=None, identity_policy="generated", stream_base=None,
                   max_units=DEFAULT_MAX_UNITS, max_unit_chars=DEFAULT_MAX_CHARS,
                   split_fingerprint=None):
    """Wrap bounded text pieces in one source envelope without retaining units."""
    require_python314()
    if not isinstance(compiled_spec, CompiledSpec):
        raise ConfigurationError("compile or load the specification before tokenizing")
    validate_identifier(namespace, "namespace")
    validate_identifier(source_id, "source_id")
    validate_limit(max_unit_chars, "max_unit_chars")
    if identity_policy == "generated" and stream_base is None:
        stream_base = source_id
    start = SourceStart(namespace, source_id, source, encoding, sys.implementation.name,
                        sys.version, unicodedata.unidata_version, compiled_spec.fingerprint,
                        compiled_spec.kinds, identity_policy, stream_base, max_units,
                        max_unit_chars, split_fingerprint)
    check_source_start(start)
    return _source_records(pieces, compiled_spec, start)


def _source_records(pieces, spec, start):
    yield start
    offset = units = pieces_seen = tokens = skips = gaps = drops = 0
    line = column = 1
    for piece in pieces:
        if not isinstance(piece, SourcePiece):
            raise OutputError("source builder requires SourcePiece inputs")
        _check_text(piece.text)
        _check_text(piece.following)
        if len(piece.following) > 1:
            raise OutputError("following context must be one character or source EOF")
        if piece.disposition not in ("unit", "gap", "dropped-empty"):
            raise OutputError("unknown source piece disposition")
        if piece.disposition == "unit" and len(piece.text) > start.max_unit_chars:
            raise LimitError(f"unit exceeds {start.max_unit_chars} characters", field="max_unit_chars")
        if piece.disposition == "gap" and len(piece.text) > MAX_GAP_CHARS:
            raise LimitError(f"gap record exceeds {MAX_GAP_CHARS} characters", field="gap_chars")
        end_line, end_column = advance_location(piece.text, 0, len(piece.text), line, column,
                                               following=piece.following)
        span = Span(offset, offset + len(piece.text), line, column, end_line, end_column)
        if piece.disposition == "unit":
            if units >= start.max_units:
                raise LimitError(f"source exceeds {start.max_units} units", field="max_units")
            if start.identity_policy == "generated":
                if piece.stream_id is not None:
                    raise OutputError("generated identity policy does not accept caller-owned IDs")
                stream_id = f"{start.stream_base}_u{units}"
            else:
                if piece.stream_id is None:
                    raise OutputError("caller identity policy requires a stream ID for every unit")
                stream_id = piece.stream_id
            yield UnitStart(start.namespace, start.source_id, stream_id, units, pieces_seen,
                            span, piece.following)
            for record in tokenize(piece.text, spec, namespace=start.namespace, stream_id=stream_id,
                                   source=start.source, encoding=start.encoding, max_chars=start.max_unit_chars):
                yield record
                if isinstance(record, StreamEnd):
                    tokens += record.token_count
                elif isinstance(record, Skipped):
                    skips += 1
            units += 1
        else:
            if piece.stream_id is not None:
                raise OutputError("only emitted units have stream IDs")
            if piece.disposition == "gap":
                if not piece.text:
                    raise OutputError("gap text must be nonempty")
                yield Gap(start.namespace, start.source_id, pieces_seen, piece.text, span, piece.following)
                gaps += 1
            else:
                if piece.text:
                    raise OutputError("dropped-empty pieces cannot contain text")
                yield DroppedEmpty(start.namespace, start.source_id, pieces_seen, span, piece.following)
                drops += 1
        offset, line, column = span.char_end, end_line, end_column
        pieces_seen += 1
    yield SourceEnd(start.namespace, start.source_id, units, pieces_seen, tokens, skips, gaps, drops,
                    offset, line, column)
