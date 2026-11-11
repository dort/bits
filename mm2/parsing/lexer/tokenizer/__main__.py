"""Command-line entry point: python -m tokenizer."""

import argparse
from contextlib import ExitStack
from pathlib import Path
import sys

from .envelope import IdentityTracker, SourcePiece, source_records
from .model import (ConfigurationError, DEFAULT_MAX_BYTES, DEFAULT_MAX_CHARS,
                    DEFAULT_MAX_UNITS, LexerError, SourceError, escaped,
                    require_python314, validate_limit)
from .bundle import write_bundle
from .source import DecodedStream, read_source, read_stream
from .spec import load_spec
from .split_spec import load_split_spec
from .splitter import split_chunks


def main(argv=None):
    try:
        require_python314()
        parser = argparse.ArgumentParser(description="Split and tokenize text using JSON specifications.")
        parser.add_argument("--spec", required=True)
        parser.add_argument("--split-spec", help="split source into bounded logical units")
        parser.add_argument("--input", required=True, help="file path, or - for binary standard input")
        parser.add_argument("--encoding", default="utf-8")
        parser.add_argument("--namespace", required=True)
        parser.add_argument("--stream-id", required=True, help="stream ID, or base for generated IDs in split mode")
        parser.add_argument("--output-dir", required=True)
        parser.add_argument("--max-bytes", type=int, help="total source byte ceiling; default unlimited with --split-spec")
        parser.add_argument("--max-chars", type=int, help="total source character ceiling; default unlimited with --split-spec")
        parser.add_argument("--max-units", type=int, help="split-unit ceiling; default 1000000000")
        args = parser.parse_args(argv)
        compiled = load_spec(args.spec)
        splitting = load_split_spec(args.split_spec) if args.split_spec is not None else None
        for name in ("max_bytes", "max_chars"):
            value = getattr(args, name)
            if value is not None:
                validate_limit(value, name)
        if splitting is not None:
            max_units = DEFAULT_MAX_UNITS if args.max_units is None else args.max_units
            # Check generated ID capacity and the unit ceiling before opening input.
            IdentityTracker("generated", namespace=args.namespace, stream_base=args.stream_id,
                            max_units=max_units)
            with ExitStack() as files:
                label = "<stdin>" if args.input == "-" else args.input
                if args.input == "-":
                    stream = sys.stdin.buffer
                else:
                    try:
                        stream = files.enter_context(Path(args.input).open("rb"))
                    except OSError as error:
                        raise SourceError(str(error), source=label) from error
                decoded = DecodedStream(stream, label=label, encoding=args.encoding,
                                        max_bytes=args.max_bytes, max_chars=args.max_chars)
                records = source_records(split_chunks(decoded, splitting, source=label), compiled,
                                         namespace=args.namespace, source_id=args.stream_id,
                                         source=label, encoding=decoded.encoding, max_units=max_units,
                                         max_unit_chars=splitting.max_unit_chars,
                                         split_fingerprint=splitting.fingerprint)
                manifest = write_bundle(records, args.output_dir)
        else:
            if args.max_units is not None:
                raise ConfigurationError("requires --split-spec", field="max_units")
            max_chars = DEFAULT_MAX_CHARS if args.max_chars is None else args.max_chars
            max_bytes = DEFAULT_MAX_BYTES if args.max_bytes is None else args.max_bytes
            options = dict(encoding=args.encoding, max_bytes=max_bytes, max_chars=max_chars)
            if args.input == "-":
                source = read_stream(sys.stdin.buffer, label="<stdin>", **options)
            else:
                source = read_source(args.input, **options)
            records = source_records([SourcePiece(source.text, stream_id=args.stream_id)], compiled,
                                     namespace=args.namespace, source_id=args.stream_id,
                                     source=source.label, encoding=source.encoding,
                                     identity_policy="caller", max_units=1, max_unit_chars=max_chars)
            manifest = write_bundle(records, args.output_dir)
        print(f"Wrote {manifest['token_count']} tokens to {escaped(args.output_dir)}")
        return 0
    except ConfigurationError as error:
        print(f"error[{error.category}]: {error}", file=sys.stderr)
        return 2
    except LexerError as error:
        print(f"error[{error.category}]: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("error[interrupted]: processing cancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
