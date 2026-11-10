"""Bounded incremental text decoding and the finite-input convenience API."""

import codecs
from dataclasses import dataclass
from pathlib import Path

from .model import (ConfigurationError, DEFAULT_MAX_BYTES, DEFAULT_MAX_CHARS,
                    LimitError, SourceError, require_python314, validate_limit)


MAX_DECODER_BUFFER = 65536


@dataclass(frozen=True, slots=True)
class TextSource:
    text: str
    label: str
    encoding: str


class DecodedStream:
    """Single-use text-chunk iterator; the caller retains ownership of the reader.

    Limits are checked before yielding a chunk. None removes a total-input limit;
    the undecoded byte buffer is still capped. Counters cover validated reads.
    complete becomes true only after a successful EOF flush.
    """

    def __init__(self, stream, *, label="<stream>", encoding="utf-8",
                 max_bytes=DEFAULT_MAX_BYTES, max_chars=DEFAULT_MAX_CHARS,
                 chunk_size=65536):
        require_python314()
        if max_bytes is not None:
            validate_limit(max_bytes, "max_bytes")
        if max_chars is not None:
            validate_limit(max_chars, "max_chars")
        if type(chunk_size) is not int or chunk_size <= 0:
            raise ConfigurationError("must be a positive integer", field="chunk_size")
        try:
            codec = codecs.lookup(encoding)
            decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
            initial = decoder.decode(b"", final=False)
        except (LookupError, TypeError) as error:
            raise ConfigurationError(str(error), field="encoding") from error
        if not isinstance(initial, str):
            raise ConfigurationError("requires a text encoding", field="encoding")
        self.label = label
        self.encoding = codec.name
        self.byte_count = self.char_count = 0
        self.complete = False
        self._chunks = self._decode(stream, decoder, chunk_size, max_bytes, max_chars)

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._chunks)

    def _check_buffer(self, decoder):
        pending = len(decoder.getstate()[0])
        if pending > MAX_DECODER_BUFFER:
            raise LimitError(f"decoder pending buffer exceeds {MAX_DECODER_BUFFER} bytes",
                             source=self.label)
        return pending

    def _decode(self, stream, decoder, chunk_size, max_bytes, max_chars):
        while True:
            pending = self._check_buffer(decoder)
            request = chunk_size if max_bytes is None else min(chunk_size, max_bytes - self.byte_count + 1)
            try:
                raw = stream.read(request)
            except OSError as error:
                raise SourceError(str(error), source=self.label) from error
            if not isinstance(raw, bytes):
                raise SourceError("reader must return bytes", source=self.label)
            if max_bytes is not None and self.byte_count + len(raw) > max_bytes:
                raise LimitError(f"input exceeds {max_bytes} bytes", source=self.label)
            try:
                part = decoder.decode(raw, final=not raw)
            except UnicodeError as error:
                offset = self.byte_count - pending + getattr(error, "start", 0)
                raise SourceError(f"cannot decode {self.encoding} at byte {offset}: {error.reason}",
                                  source=self.label) from error
            if not isinstance(part, str):
                raise ConfigurationError("requires a text encoding", field="encoding")
            self._check_buffer(decoder)
            if max_chars is not None and self.char_count + len(part) > max_chars:
                raise LimitError(f"input exceeds {max_chars} decoded characters", source=self.label)
            self.byte_count += len(raw)
            self.char_count += len(part)
            if not raw:
                self.complete = True
            if part:
                yield part
            if not raw:
                return


def read_stream(stream, *, label="<stream>", encoding="utf-8",
                max_bytes=DEFAULT_MAX_BYTES, max_chars=DEFAULT_MAX_CHARS,
                chunk_size=65536):
    """Buffer one complete decoded input; read chunks never delimit tokens."""
    decoded = DecodedStream(stream, label=label, encoding=encoding, max_bytes=max_bytes,
                            max_chars=max_chars, chunk_size=chunk_size)
    return TextSource("".join(decoded), decoded.label, decoded.encoding)


def read_source(path, **options):
    require_python314()
    try:
        with Path(path).open("rb") as stream:
            return read_stream(stream, label=str(path), **options)
    except OSError as error:
        raise SourceError(str(error), source=str(path)) from error
