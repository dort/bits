"""Benchmark case registry: grammars, unit texts, deterministic identities.

A case names one measured configuration: a grammar, a unit-text generator with
a token count, a unit count, an engine, and optional runner limit overrides.
Its `case_id` is a pure function of those parameters, so a run is repeatable
from the registry arguments alone. The registry covers the four assigned
dimensions: unit-count scaling with everything else fixed, tokens-per-unit
scaling across grammar shapes (including a long-token text that separates
character count from parser work), engine comparison on one fixed input, and
deliberate limit exhaustion.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
LEXER_SPEC = PROJECT.parent / "lexer/specs/expression_demo.json"
EXPR_GRAMMAR = PROJECT / "tests/fixtures/grammar_expr_demo.json"
CHAIN_DEPTH = 31

# One short MM2 grammar identifier per grammar key; a grammar ID is an atom in
# every emitted fact, so the spelling is fixed here for reproducibility.
GRAMMAR_IDS = {"expr": "gexp", "right": "grgt", "chain": "gchn", "concat": "gcat"}


def _expr():
    """The worked-example grammar, from its pinned test fixture."""
    return json.loads(EXPR_GRAMMAR.read_text())


def _right():
    """Right-recursive integer list: list -> INT list | INT."""
    return {"version": 1, "start": "list", "productions": [
        {"name": "cons", "lhs": "list", "rhs": [{"t": "INT"}, {"nt": "list"}]},
        {"name": "last", "lhs": "list", "rhs": [{"t": "INT"}]}]}


def _chain(depth=CHAIN_DEPTH):
    """A unit-production chain ending in a right-recursive integer list.

    The chain forces sweeps proportional to its depth before the first token
    can contribute; the list bottom lets the token count scale independently.
    """
    last = depth - 1
    productions = [{"name": f"c{i:02d}", "lhs": f"a{i:02d}",
                    "rhs": [{"nt": f"a{i + 1:02d}"}]} for i in range(last)]
    productions += [
        {"name": "more", "lhs": f"a{last:02d}",
         "rhs": [{"t": "INT"}, {"nt": f"a{last:02d}"}]},
        {"name": "last", "lhs": f"a{last:02d}", "rhs": [{"t": "INT"}]}]
    return {"version": 1, "start": "a00", "productions": productions}


def _concat():
    """Ambiguous concatenation: s -> s s | INT (Catalan-many trees)."""
    return {"version": 1, "start": "s", "productions": [
        {"name": "join", "lhs": "s", "rhs": [{"nt": "s"}, {"nt": "s"}]},
        {"name": "one", "lhs": "s", "rhs": [{"t": "INT"}]}]}


GRAMMARS = {"expr": _expr, "right": _right, "chain": _chain, "concat": _concat}


def _fixed_text(tokens):
    """The worked example `x + 12` (3 tokens, pinned 13-item chart)."""
    if tokens != 3:
        raise ValueError("the fixed unit is exactly 3 tokens")
    return "x + 12"


def _expr_text(tokens):
    """`1 + 2 + ...`: k integers and k-1 pluses, so the count must be odd."""
    if tokens % 2 == 0 or tokens < 1:
        raise ValueError("expression token counts are odd and positive")
    return " + ".join(str(i % 97 + 1) for i in range((tokens + 1) // 2))


def _long_text(tokens):
    """The expression shape with 24-character identifiers as operands.

    Token count matches `_expr_text` while character count is roughly eight
    times larger, separating lexing/transport cost from parser work.
    """
    if tokens % 2 == 0 or tokens < 1:
        raise ValueError("expression token counts are odd and positive")
    return " + ".join(f"v{i:05d}" + "x" * 18 for i in range((tokens + 1) // 2))


def _ints_text(tokens):
    """`1 2 3 ...`: a flat integer sequence of exactly `tokens` tokens."""
    if tokens < 1:
        raise ValueError("token counts are positive")
    return " ".join(str(i % 97 + 1) for i in range(tokens))


TEXTS = {"fixed": _fixed_text, "expr": _expr_text, "long": _long_text,
         "ints": _ints_text}


@dataclass
class Case:
    case_id: str
    dimension: str              # units | tokens | engines | limits | control
    grammar: str                # GRAMMARS key
    text: str                   # TEXTS key
    tokens_per_unit: int
    unit_count: int = 1
    engine: str = "recognition"
    max_trees: int | None = None
    max_depth: int | None = None
    runner: dict = field(default_factory=dict)  # Runner keyword overrides
    expect: str | None = None   # expected recognition, for the report only


def registry(*, units=(4, 16, 64), expr_tokens=(7, 15, 31),
             ints_tokens=(7, 15, 31), chain_tokens=(1, 7, 15),
             concat_tokens=(3, 8)):
    """Every case of one run, in execution order, with deterministic IDs.

    The defaults are the quick configuration; larger workloads are requested
    explicitly through the harness flags that feed these parameters.
    """
    cases = [Case("control-mork", "control", "expr", "fixed", 3)]
    for count in units:
        cases.append(Case(f"units-n{count:05d}", "units", "expr", "fixed", 3,
                          unit_count=count, expect="accepted"))
    for tokens in expr_tokens:
        cases.append(Case(f"tokens-expr-n{tokens:04d}", "tokens", "expr",
                          "expr", tokens, expect="accepted"))
        cases.append(Case(f"tokens-long-n{tokens:04d}", "tokens", "expr",
                          "long", tokens, expect="accepted"))
    for tokens in ints_tokens:
        cases.append(Case(f"tokens-right-n{tokens:04d}", "tokens", "right",
                          "ints", tokens, expect="accepted"))
    for tokens in chain_tokens:
        cases.append(Case(f"tokens-chain-n{tokens:04d}", "tokens", "chain",
                          "ints", tokens, expect="accepted"))
    for tokens in concat_tokens:
        cases.append(Case(f"tokens-concat-n{tokens:04d}", "tokens", "concat",
                          "ints", tokens, expect="accepted"))
    tokens = max(concat_tokens)
    for suffix, engine, trees, depth in (("recognition", "recognition", None, None),
                                         ("forest", "forest", None, None),
                                         ("trees", "forest", 512, 40)):
        cases.append(Case(f"engines-concat-n{tokens:04d}-{suffix}", "engines",
                          "concat", "ints", tokens, engine=engine,
                          max_trees=trees, max_depth=depth, expect="accepted"))
    cases += [
        Case("limits-sweeps", "limits", "chain", "ints", 1,
             runner={"initial_rounds": 4, "max_sweeps": 4}, expect="incomplete"),
        Case("limits-walltime", "limits", "expr", "expr", 31,
             runner={"timeout_seconds": 0.05}, expect="incomplete"),
        Case("limits-tokens", "limits", "expr", "expr", 31,
             runner={"max_tokens": 8}, expect="incomplete"),
        Case("limits-trees", "limits", "concat", "ints", 8, engine="forest",
             max_trees=2, max_depth=40, expect="accepted"),
        Case("limits-depth", "limits", "concat", "ints", 8, engine="forest",
             max_trees=512, max_depth=2, expect="accepted"),
    ]
    return cases
