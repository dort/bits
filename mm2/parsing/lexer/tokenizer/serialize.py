"""Lossless token transport and atomic publication of completed bundles."""

import ctypes
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import tempfile

from .model import (ConfigurationError, OutputError, Skipped, StreamEnd, StreamStart,
                    Token, require_python314, validate_identifier)


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


def _checked_records(records):
    """Check one stream and hold its completion marker until iteration ends."""
    start = end = None
    token_count = char_count = 0
    for record in records:
        if end is not None:
            raise OutputError("records follow stream completion")
        if start is None:
            if not isinstance(record, StreamStart):
                raise OutputError("first record must start a stream")
            try:
                validate_identifier(record.namespace, "namespace")
                validate_identifier(record.stream_id, "stream_id")
                for kind in record.kinds:
                    validate_identifier(kind, "kind", terminal=True)
            except ConfigurationError as error:
                raise OutputError(str(error)) from error
            if record.kinds != tuple(sorted(set(record.kinds))):
                raise OutputError("declared kinds must be sorted and distinct")
            if DIGEST.fullmatch(record.spec_fingerprint) is None:
                raise OutputError("specification fingerprint must be a full SHA-256 digest")
            start = record
        elif not isinstance(record, (Token, Skipped, StreamEnd)):
            raise OutputError("unexpected record inside stream")
        if (record.namespace, record.stream_id) != (start.namespace, start.stream_id):
            raise OutputError("records mix stream identities")
        if isinstance(record, (Token, Skipped)):
            if (not record.lexeme or record.span.char_start != char_count or
                    type(record.span.char_end) is not int or
                    record.span.char_end != char_count + len(record.lexeme)):
                raise OutputError("source spans must cover the input consecutively")
            char_count = record.span.char_end
            if isinstance(record, Token):
                if type(record.index) is not int or record.index != token_count:
                    raise OutputError("token indices must be consecutive")
                if record.kind not in start.kinds:
                    raise OutputError("token kind is absent from declared catalog")
                token_count += 1
        elif isinstance(record, StreamEnd):
            if (type(record.token_count) is not int or type(record.source_length) is not int or
                    record.token_count != token_count or record.source_length != char_count):
                raise OutputError("completion counts disagree with stream records")
            end = record
            continue
        yield record
    if end is None:
        raise OutputError("incomplete stream: no successful stream-end record")
    yield end


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


def iter_mm2(records):
    require_python314()
    for record in _checked_records(records):
        yield from _mm2_lines(record)


def _json_line(record):
    return json.dumps(asdict(record), ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n"


def iter_jsonl(records):
    require_python314()
    for record in _checked_records(records):
        yield _json_line(record)


def _publish_directory(staging, destination):
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


def write_bundle(records, output_dir):
    """Publish JSONL, MM2, and a manifest together after complete success."""
    require_python314()
    destination = Path(output_dir).absolute()
    try:
        if os.path.lexists(destination):
            raise OutputError("output directory already exists", source=str(destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f".{destination.name}.", dir=destination.parent) as temporary:
            staging = Path(temporary)
            manifest = None
            skipped_count = 0
            with (staging.joinpath("tokens.jsonl").open("w", encoding="utf-8", newline="\n") as jsonl,
                  staging.joinpath("tokens.mm2").open("w", encoding="ascii", newline="\n") as mm2):
                for record in _checked_records(records):
                    jsonl.write(_json_line(record))
                    mm2.writelines(_mm2_lines(record))
                    if isinstance(record, StreamStart):
                        manifest = asdict(record)
                        del manifest["type"]
                    elif isinstance(record, Skipped):
                        skipped_count += 1
                    elif isinstance(record, StreamEnd):
                        manifest.update(token_count=record.token_count,
                                        source_length=record.source_length,
                                        skipped_span_count=skipped_count, complete=True)
            with staging.joinpath("manifest.json").open("w", encoding="utf-8", newline="\n") as output:
                json.dump(manifest, output, ensure_ascii=True, indent=2, allow_nan=False)
                output.write("\n")
            _publish_directory(staging, destination)
        return manifest
    except OSError as error:
        raise OutputError(str(error), source=str(destination)) from error
