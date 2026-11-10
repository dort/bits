"""Command-line entry point: python -m grammarc parse."""

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import sys

from tokenizer.model import DEFAULT_MAX_CHARS, LexerError, escaped, require_python314

from .runner import (DEFAULT_INITIAL_ROUNDS, DEFAULT_MAX_DUMP_BYTES,
                     DEFAULT_MAX_PAYLOAD_BYTES, DEFAULT_MAX_SWEEPS,
                     DEFAULT_MAX_TOKENS, DEFAULT_MORK,
                     DEFAULT_TIMEOUT_SECONDS, Runner)
from .spec import load_grammar


def main(argv=None):
    try:
        require_python314()
        parser = argparse.ArgumentParser(
            prog="grammarc",
            description="Recognize a version-2 token bundle's units with an MM2 Earley engine.")
        commands = parser.add_subparsers(dest="command", required=True)
        parse = commands.add_parser("parse")
        parse.add_argument("--grammar", required=True)
        parse.add_argument("--grammar-id", required=True)
        parse.add_argument("--tokens", required=True, help="a completed version-2 bundle directory")
        parse.add_argument("--output-dir", required=True)
        parse.add_argument("--engine", choices=("recognition", "forest"), default="recognition")
        parse.add_argument("--mork", default=DEFAULT_MORK)
        parse.add_argument("--initial-rounds", type=int, default=DEFAULT_INITIAL_ROUNDS)
        parse.add_argument("--max-sweeps", type=int, default=DEFAULT_MAX_SWEEPS)
        parse.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
        parse.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
        parse.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
        parse.add_argument("--max-payload-bytes", type=int, default=DEFAULT_MAX_PAYLOAD_BYTES)
        parse.add_argument("--max-dump-bytes", type=int, default=DEFAULT_MAX_DUMP_BYTES)
        parse.add_argument("--max-process-bytes", type=int, default=None)
        parse.add_argument("--max-trees", type=int, default=None,
                           help="enumerate up to this many trees per unit (forest engine only)")
        parse.add_argument("--max-depth", type=int, default=None,
                           help="nonterminal nesting limit for tree enumeration")
        args = parser.parse_args(argv)

        grammar = load_grammar(args.grammar)
        runner = Runner(grammar, args.grammar_id, engine=args.engine, mork=args.mork,
                        initial_rounds=args.initial_rounds, max_sweeps=args.max_sweeps,
                        timeout_seconds=args.timeout_seconds, max_tokens=args.max_tokens,
                        max_chars=args.max_chars, max_payload_bytes=args.max_payload_bytes,
                        max_dump_bytes=args.max_dump_bytes,
                        max_process_bytes=args.max_process_bytes,
                        max_trees=args.max_trees, max_depth=args.max_depth)
        destination = Path(args.output_dir)
        destination.mkdir(parents=True, exist_ok=False)
        counts = {"accepted": 0, "rejected": 0, "incomplete": 0}
        incomplete_results = 0
        with (destination / "results.jsonl").open("x", encoding="ascii") as sink:
            for unit in runner.run_bundle(args.tokens):
                counts[unit.recognition] += 1
                # A requested forest or enumeration cut short by a limit makes
                # the command incomplete even when recognition accepted.
                if (unit.recognition == "incomplete"
                        or unit.forest_complete is False
                        or unit.enumeration_complete is False):
                    incomplete_results += 1
                sink.write(json.dumps(dataclasses.asdict(unit), ensure_ascii=True,
                                      sort_keys=True) + "\n")
        summary = {
            "grammar": str(args.grammar),
            "grammar_id": args.grammar_id,
            "grammar_fingerprint": grammar.fingerprint,
            "engine": args.engine,
            "engine_file": runner.engine_path.name,
            "engine_sha256": hashlib.sha256(runner.engine_path.read_bytes()).hexdigest(),
            "bundle": str(args.tokens),
            "units": sum(counts.values()),
            "counts": counts,
            "incomplete_results": incomplete_results,
            "limits": {"initial_rounds": args.initial_rounds, "max_sweeps": args.max_sweeps,
                       "timeout_seconds": args.timeout_seconds, "max_tokens": args.max_tokens,
                       "max_chars": args.max_chars, "max_payload_bytes": args.max_payload_bytes,
                       "max_dump_bytes": args.max_dump_bytes,
                       "max_process_bytes": args.max_process_bytes},
        }
        (destination / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
            encoding="ascii")
        print(f"Processed {summary['units']} units into {escaped(args.output_dir)}: "
              f"{counts['accepted']} accepted, {counts['rejected']} rejected, "
              f"{counts['incomplete']} incomplete")
        if incomplete_results:
            return 3
        if counts["rejected"]:
            return 1
        return 0
    except LexerError as error:
        print(f"error[{error.category}]: {error}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error[runtime]: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("error[interrupted]: processing cancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
