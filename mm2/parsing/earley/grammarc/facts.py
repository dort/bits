"""Parse and select MM2 facts from engine dumps.

A dump is read back as nested tuples whose leaves are atom strings. The
canonical semantic projection defined here is what the runner compares across
increasing sweep budgets: the deduplicated rendered `item`/`accepted` facts of
one (namespace, stream, grammar) triple, plus `node`/`part` in forest mode,
excluding round tables, execution instructions, and instrumentation.
"""

import re

_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^()\s]+')

RECOGNITION_HEADS = ("item", "accepted")
FOREST_HEADS = ("item", "accepted", "node", "part")


def parse_facts(text, deadline=None):
    """Parse a dump or fixture into nested tuples; atoms stay strings.

    Each fact is one parenthesized expression; the dump writes one per line,
    but the parser only relies on balanced parentheses. Lines whose first
    nonblank character is ';' are comments (fixtures carry them, dumps do
    not) and are skipped. `deadline` is an object whose `check()` raises when
    the caller's wall-time budget is exhausted; it is consulted periodically
    because a dump can be tens of megabytes.
    """
    text = "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith(";"))
    facts = []
    stack = []
    for count, match in enumerate(_TOKEN.finditer(text)):
        if deadline is not None and not count % 4096:
            deadline.check()
        token = match.group()
        if token == "(":
            stack.append([])
        elif token == ")":
            if not stack:
                raise ValueError(f"unbalanced ')' at offset {match.start()}")
            done = tuple(stack.pop())
            if stack:
                stack[-1].append(done)
            else:
                facts.append(done)
        else:
            if not stack:
                raise ValueError(f"atom {token!r} outside a fact at offset {match.start()}")
            stack[-1].append(token)
    if stack:
        raise ValueError("unbalanced '(' at end of dump")
    return facts


def render(expr):
    if isinstance(expr, tuple):
        return "(" + " ".join(render(piece) for piece in expr) + ")"
    return expr


def select(facts, head, *prefix):
    """Facts whose first atom is `head` and whose next atoms match `prefix`."""
    return {fact for fact in facts
            if fact and fact[0] == head and fact[1:1 + len(prefix)] == prefix}


def projection(facts, namespace, stream, grammar, heads, deadline=None):
    """The canonical semantic projection for one (namespace, stream, grammar)."""
    chosen = set()
    for head in heads:
        for count, fact in enumerate(select(facts, head, namespace, stream, grammar)):
            if deadline is not None and not count % 1024:
                deadline.check()
            chosen.add(render(fact))
    return frozenset(chosen)
