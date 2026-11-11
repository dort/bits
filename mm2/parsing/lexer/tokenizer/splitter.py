"""Incremental splitting with finite lookahead and exact source preservation."""

from .envelope import SourcePiece
from .model import ConfigurationError, LimitError, SourceError, advance_location, require_python314
from .split_spec import CompiledSplitSpec


def split_chunks(chunks, compiled_split, *, source="<stream>"):
    """Return bounded SourcePieces from decoded chunks, in source order.

    Chunk boundaries never decide matches. Pieces carry the actual next source
    character, including when they end between CR and LF. Text storage is one
    bounded unit plus a match-width tail and the current caller-owned chunk.
    The iterable must finish normally before the final residual piece is emitted.
    """
    require_python314()
    if not isinstance(compiled_split, CompiledSplitSpec):
        raise ConfigurationError("compile or load the split specification before splitting")
    return _split(chunks, compiled_split, source)


def _segments(chunks, spec, source):
    """Yield (text, matched, following), retaining only undecided search text.

    Before EOF a candidate needs the full match width and one extra character
    for provenance. Searches may see the undecided tail, but matches starting
    there are deferred. A preceding character keeps ^ anchored to the real
    source instead of the compacted buffer. Decided nonmatches are never rescanned.
    """
    chunks = iter(chunks)
    tail = previous = ""
    eof = False
    while True:
        try:
            chunk = next(chunks)
        except StopIteration:
            chunk, eof = "", True
        if not isinstance(chunk, str):
            raise SourceError("splitter requires decoded string chunks", source=source)
        if not chunk and not eof:
            continue
        text = previous + tail + chunk
        cursor = len(previous)
        decided_end = len(text) if eof else max(cursor, len(text) - spec.width)
        while cursor < decided_end:
            if spec.literal is not None:
                start = text.find(spec.literal, cursor)
                end = start + spec.width
            else:
                match = spec.pattern.search(text, cursor)
                start, end = match.span() if match is not None else (-1, -1)
            if start < 0 or start >= decided_end:
                yield text[cursor:decided_end], False, text[decided_end:decided_end + 1]
                cursor = decided_end
                break
            if not 0 < end - start <= spec.width:
                raise ConfigurationError("split matcher violated its positive-width bound", field="pattern")
            if start > cursor:
                yield text[cursor:start], False, text[start:start + 1]
            yield text[start:end], True, text[end:end + 1]
            cursor = end
        if eof:
            return
        previous = text[cursor - 1:cursor] if cursor else ""
        tail = text[cursor:]


def _split(chunks, spec, source):
    pieces = []
    length = offset = 0
    line = column = 1
    saw_boundary = False

    def advance(text, following):
        nonlocal offset, line, column
        line, column = advance_location(text, 0, len(text), line, column, following=following)
        offset += len(text)

    def append(text, following):
        nonlocal length
        if length + len(text) > spec.max_unit_chars:
            allowed = spec.max_unit_chars - length
            error_line, error_column = advance_location(text, 0, allowed, line, column, following=following)
            raise LimitError(f"unit exceeds {spec.max_unit_chars} characters", source=source,
                             field="max_unit_chars", offset=offset + allowed,
                             line=error_line, column=error_column)
        pieces.append(text)
        length += len(text)
        advance(text, following)

    def unit(following):
        nonlocal length
        text = "".join(pieces)
        pieces.clear()
        length = 0
        disposition = "dropped-empty" if not text and spec.empty_units == "drop" else "unit"
        return SourcePiece(text, disposition, following=following)

    for text, matched, following in _segments(chunks, spec, source):
        if spec.mode == "boundary":
            if matched:
                if length:
                    yield unit(text[0])
                saw_boundary = True
            elif not saw_boundary and spec.preamble == "reject":
                raise SourceError("nonempty text precedes the first boundary", source=source,
                                  offset=0, line=1, column=1)
            append(text, following)
        elif not matched:
            append(text, following)
        elif spec.retain == "end":
            append(text, following)
            yield unit(following)
        else:
            yield unit(text[0])
            yield SourcePiece(text, "gap", following=following)
            advance(text, following)
    if length or offset == 0:
        yield unit("")
