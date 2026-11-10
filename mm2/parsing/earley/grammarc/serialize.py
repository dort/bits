"""Serialize compiled grammars and engine-contract data facts.

Every emitted atom passes the lexer's `checked_atom` guard (the non-interning
MORK reader silently truncates atoms beyond 63 bytes); grammar names are at
most 32 characters by schema, so everything here is short by construction.
"""

from tokenizer.model import validate_identifier
from tokenizer.serialize import checked_atom

MAX_ROUNDS = 998  # three-digit zero-padded round symbols: r001 .. r999


def _render(piece):
    if isinstance(piece, (tuple, list)):
        return "(" + " ".join(_render(inner) for inner in piece) + ")"
    return checked_atom(piece)


def _fact(*pieces):
    return _render(pieces) + "\n"


def grammar_facts(grammar, grammar_id):
    """Yield the grm-* fact lines for one compiled grammar.

    `grammar_id` follows the namespace identifier regime; it denotes one
    immutable compiled grammar, and loading two different grammars under one
    id would merge their facts, so the caller enforces uniqueness.
    """
    validate_identifier(grammar_id, "grammar_id")
    digest = grammar.fingerprint
    yield _fact("grm-grammar", grammar_id, 1)
    yield _fact("grm-spec", grammar_id, "sha256",
                "h" + digest[:32], "h" + digest[32:])
    yield _fact("grm-start", grammar_id, grammar.start)
    for production in grammar.productions:
        yield _fact("grm-prod", grammar_id, production.name, production.lhs,
                    len(production.rhs))
        for position, (tag, symbol) in enumerate(production.rhs):
            yield _fact("grm-rhs", grammar_id, production.name, position,
                        (tag, symbol))
    for dot in range(grammar.max_rhs_length):
        yield _fact("grm-dot", grammar_id, dot, dot + 1)


def demand_fact(namespace, stream_id, grammar_id):
    """The (parse NS S G) fact requesting one stream/grammar recognition."""
    validate_identifier(namespace, "namespace")
    validate_identifier(stream_id, "stream_id")
    validate_identifier(grammar_id, "grammar_id")
    return _fact("parse", namespace, stream_id, grammar_id)


def round_table_facts(rounds):
    """The engines' sweep schedule: a chained round table plus (budget B).

    The engines start at round symbol r001 and write (swept B) only after the
    whole table is consumed; symbols are three-digit zero-padded because MM2
    compares symbols length-first.
    """
    if type(rounds) is not int or not 1 <= rounds <= MAX_ROUNDS:
        raise ValueError(f"rounds must be an integer in 1..{MAX_ROUNDS}, got {rounds!r}")
    lines = [_fact("nextround", f"r{i:03d}", f"r{i + 1:03d}")
             for i in range(1, rounds + 1)]
    lines.append(_fact("budget", f"b{rounds:03d}"))
    return "".join(lines)
