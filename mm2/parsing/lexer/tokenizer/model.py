"""Records, diagnostics, and shared input constraints."""

from dataclasses import dataclass, field
import json
import re
import sys


CONTRACT_VERSION = 1
BUNDLE_VERSION = 2
DEFAULT_MAX_UNITS = 1_000_000_000
DEFAULT_MAX_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_CHARS = 4 * 1024 * 1024
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,31}")
KIND = re.compile(r"[A-Z][A-Z0-9_]{0,31}")


def escaped(value, limit=200):
    """Bound diagnostic text before escaping control characters for terminals."""
    value = str(value)
    if len(value) > limit:
        value = value[:limit] + "..."
    return json.dumps(value, ensure_ascii=True)[1:-1]


class LexerError(Exception):
    category = "lexer"

    def __init__(self, message, *, source=None, rule=None, field=None,
                 offset=None, line=None, column=None, excerpt=None,
                 pattern_offset=None):
        super().__init__(message)
        self.message = message
        self.source = source
        self.rule = rule
        self.field = field
        self.offset = offset
        self.line = line
        self.column = column
        self.excerpt = excerpt
        self.pattern_offset = pattern_offset
        # A source envelope translates lexical coordinates while retaining the
        # original unit-local location. Direct tokenize() errors stay local.
        self.local_offset = self.local_line = self.local_column = None
        self.unit_index = self.stream_id = None

    def __str__(self):
        context = []
        if self.source is not None:
            context.append(escaped(self.source, 160))
        if self.line is not None:
            context.append(f"line {self.line}, column {self.column}")
        if self.offset is not None:
            context.append(f"offset {self.offset}")
        if self.unit_index is not None:
            context.append(f"unit {self.unit_index} ({escaped(self.stream_id, 32)})")
        if self.local_offset is not None:
            context.append(f"local line {self.local_line}, column {self.local_column}, offset {self.local_offset}")
        if self.rule is not None:
            context.append(f"rule {escaped(self.rule, 40)}")
        if self.field is not None:
            context.append(f"field {escaped(self.field, 40)}")
        if self.pattern_offset is not None:
            context.append(f"pattern offset {self.pattern_offset}")
        prefix = ": ".join(context)
        result = (prefix + ": " if prefix else "") + escaped(self.message, 300)
        if self.excerpt is not None:
            result += f' (near "{escaped(self.excerpt, 40)}")'
        return result


class ConfigurationError(LexerError):
    category = "configuration"


class RuntimeVersionError(ConfigurationError):
    category = "runtime"


class SourceError(LexerError):
    category = "source"


class LexicalError(LexerError):
    category = "lexical"


class LimitError(LexerError):
    category = "limit"


class OutputError(LexerError):
    category = "output"


def require_python314():
    if sys.version_info[:2] != (3, 14):
        raise RuntimeVersionError(
            f"requires Python 3.14; running {sys.version_info.major}.{sys.version_info.minor}"
        )


def validate_identifier(value, label, *, terminal=False):
    pattern = KIND if terminal else IDENTIFIER
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ConfigurationError(f"must match {pattern.pattern}", field=label)
    return value


def validate_limit(value, label):
    if type(value) is not int or value < 0:
        raise ConfigurationError("must be a nonnegative integer", field=label)


def advance_location(text, start, end, line, column, *, following=""):
    """Count CRLF at LF, including across tokens or separately held pieces.

    following is the character immediately beyond text, or an empty string at
    source EOF. A streaming caller must resolve that lookahead before advancing
    past a trailing CR. Characters within text supply their own right context.
    """
    for offset in range(start, end):
        char = text[offset]
        if char == "\n" or (char == "\r" and
                            (text[offset + 1] if offset + 1 < len(text) else following) != "\n"):
            line += 1
            column = 1
        else:
            column += 1
    return line, column


@dataclass(frozen=True, slots=True)
class Span:
    char_start: int
    char_end: int
    line_start: int
    column_start: int
    line_end: int
    column_end: int


@dataclass(frozen=True, slots=True)
class StreamStart:
    namespace: str
    stream_id: str
    source: str
    encoding: str | None
    python_implementation: str
    python_version: str
    unicode_version: str
    spec_fingerprint: str
    kinds: tuple[str, ...]
    contract_version: int = field(default=CONTRACT_VERSION, init=False)
    fingerprint_algorithm: str = field(default="sha256", init=False)
    type: str = field(default="stream-start", init=False)


@dataclass(frozen=True, slots=True)
class Token:
    namespace: str
    stream_id: str
    index: int
    kind: str
    rule: str
    lexeme: str
    span: Span
    type: str = field(default="token", init=False)


@dataclass(frozen=True, slots=True)
class Skipped:
    namespace: str
    stream_id: str
    rule: str
    lexeme: str
    span: Span
    type: str = field(default="skipped", init=False)


@dataclass(frozen=True, slots=True)
class StreamEnd:
    namespace: str
    stream_id: str
    token_count: int
    source_length: int
    complete: bool = field(default=True, init=False)
    type: str = field(default="stream-end", init=False)


@dataclass(frozen=True, slots=True)
class SourceStart:
    namespace: str
    source_id: str
    source: str
    encoding: str | None
    python_implementation: str
    python_version: str
    unicode_version: str
    spec_fingerprint: str
    kinds: tuple[str, ...]
    identity_policy: str
    stream_base: str | None
    max_units: int
    max_unit_chars: int
    split_fingerprint: str | None = None
    bundle_version: int = field(default=BUNDLE_VERSION, init=False)
    contract_version: int = field(default=CONTRACT_VERSION, init=False)
    fingerprint_algorithm: str = field(default="sha256", init=False)
    type: str = field(default="source-start", init=False)


@dataclass(frozen=True, slots=True)
class UnitStart:
    namespace: str
    source_id: str
    stream_id: str
    unit_index: int
    piece_index: int
    span: Span
    following: str
    type: str = field(default="unit-start", init=False)


@dataclass(frozen=True, slots=True)
class Gap:
    namespace: str
    source_id: str
    piece_index: int
    text: str
    span: Span
    following: str
    type: str = field(default="gap", init=False)


@dataclass(frozen=True, slots=True)
class DroppedEmpty:
    namespace: str
    source_id: str
    piece_index: int
    span: Span
    following: str
    type: str = field(default="dropped-empty", init=False)


@dataclass(frozen=True, slots=True)
class SourceEnd:
    namespace: str
    source_id: str
    unit_count: int
    piece_count: int
    token_count: int
    skipped_span_count: int
    gap_count: int
    dropped_empty_count: int
    source_length: int
    line_end: int
    column_end: int
    complete: bool = field(default=True, init=False)
    type: str = field(default="source-end", init=False)
