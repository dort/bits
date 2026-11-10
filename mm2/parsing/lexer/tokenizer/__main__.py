"""Command-line entry point: python -m tokenizer."""

import argparse
import sys

from .envelope import SourcePiece, source_records
from .model import (ConfigurationError, DEFAULT_MAX_BYTES, DEFAULT_MAX_CHARS,
                    LexerError, escaped, require_python314)
from .bundle import write_bundle
from .source import read_source, read_stream
from .spec import load_spec


def main(argv=None):
    try:
        require_python314()
        parser = argparse.ArgumentParser(description="Tokenize finite text using a JSON lexical specification.")
        parser.add_argument("--spec", required=True)
        parser.add_argument("--input", required=True, help="file path, or - for binary standard input")
        parser.add_argument("--encoding", default="utf-8")
        parser.add_argument("--namespace", required=True)
        parser.add_argument("--stream-id", required=True)
        parser.add_argument("--output-dir", required=True)
        parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
        parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
        args = parser.parse_args(argv)
        compiled = load_spec(args.spec)
        options = dict(encoding=args.encoding, max_bytes=args.max_bytes, max_chars=args.max_chars)
        if args.input == "-":
            source = read_stream(sys.stdin.buffer, label="<stdin>", **options)
        else:
            source = read_source(args.input, **options)
        records = source_records([SourcePiece(source.text, stream_id=args.stream_id)], compiled,
                                 namespace=args.namespace, source_id=args.stream_id,
                                 source=source.label, encoding=source.encoding,
                                 identity_policy="caller", max_units=1, max_unit_chars=args.max_chars)
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
