"""Span-keyed forest traversal and bounded tree enumeration.

The forest is the `node`/`part` fact set a forest-engine dump carries for one
(namespace, stream, grammar). Three entities have distinct identities: a
symbol node `(A, O, P)`, an intermediate prefix `(R, D, O, P)` (the first `D`
symbols of production `R` spanning tokens `O..P`), and a packed alternative —
one whole `part` fact, child descriptor included. Traversal is
production-aware: a child descriptor `(nt A R2)` commits to production `R2`,
and expanding the child's symbol node through every production of `A` instead
would emit duplicate trees, because the parent already holds one edge per
child production.

Enumeration is bounded by a tree count, a nonterminal nesting depth, and the
optional deadline given to the constructor, and reports whether it exhausted
all alternatives: the stored graph is finite but may contain cycles (unit
productions), and even an acyclic ambiguous graph can hold exponentially many
trees. Traversal keeps its state on explicit stacks, so the supported limits
govern termination; the Python call stack never grows with graph depth.

A `deadline` is any object with `check()`, which raises when the caller's
wall-time budget is exhausted, and `expired()`, which reports it; the runner
passes its per-unit deadline. Construction and `graph()` raise through
`check()`; `enumerate` instead stops and reports the output incomplete, so
the trees found before expiry are kept.
"""

from .facts import select


def _copy_tree(tree, deadline=None):
    """A structural copy of one finished tree, without recursion.

    Enumeration reuses its mutable skeleton nodes across alternatives, so an
    emitted tree must not share them. The copy itself is work under the
    caller's deadline: on expiry it returns None and the unfinished copy is
    discarded.
    """
    duplicate = dict(tree)
    duplicate["span"] = list(tree["span"])
    stack = [(tree, duplicate)]
    count = 0
    while stack:
        if deadline is not None and not count % 256 and deadline.expired():
            return None
        count += 1
        original, copy = stack.pop()
        if "children" not in original:
            continue
        copies = []
        for child in original["children"]:
            child_copy = dict(child)
            child_copy["span"] = list(child["span"])
            copies.append(child_copy)
            stack.append((child, child_copy))
        copy["children"] = copies
    return duplicate


class Forest:
    def __init__(self, grammar, facts, namespace, stream_id, grammar_id,
                 deadline=None):
        self.grammar = grammar
        self.deadline = deadline
        self.key = (namespace, stream_id, grammar_id)
        self.productions = {production.name: production
                            for production in grammar.productions}
        self.by_symbol = {}   # nonterminal -> [productions with that lhs]
        for production in grammar.productions:
            self.by_symbol.setdefault(production.lhs, []).append(production)
        self.nodes = {fact[4:7] for fact in select(facts, "node", *self.key)}
        self.parts = {}       # prefix (R, D, O, P) -> sorted [(M, C), ...]
        for count, fact in enumerate(select(facts, "part", *self.key)):
            if deadline is not None and not count % 1024:
                deadline.check()
            _, _, _, _, name, dot, origin, split, end, child = fact
            self.parts.setdefault((name, dot, origin, end), set()).add((split, child))
        self.parts = {prefix: sorted(pairs) for prefix, pairs in self.parts.items()}
        ends = select(facts, "lex-end", namespace, stream_id)
        if len(ends) != 1:
            raise ValueError(f"expected one lex-end fact for {namespace}/{stream_id}, "
                             f"found {len(ends)}")
        self.length = next(iter(ends))[3]

    @property
    def roots(self):
        """The start-symbol node spanning the whole input, when it exists.

        Distinct accepting start productions are packed alternatives of this
        one node, not separate roots.
        """
        root = (self.grammar.start, "0", self.length)
        return [root] if root in self.nodes else []

    def graph(self):
        """The complete alternative set as JSON-ready data (lossless)."""
        parts = []
        for count, ((name, dot, origin, end), pairs) in enumerate(self.parts.items()):
            if self.deadline is not None and not count % 1024:
                self.deadline.check()
            parts.extend([name, int(dot), int(origin), int(split), int(end),
                          list(child)]
                         for split, child in pairs)
        return {
            "namespace": self.key[0], "stream_id": self.key[1],
            "grammar_id": self.key[2], "start": self.grammar.start,
            "length": int(self.length),
            "nodes": sorted([symbol, int(origin), int(end)]
                            for symbol, origin, end in self.nodes),
            "parts": sorted(parts),
        }

    def enumerate(self, max_trees, max_depth):
        """Concrete trees from the roots: (trees, complete).

        `complete` is True only when every alternative was exhausted within
        both limits and the deadline; a cycle, a count/depth cut, or deadline
        expiry makes it False. A tree is `{"nt": A, "production": R, "span":
        [O, P], "children": [...]}` with terminal leaves `{"t": K, "span":
        [M, P]}` — Remy's full-child-list shape, produced here as a bounded
        output view of the packed graph.

        The traversal is a depth-first search over explicit choice points.
        Tasks fill the child slots of mutable tree skeletons; each choice
        point snapshots the pending task list and restores it per
        alternative, and a finished tree is copied out because later
        alternatives reassign the same slots.
        """
        for label, value in (("max_trees", max_trees), ("max_depth", max_depth)):
            if type(value) is not int or value < 1:
                raise ValueError(f"{label} must be a positive integer, got {value!r}")
        deadline = self.deadline
        trees = []
        truncated = False
        steps = 0
        for start_symbol, start_origin, start_end in self.roots:
            holder = [None]
            # The root's alternatives are its productions; every later choice
            # point is the packed-alternative set of one prefix.
            root_options = [("root", production)
                            for production in self.by_symbol.get(start_symbol, ())]
            choices = [(root_options, [])]  # (untried alternatives, agenda snapshot)
            while choices:
                options, snapshot = choices[-1]
                if not options:
                    choices.pop()
                    continue
                if deadline is not None and deadline.expired():
                    return trees, False
                alternative = options.pop(0)
                agenda = list(snapshot)
                if alternative[0] == "root":
                    production = alternative[1]
                    node = {"nt": start_symbol, "production": production.name,
                            "span": [int(start_origin), int(start_end)],
                            "children": [None] * len(production.rhs)}
                    holder[0] = node
                    agenda.append(("seq", production, len(production.rhs),
                                   start_origin, start_end, 1, node["children"]))
                else:
                    _, production, dot, origin, end, depth, children, split, child = alternative
                    agenda.append(("seq", production, dot - 1, origin, split,
                                   depth, children))
                    agenda.append(("tree", child, split, end, depth,
                                   children, dot - 1))
                dead = opened = False
                while agenda:
                    steps += 1
                    if deadline is not None and not steps % 64 and deadline.expired():
                        return trees, False
                    task = agenda.pop()
                    if task[0] == "seq":
                        _, production, dot, origin, end, depth, children = task
                        if dot == 0:
                            if origin != end:
                                dead = True
                                break
                            continue
                        pairs = self.parts.get((production.name, str(dot), origin, end), ())
                        if not pairs:
                            dead = True
                            break
                        choices.append((
                            [("part", production, dot, origin, end, depth,
                              children, split, child) for split, child in pairs],
                            list(agenda)))
                        opened = True
                        break
                    _, child, start, end, depth, children, index = task
                    if child[0] == "t":
                        children[index] = {"t": child[1], "span": [int(start), int(end)]}
                        continue
                    _, symbol, name = child
                    production = self.productions.get(name)
                    if production is None or production.lhs != symbol:
                        raise ValueError(f"child descriptor names unknown or mismatched "
                                         f"production {name!r} for nonterminal {symbol!r}")
                    if depth + 1 > max_depth:
                        truncated = True
                        dead = True
                        break
                    node = {"nt": symbol, "production": name,
                            "span": [int(start), int(end)],
                            "children": [None] * len(production.rhs)}
                    children[index] = node
                    agenda.append(("seq", production, len(production.rhs),
                                   start, end, depth + 1, node["children"]))
                if dead or opened:
                    continue
                # The agenda is exhausted: holder[0] is one complete tree.
                if len(trees) >= max_trees:
                    return trees, False
                copy = _copy_tree(holder[0], deadline)
                if copy is None:
                    return trees, False
                trees.append(copy)
        # A completion claim must still be inside the budget: work since the
        # last periodic check (the final copy, exhausting the choice stack)
        # may have crossed the deadline.
        if deadline is not None and deadline.expired():
            return trees, False
        return trees, not truncated
