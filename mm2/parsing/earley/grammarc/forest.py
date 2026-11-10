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

Enumeration is bounded by a tree count and a nonterminal nesting depth and
reports whether it exhausted all alternatives: the stored graph is finite but
may contain cycles (unit productions), and even an acyclic ambiguous graph
can hold exponentially many trees.
"""

from .facts import select


class Forest:
    def __init__(self, grammar, facts, namespace, stream_id, grammar_id):
        self.grammar = grammar
        self.key = (namespace, stream_id, grammar_id)
        self.productions = {production.name: production
                            for production in grammar.productions}
        self.by_symbol = {}   # nonterminal -> [productions with that lhs]
        for production in grammar.productions:
            self.by_symbol.setdefault(production.lhs, []).append(production)
        self.nodes = {fact[4:7] for fact in select(facts, "node", *self.key)}
        self.parts = {}       # prefix (R, D, O, P) -> sorted [(M, C), ...]
        for fact in select(facts, "part", *self.key):
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
        return {
            "namespace": self.key[0], "stream_id": self.key[1],
            "grammar_id": self.key[2], "start": self.grammar.start,
            "length": int(self.length),
            "nodes": sorted([symbol, int(origin), int(end)]
                            for symbol, origin, end in self.nodes),
            "parts": sorted(
                [name, int(dot), int(origin), int(split), int(end),
                 list(child)]
                for (name, dot, origin, end), pairs in self.parts.items()
                for split, child in pairs),
        }

    def enumerate(self, max_trees, max_depth):
        """Concrete trees from the roots: (trees, complete).

        `complete` is True only when every alternative was exhausted within
        both limits; a cycle or a count/depth cut makes it False. A tree is
        `{"nt": A, "production": R, "span": [O, P], "children": [...]}` with
        terminal leaves `{"t": K, "span": [M, P]}` — Remy's full-child-list
        shape, produced here as a bounded output view of the packed graph.
        """
        for label, value in (("max_trees", max_trees), ("max_depth", max_depth)):
            if type(value) is not int or value < 1:
                raise ValueError(f"{label} must be a positive integer, got {value!r}")
        trees = []
        truncated = False

        def symbol_trees(symbol, origin, end, depth):
            nonlocal truncated
            if depth > max_depth:
                truncated = True
                return
            for production in self.by_symbol.get(symbol, ()):
                for children in child_sequences(production, len(production.rhs),
                                                origin, end, depth):
                    yield {"nt": symbol, "production": production.name,
                           "span": [int(origin), int(end)], "children": children}

        def child_sequences(production, dot, origin, end, depth):
            if dot == 0:
                if origin == end:
                    yield []
                return
            key = (production.name, str(dot), origin, end)
            for split, child in self.parts.get(key, ()):
                for last in child_trees(child, split, end, depth):
                    for rest in child_sequences(production, dot - 1, origin,
                                                split, depth):
                        yield rest + [last]

        def child_trees(child, start, end, depth):
            nonlocal truncated
            if child[0] == "t":
                yield {"t": child[1], "span": [int(start), int(end)]}
                return
            _, symbol, name = child
            production = self.productions.get(name)
            if production is None or production.lhs != symbol:
                raise ValueError(f"child descriptor names unknown or mismatched "
                                 f"production {name!r} for nonterminal {symbol!r}")
            if depth + 1 > max_depth:
                truncated = True
                return
            for children in child_sequences(production, len(production.rhs),
                                            start, end, depth + 1):
                yield {"nt": symbol, "production": name,
                       "span": [int(start), int(end)], "children": children}

        for symbol, origin, end in self.roots:
            for tree in symbol_trees(symbol, origin, end, 1):
                if len(trees) >= max_trees:
                    truncated = True
                    return trees, False
                trees.append(tree)
        return trees, not truncated
