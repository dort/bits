"""Finite byte input with strict, incremental text decoding."""

import codecs
from dataclasses import dataclass
from pathlib import Path

from .model import (ConfigurationError, DEFAULT_MAX_BYTES, DEFAULT_MAX_CHARS,
                    LimitError, SourceError, require_python314, validate_limit)


@dataclass(frozen=True, slots=True)
class TextSource:
    text: str
    label: str
    encoding: str


def read_stream(stream, *, label="<stream>", encoding="utf-8",
                max_bytes=DEFAULT_MAX_BYTES, max_chars=DEFAULT_MAX_CHARS,
                chunk_size=65536):
    """Read one complete input; read chunks never delimit lexical tokens."""
    require_python314()
    validate_limit(max_bytes, "max_bytes")
    validate_limit(max_chars, "max_chars")
    if type(chunk_size) is not int or chunk_size <= 0:
        raise ConfigurationError("must be a positive integer", field="chunk_size")
    try:
        codec = codecs.lookup(encoding)
        decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
        if not isinstance(decoder.decode(b"", final=False), str):
            raise ConfigurationError("requires a text encoding", field="encoding")
    except LookupError as error:
        raise ConfigurationError(str(error), field="encoding") from error
    pieces = []
    byte_count = char_count = 0
    while True:
        try:
            raw = stream.read(min(chunk_size, max_bytes - byte_count + 1))
        except OSError as error:
            raise SourceError(str(error), source=label) from error
        if not isinstance(raw, bytes):
            raise SourceError("reader must return bytes", source=label)
        if byte_count + len(raw) > max_bytes:
            raise LimitError(f"input exceeds {max_bytes} bytes", source=label)
        pending = len(decoder.getstate()[0])
        try:
            part = decoder.decode(raw, final=not raw)
        except UnicodeError as error:
            offset = byte_count - pending + getattr(error, "start", 0)
            raise SourceError(f"cannot decode {codec.name} at byte {offset}: {error.reason}",
                              source=label) from error
        if not isinstance(part, str):
            raise ConfigurationError("requires a text encoding", field="encoding")
        byte_count += len(raw)
        char_count += len(part)
        if char_count > max_chars:
            raise LimitError(f"input exceeds {max_chars} decoded characters", source=label)
        pieces.append(part)
        if not raw:
            break
    return TextSource("".join(pieces), label, codec.name)


def read_source(path, **options):
    require_python314()
    try:
        with Path(path).open("rb") as stream:
            return read_stream(stream, label=str(path), **options)
    except OSError as error:
        raise SourceError(str(error), source=str(path)) from error
