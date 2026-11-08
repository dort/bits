"""Reproducible synthetic measurements; each stage runs in a fresh process."""

import argparse
import io
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import sysconfig
import tempfile
import time
import unicodedata

from tokenizer import (compile_spec, iter_jsonl, iter_mm2, load_spec, read_stream,
                       tokenize, write_bundle)
from tokenizer.model import DEFAULT_MAX_BYTES, DEFAULT_MAX_CHARS


HERE = Path(__file__).resolve().parents[1]
MORK = HERE.parents[3] / "MORK/target/release/mork"


def fixture(case, size):
    if case == "expression":
        compiled = load_spec(HERE / "specs/expression_demo.json")
        unit = "x + 0012 "
    elif case == "many-rules":
        rules = [{"name": f"keyword{i}", "literal": f"keyword{i:02}", "kind": "KEYWORD"}
                 for i in range(40)]
        rules += [{"name": "word", "pattern": "[a-z0-9]+", "kind": "WORD"},
                  {"name": "space", "literal": " ", "skip": True}]
        compiled = compile_spec({"version": 1, "rules": rules})
        unit = "keyword39 aaa "
    elif case == "characters":
        compiled = load_spec(HERE / "specs/characters_demo.json")
        unit = "λ 😀\n"
    elif case == "unicode-token":
        compiled = compile_spec({"version": 1, "rules": [
            {"name": "all", "pattern": ".+", "flags": ["DOTALL"], "kind": "TEXT"}]})
        unit = "😀"
    else:
        raise ValueError(case)
    return (unit * ((size + len(unit) - 1) // len(unit)))[:size], compiled


def worker(case, size, stage):
    text, compiled = fixture(case, size)
    def records():
        return tokenize(text, compiled, namespace="bench", stream_id="s0", max_chars=max(size, DEFAULT_MAX_CHARS))
    prepared = list(records()) if stage == "serialize" else None
    root = HERE / "output/benchmark-tmp"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        directory = Path(temporary)
        if stage == "mork":
            write_bundle(records(), directory / "input")
        start = time.perf_counter()
        output_size = 0
        token_count = None
        if stage == "lexer":
            for record in records():
                if record.type == "stream-end":
                    token_count = record.token_count
        elif stage == "source":
            raw = text.encode("utf-8")
            source = read_stream(io.BytesIO(raw), max_chars=max(size, DEFAULT_MAX_CHARS),
                                 max_bytes=max(len(raw), DEFAULT_MAX_BYTES))
            if source.text != text:
                raise RuntimeError("decoded benchmark input differs")
        elif stage == "serialize":
            with (directory.joinpath("tokens.jsonl").open("w", encoding="ascii") as jsonl,
                  directory.joinpath("tokens.mm2").open("w", encoding="ascii") as mm2):
                jsonl.writelines(iter_jsonl(prepared))
                mm2.writelines(iter_mm2(prepared))
            output_size = sum(path.stat().st_size for path in directory.iterdir())
        elif stage == "bundle":
            manifest = write_bundle(records(), directory / "result")
            token_count = manifest["token_count"]
            output_size = sum(path.stat().st_size for path in directory.joinpath("result").iterdir())
        elif stage == "mork":
            binary = os.environ.get("MORK", str(MORK))
            subprocess.run([binary, "run", str(directory / "input/tokens.mm2"),
                            str(directory / "space.mm2")], check=True, capture_output=True, timeout=60)
            output_size = directory.joinpath("space.mm2").stat().st_size
        elapsed = time.perf_counter() - start
    usage = resource.RUSAGE_CHILDREN if stage == "mork" else resource.RUSAGE_SELF
    return dict(case=case, chars=len(text), utf8_bytes=len(text.encode("utf-8")),
                rules=len(compiled.rules), stage=stage, seconds=round(elapsed, 6),
                peak_rss_kib=resource.getrusage(usage).ru_maxrss,
                output_bytes=output_size, token_count=token_count)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[4096, 32768])
    parser.add_argument("--cases", nargs="+", default=["expression", "many-rules", "characters", "unicode-token"])
    parser.add_argument("--stages", nargs="+", default=["lexer", "serialize", "bundle", "mork"])
    parser.add_argument("--report", default="output/benchmark.json")
    parser.add_argument("--worker", nargs=3, metavar=("CASE", "SIZE", "STAGE"))
    args = parser.parse_args()
    if args.worker:
        case, size, stage = args.worker
        print(json.dumps(worker(case, int(size), stage)))
        return
    rows = []
    for case in args.cases:
        for size in args.sizes:
            for stage in args.stages:
                result = subprocess.run([sys.executable, "-m", "benchmarks.measure", "--worker",
                                         case, str(size), stage], cwd=HERE, check=True,
                                        capture_output=True, text=True, timeout=90)
                row = json.loads(result.stdout)
                rows.append(row)
                print(json.dumps(row), flush=True)
    report = dict(python=sys.version, executable=sys.executable,
                  unicode=unicodedata.unidata_version,
                  configure_args=sysconfig.get_config_var("CONFIG_ARGS"),
                  notes=["Linux peak RSS in KiB; each row runs in a fresh process.",
                         "Serialization time excludes lexing; its RSS includes prebuilt records.",
                         "Bundle RSS measures streaming records without retaining a token list.",
                         "MORK time includes process startup, loading, and dumping; no parser rules.",
                         "Source time includes UTF-8 encoding the synthetic fixture."], rows=rows)
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
