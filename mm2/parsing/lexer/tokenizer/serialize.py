"""Shared record checks and lossless token transport primitives."""

import ctypes
from dataclasses import asdict, fields
import json
import os
import re

from .config import loads_json
from .model import (CONTRACT_VERSION, ConfigurationError, DroppedEmpty, Gap,
                    OutputError, Skipped, SourceEnd, SourceStart, Span, StreamEnd,
                    StreamStart, Token, UnitStart, advance_location,
                    validate_identifier)


CHUNK_BYTES = 24
ATOM = re.compile(r"[A-Za-z0-9_-]+")
HEX_CHUNK = re.compile(r"h(?:[0-9a-f]{2}){1,24}")
DIGEST = re.compile(r"[0-9a-f]{64}")


def checked_atom(value):
    """The non-interning MORK reader silently truncates atoms beyond 63 bytes."""
    if type(value) is int and value >= 0:
        value = str(value)
    if not isinstance(value, str) or not ATOM.fullmatch(value) or len(value) > 63:
        raise OutputError("MM2 atoms must contain 1..63 safe ASCII characters")
    return value


def _fact(*atoms):
    return "(" + " ".join(checked_atom(atom) for atom in atoms) + ")\n"


def encode_lexeme(text):
    """Return UTF-8 byte count and an iterator of (index, encoded atom) pairs."""
    try:
        raw = text.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise OutputError("lexeme cannot be encoded as strict UTF-8") from error
    return len(raw), ((offset // CHUNK_BYTES, "h" + raw[offset:offset + CHUNK_BYTES].hex())
                      for offset in range(0, len(raw), CHUNK_BYTES))


def decode_lexeme(parts, *, byte_count, chunk_count):
    """Reassemble unordered exported parts, rejecting missing/duplicate chunks."""
    if (type(byte_count) is not int or byte_count < 0 or
            type(chunk_count) is not int or chunk_count < 0 or
            chunk_count != (byte_count + CHUNK_BYTES - 1) // CHUNK_BYTES):
        raise OutputError("invalid lexeme byte/chunk counts")
    decoded = {}
    for index, atom in parts:
        if type(index) is not int or not 0 <= index < chunk_count or index in decoded:
            raise OutputError("duplicate or out-of-range lexeme chunk index")
        if not isinstance(atom, str) or HEX_CHUNK.fullmatch(atom) is None:
            raise OutputError("invalid encoded lexeme chunk")
        raw = bytes.fromhex(atom[1:])
        expected = CHUNK_BYTES if index + 1 < chunk_count else byte_count - index * CHUNK_BYTES
        if len(raw) != expected:
            raise OutputError("lexeme chunk length disagrees with declared size")
        decoded[index] = raw
    if len(decoded) != chunk_count:
        raise OutputError("missing lexeme chunks")
    try:
        return b"".join(decoded[index] for index in range(chunk_count)).decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise OutputError("lexeme chunks do not encode valid UTF-8") from error


def _identifier(value, label, *, terminal=False):
    try:
        return validate_identifier(value, label, terminal=terminal)
    except ConfigurationError as error:
        raise OutputError(str(error)) from error


def _count(value):
    return type(value) is int and value >= 0


def _check_span(span):
    if (not isinstance(span, Span) or not _count(span.char_start) or
            not _count(span.char_end) or span.char_end < span.char_start or
            any(type(value) is not int or value < 1 for value in
                (span.line_start, span.column_start, span.line_end, span.column_end))):
        raise OutputError("invalid source span")


def _check_text(text, *, empty=True):
    if not isinstance(text, str) or (not empty and not text):
        raise OutputError("expected text" + ("" if empty else " of nonzero length"))
    if re.search("[\ud800-\udfff]", text):
        raise OutputError("text contains an isolated surrogate code point")


def _check_metadata(record):
    for name in ("source", "python_implementation", "python_version", "unicode_version"):
        _check_text(getattr(record, name))
    if record.encoding is not None:
        _check_text(record.encoding, empty=False)
    if (type(record.contract_version) is not int or record.contract_version != CONTRACT_VERSION or
            record.fingerprint_algorithm != "sha256"):
        raise OutputError("unsupported lexical contract or fingerprint algorithm")
    if not isinstance(record.kinds, tuple):
        raise OutputError("declared kinds must be a tuple")
    for kind in record.kinds:
        _identifier(kind, "kind", terminal=True)
    if record.kinds != tuple(sorted(set(record.kinds))):
        raise OutputError("declared kinds must be sorted and distinct")
    if not isinstance(record.spec_fingerprint, str) or DIGEST.fullmatch(record.spec_fingerprint) is None:
        raise OutputError("specification fingerprint must be a full SHA-256 digest")


class TextPosition:
    """Track text pieces while deferring a trailing CR until right context exists."""

    def __init__(self, line=1, column=1):
        self.line, self.column = line, column
        self.pending_cr = False

    def resolve(self, following):
        if self.pending_cr:
            self.line, self.column = advance_location("\r", 0, 1, self.line, self.column,
                                                     following=following)
            self.pending_cr = False

    def advance(self, text):
        if not text:
            return
        self.resolve(text[0])
        end = len(text) - int(text.endswith("\r"))
        self.line, self.column = advance_location(text, 0, end, self.line, self.column)
        self.pending_cr = end != len(text)

    @property
    def coordinates(self):
        return self.line, self.column


class StreamValidator:
    """Validate one stream incrementally; envelope code decides when to emit ends."""

    def __init__(self):
        self.start = self.end = None
        self.token_count = self.char_count = self.skipped_count = 0
        self.position = TextPosition()
        self.pending_end = None

    def _resolve(self, following):
        self.position.resolve(following)
        if self.pending_end is not None and self.pending_end != self.position.coordinates:
            raise OutputError("local source coordinates disagree with text")
        self.pending_end = None

    def push(self, record):
        if self.end is not None:
            raise OutputError("records follow stream completion")
        if self.start is None:
            if not isinstance(record, StreamStart):
                raise OutputError("first record must start a stream")
            _identifier(record.namespace, "namespace")
            _identifier(record.stream_id, "stream_id")
            _check_metadata(record)
            self.start = record
        elif not isinstance(record, (Token, Skipped, StreamEnd)):
            raise OutputError("unexpected record inside stream")
        if (record.namespace, record.stream_id) != (self.start.namespace, self.start.stream_id):
            raise OutputError("records mix stream identities")
        if isinstance(record, (Token, Skipped)):
            _check_text(record.lexeme, empty=False)
            _check_span(record.span)
            _identifier(record.rule, "rule")
            if (record.span.char_start != self.char_count or
                    record.span.char_end != self.char_count + len(record.lexeme)):
                raise OutputError("source spans must cover the input consecutively")
            self._resolve(record.lexeme[0])
            if (record.span.line_start, record.span.column_start) != self.position.coordinates:
                raise OutputError("local source start disagrees with text")
            self.position.advance(record.lexeme)
            self.pending_end = (record.span.line_end, record.span.column_end)
            if not self.position.pending_cr:
                self._resolve("")
            self.char_count = record.span.char_end
            if isinstance(record, Token):
                if type(record.index) is not int or record.index != self.token_count:
                    raise OutputError("token indices must be consecutive")
                if record.kind not in self.start.kinds:
                    raise OutputError("token kind is absent from declared catalog")
                self.token_count += 1
            else:
                self.skipped_count += 1
        elif isinstance(record, StreamEnd):
            if (type(record.token_count) is not int or type(record.source_length) is not int or
                    record.token_count != self.token_count or record.source_length != self.char_count or
                    record.complete is not True):
                raise OutputError("completion counts disagree with stream records")
            self._resolve("")
            self.end = record


def _mm2_lines(record):
    namespace, stream = record.namespace, record.stream_id
    if isinstance(record, StreamStart):
        yield _fact("lex-stream", namespace, stream, record.contract_version)
        digest = record.spec_fingerprint
        yield _fact("lex-spec", namespace, stream, "sha256", "h" + digest[:32], "h" + digest[32:])
        for kind in record.kinds:
            yield _fact("lex-kind", namespace, stream, kind)
    elif isinstance(record, Token):
        index = record.index
        yield _fact("lex-token", namespace, stream, index, index + 1, record.kind)
        yield _fact("lex-span", namespace, stream, index, record.span.char_start, record.span.char_end)
        byte_count, parts = encode_lexeme(record.lexeme)
        yield _fact("lex-value-size", namespace, stream, index, byte_count,
                    (byte_count + CHUNK_BYTES - 1) // CHUNK_BYTES)
        for chunk_index, atom in parts:
            yield _fact("lex-value-part", namespace, stream, index, chunk_index, atom)
    elif isinstance(record, StreamEnd):
        yield _fact("lex-end", namespace, stream, record.token_count, record.source_length)


def _json_line(record):
    return json.dumps(asdict(record), ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n"


def record_from_json(text):
    """Read the exact dataclass schema, including fixed fields, without coercion."""
    try:
        value = loads_json(text, source="token bundle")
    except (ConfigurationError, ValueError, RecursionError) as error:
        raise OutputError(f"invalid bundle JSON: {error}") from error
    classes = (SourceStart, UnitStart, Gap, DroppedEmpty, SourceEnd,
               StreamStart, Token, Skipped, StreamEnd)
    if not isinstance(value, dict):
        raise OutputError("bundle record must be a JSON object")
    cls = next((cls for cls in classes if value.get("type") == cls.__dataclass_fields__["type"].default), None)
    if cls is None or set(value) != {field.name for field in fields(cls)}:
        raise OutputError("unknown bundle record type or fields")
    for field in fields(cls):
        if not field.init and (type(value[field.name]) is not type(field.default) or
                               value[field.name] != field.default):
            raise OutputError(f"invalid fixed record field {field.name}")
    if "span" in value:
        span = value["span"]
        if not isinstance(span, dict) or set(span) != {field.name for field in fields(Span)}:
            raise OutputError("invalid span fields")
        value["span"] = Span(**span)
    if "kinds" in value:
        if not isinstance(value["kinds"], list):
            raise OutputError("declared kinds must be an array")
        value["kinds"] = tuple(value["kinds"])
    return cls(**{field.name: value[field.name] for field in fields(cls) if field.init})


def publish_directory(staging, destination):
    """Linux renameat2 prevents overwriting a destination created concurrently."""
    library = ctypes.CDLL(None, use_errno=True)
    rename = getattr(library, "renameat2", None)
    if rename is None:
        raise OutputError("atomic bundle publication requires Linux renameat2")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    # AT_FDCWD = -100; RENAME_NOREPLACE = 1. Paths here are absolute.
    if rename(-100, os.fsencode(staging), -100, os.fsencode(destination), 1) != 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), str(destination))
