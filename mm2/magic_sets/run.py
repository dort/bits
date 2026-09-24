#!/usr/bin/env python3
"""Validate the input and run MM2; no rewriting or Datalog evaluation here."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
DEFAULT_MORK = HERE.parents[2] / "MORK/target/release/mork"


def parse(text):
    """Read bare-symbol S-expressions with semicolon comments."""
    tokens = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text))
    stack, roots = [], []
    for token in tokens:
        if token == "(":
            stack.append([])
        elif token == ")":
            if not stack:
                raise ValueError("unmatched closing parenthesis")
            expr = tuple(stack.pop())
            (stack[-1] if stack else roots).append(expr)
        else:
            (stack[-1] if stack else roots).append(token)
    if stack:
        raise ValueError("unclosed parenthesis")
    return roots


def sexpr(expr):
    if isinstance(expr, str):
        return expr
    return "(" + " ".join(map(sexpr, expr)) + ")"


def items(expr):
    result = []
    while expr != "nil":
        if not isinstance(expr, tuple) or len(expr) != 3 or expr[0] != "cons":
            raise ValueError(f"expected cons-list ending in nil: {sexpr(expr)}")
        result.append(expr[1])
        expr = expr[2]
    return result


def symbol(value):
    # Explicit variables are (v name). Native $variables and executable
    # directives are deliberately excluded from the Datalog input language.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:/+\-]+", value):
        raise ValueError(f"expected a bare symbol, got {sexpr(value)}")


def validate(program):
    declarations, arities, rule_ids, query_ids = {}, {}, set(), set()
    for expr in program:
        if not isinstance(expr, tuple) or not expr:
            raise ValueError("each input expression must be a declaration, fact, rule, or query")
        if expr[0] in ("edb", "idb"):
            if len(expr) != 2:
                raise ValueError("predicate declarations have the form (edb NAME) or (idb NAME)")
            kind, name = expr
            symbol(name)
            if name in declarations and declarations[name] != kind:
                raise ValueError(f"{name} cannot be both edb and idb")
            declarations[name] = kind

    def predicate(name, size, kind=None):
        symbol(name)
        if name not in declarations:
            raise ValueError(f"undeclared predicate: {name}")
        if kind is not None and declarations[name] != kind:
            raise ValueError(f"{name} must be declared {kind} in this position")
        if name in arities and arities[name] != size:
            raise ValueError(f"inconsistent arity for {name}: {arities[name]} and {size}")
        arities[name] = size

    def atom(expr, kind=None):
        if not isinstance(expr, tuple) or len(expr) != 3 or expr[0] != "atom":
            raise ValueError(f"expected (atom PREDICATE TERMS): {sexpr(expr)}")
        terms = items(expr[2])
        predicate(expr[1], len(terms), kind)
        variables = set()
        for term in terms:
            if not isinstance(term, tuple) or len(term) != 2 or term[0] not in ("v", "c"):
                raise ValueError(f"terms must be (v NAME) or (c VALUE): {sexpr(term)}")
            symbol(term[1])
            if term[0] == "v":
                variables.add(term[1])
        return variables

    for expr in program:
        tag = expr[0]
        if tag in ("edb", "idb"):
            continue
        if tag == "fact" and len(expr) == 3:
            values = items(expr[2])
            predicate(expr[1], len(values), "edb")
            for value in values:
                symbol(value)
        elif tag == "rule" and len(expr) == 4:
            _, name, head, body = expr
            symbol(name)
            if name in rule_ids:
                raise ValueError(f"duplicate rule identifier: {name}")
            rule_ids.add(name)
            head_vars = atom(head, "idb")
            body_vars = set()
            for literal in items(body):
                body_vars.update(atom(literal))
            if not head_vars <= body_vars:
                raise ValueError(f"unsafe rule {name}: head variables absent from body: {sorted(head_vars - body_vars)}")
        elif tag == "query" and len(expr) == 3:
            symbol(expr[1])
            if expr[1] in query_ids:
                raise ValueError(f"duplicate query identifier: {expr[1]}")
            query_ids.add(expr[1])
            atom(expr[2])
        else:
            raise ValueError(f"unsupported input form: {sexpr(expr)}")
    return declarations


def run_file(path, engine="magic", timeout=60):
    path = Path(path).resolve()
    validate(parse(path.read_text()))
    binary = os.environ.get("MORK", str(DEFAULT_MORK))
    completed = subprocess.run(
        [binary, "run", str(path), "--aux-path", str(HERE / f"{engine}_engine.mm2"),
         "--aux-path", str(HERE / "common.mm2")],
        text=True, capture_output=True, timeout=timeout, check=True,
    )
    log, marker, dump = completed.stdout.partition("result:\n")
    if not marker:
        raise RuntimeError("MORK did not return a space dump:\n" + completed.stdout + completed.stderr)
    space = parse(dump)
    if any(isinstance(expr, tuple) and expr and expr[0] == "exec" for expr in space):
        raise RuntimeError("MORK stopped with unexecuted instructions; result is incomplete")
    return space, log


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=HERE / "example.mm2")
    parser.add_argument("--engine", choices=("magic", "plain"), default="magic")
    parser.add_argument("--show", choices=("answers", "rules", "magic", "derived", "all"), default="answers")
    parser.add_argument("--stats", action="store_true", help="report MORK counters and relation sizes on stderr")
    parser.add_argument("--timeout", type=float, default=60, help="seconds before aborting, not a semantic iteration bound")
    args = parser.parse_args()
    try:
        space, log = run_file(args.input, args.engine, args.timeout)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stdout + exc.stderr, file=sys.stderr)
        return 1
    tags = {"answers": {"result"}, "rules": {"generated"}, "magic": {"magic"},
            "derived": {"derived", "closure"}}
    for expr in space:
        if args.show == "all" or (isinstance(expr, tuple) and expr and expr[0] in tags[args.show]):
            print(sexpr(expr))
    if args.stats:
        for line in log.splitlines():
            if line.startswith("executing "):
                print(line, file=sys.stderr)
        for tag in ("result", "generated", "magic", "derived", "closure"):
            print(f"{tag}: {sum(isinstance(e, tuple) and bool(e) and e[0] == tag for e in space)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
