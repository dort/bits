"""Deterministic longest-candidate matching over one complete text input."""

import re
import sys
import unicodedata

from .model import (ConfigurationError, DEFAULT_MAX_CHARS, LexicalError, LimitError,
                    Skipped, SourceError, Span, StreamEnd, StreamStart, Token,
                    advance_location, require_python314, validate_identifier,
                    validate_limit)
from .spec import CompiledSpec


SURROGATE = re.compile("[\ud800-\udfff]")


def tokenize(text, compiled_spec, *, namespace, stream_id, source="<text>",
             encoding=None, max_chars=DEFAULT_MAX_CHARS):
    """Return records; only a consumed StreamEnd proves complete tokenization."""
    require_python314()
    validate_identifier(namespace, "namespace")
    validate_identifier(stream_id, "stream_id")
    validate_limit(max_chars, "max_chars")
    if not isinstance(text, str):
        raise SourceError("tokenize requires a Python string", source=source)
    if not isinstance(compiled_spec, CompiledSpec):
        raise ConfigurationError("compile or load the specification before tokenizing")
    if len(text) > max_chars:
        raise LimitError(f"input exceeds {max_chars} characters", source=source)
    invalid = SURROGATE.search(text)
    if invalid:
        line, column = advance_location(text, 0, invalid.start(), 1, 1)
        raise SourceError("isolated surrogate code point", source=source,
                          offset=invalid.start(), line=line, column=column)
    return _scan(text, compiled_spec, namespace, stream_id, source, encoding)


def _scan(text, spec, namespace, stream_id, source, encoding):
    yield StreamStart(namespace, stream_id, source, encoding,
                      sys.implementation.name, sys.version, unicodedata.unidata_version,
                      spec.fingerprint, spec.kinds)
    offset = index = 0
    line = column = 1
    while offset < len(text):
        winner = None
        best_end = offset
        for rule in spec.rules:
            if rule.literal is not None:
                end = offset + len(rule.literal) if text.startswith(rule.literal, offset) else None
            else:
                match = rule.pattern.match(text, offset)
                end = match.end() if match is not None else None
            if end == offset:
                raise ConfigurationError("pattern produced a zero-length match",
                                         source=source, rule=rule.name, field="pattern",
                                         offset=offset, line=line, column=column,
                                         excerpt=text[offset:offset + 40])
            if end is not None and end > best_end:
                winner, best_end = rule, end
        if winner is None:
            raise LexicalError("no rule matches the input", source=source, offset=offset,
                               line=line, column=column, excerpt=text[offset:offset + 40])
        end_line, end_column = advance_location(text, offset, best_end, line, column)
        span = Span(offset, best_end, line, column, end_line, end_column)
        lexeme = text[offset:best_end]
        if winner.kind is None:
            yield Skipped(namespace, stream_id, winner.name, lexeme, span)
        else:
            yield Token(namespace, stream_id, index, winner.kind, winner.name, lexeme, span)
            index += 1
        offset, line, column = best_end, end_line, end_column
    yield StreamEnd(namespace, stream_id, index, len(text))
