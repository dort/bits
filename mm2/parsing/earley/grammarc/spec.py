"""Load, validate, and compile version-1 grammar specifications.

The JSON schema is the one fixed in the Earley plans: an object with exactly
the fields `version` (the integer 1), `start` (a nonterminal), and
`productions` (a nonempty array of {name, lhs, rhs} objects whose `rhs`
elements each carry exactly one of `nt`/`t`). Nonterminals and production
names are lowercase (`[a-z][a-z0-9_]{0,31}`), terminal kinds uppercase
(`[A-Z][A-Z0-9_]{0,31}`), so the two vocabularies cannot collide. Epsilon
productions (empty `rhs`) are rejected in version 1.
"""

from dataclasses import dataclass
import re

from tokenizer.config import fingerprint, load_json
from tokenizer.model import ConfigurationError, require_python314

NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")
KIND = re.compile(r"[A-Z][A-Z0-9_]{0,31}")


@dataclass(frozen=True)
class Production:
    name: str
    lhs: str
    rhs: tuple  # of ("nt", nonterminal) / ("t", kind) pairs, in body order


@dataclass(frozen=True)
class CompiledGrammar:
    start: str
    productions: tuple
    fingerprint: str  # SHA-256 hex digest of the canonical specification JSON

    @property
    def nonterminals(self):
        return tuple(sorted({production.lhs for production in self.productions}))

    @property
    def terminals(self):
        return tuple(sorted({symbol for production in self.productions
                             for tag, symbol in production.rhs if tag == "t"}))

    @property
    def max_rhs_length(self):
        return max(len(production.rhs) for production in self.productions)

    def check_terminals(self, declared_kinds):
        """Reject terminals outside a token stream's declared kind catalog.

        The catalog comes from `lex-kind` facts or a bundle manifest; a
        grammar terminal the lexer never declares would otherwise fail as a
        silently empty parse instead of a named configuration error.
        """
        missing = sorted(set(self.terminals) - set(declared_kinds))
        if missing:
            raise ConfigurationError(
                "terminals absent from the declared kind catalog: "
                + ", ".join(missing), field="productions")
        return self


def load_grammar(path):
    try:
        return compile_grammar(load_json(path))
    except ConfigurationError as error:
        error.source = str(path)
        raise


def _name(value, field, pattern=NAME):
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ConfigurationError(f"must match {pattern.pattern}", field=field)
    return value


def _compile_production(entry):
    if not isinstance(entry, dict):
        raise ConfigurationError("each production must be an object")
    if set(entry) != {"name", "lhs", "rhs"}:
        raise ConfigurationError("expected exactly the fields name, lhs, and rhs")
    name = _name(entry["name"], "name")
    lhs = _name(entry["lhs"], "lhs")
    if not isinstance(entry["rhs"], list):
        raise ConfigurationError("must be an array", field="rhs")
    if not entry["rhs"]:
        raise ConfigurationError(
            "empty right-hand sides (epsilon productions) are rejected in "
            "version 1", field="rhs")
    body = []
    for element in entry["rhs"]:
        if not isinstance(element, dict) or len(element) != 1:
            raise ConfigurationError(
                "each right-hand-side element carries exactly one of the "
                "fields nt and t", field="rhs")
        ((tag, symbol),) = element.items()
        if tag == "nt":
            body.append((tag, _name(symbol, "rhs")))
        elif tag == "t":
            body.append((tag, _name(symbol, "rhs", KIND)))
        else:
            raise ConfigurationError(
                "each right-hand-side element carries exactly one of the "
                "fields nt and t", field="rhs")
    return Production(name, lhs, tuple(body))


def compile_grammar(raw):
    require_python314()
    if not isinstance(raw, dict):
        raise ConfigurationError("grammar specification must be a JSON object")
    if set(raw) != {"version", "start", "productions"}:
        raise ConfigurationError(
            "expected exactly the fields version, start, and productions")
    if type(raw["version"]) is not int or raw["version"] != 1:
        raise ConfigurationError("must be the JSON integer 1", field="version")
    start = _name(raw["start"], "start")
    if not isinstance(raw["productions"], list) or not raw["productions"]:
        raise ConfigurationError("must be a nonempty array", field="productions")
    productions = []
    names = set()
    for index, entry in enumerate(raw["productions"]):
        try:
            production = _compile_production(entry)
            if production.name in names:
                raise ConfigurationError("duplicate production name", field="name")
        except ConfigurationError as error:
            if error.rule is None:
                error.rule = (entry.get("name", f"#{index}")
                              if isinstance(entry, dict) else f"#{index}")
            raise
        names.add(production.name)
        productions.append(production)
    defined = {production.lhs for production in productions}
    undefined = sorted({symbol for production in productions
                        for tag, symbol in production.rhs
                        if tag == "nt" and symbol not in defined})
    if undefined:
        raise ConfigurationError(
            "nonterminals referenced but defined by no production: "
            + ", ".join(undefined), field="productions")
    if start not in defined:
        raise ConfigurationError(
            f"start nonterminal {start} is defined by no production",
            field="start")
    return CompiledGrammar(start, tuple(productions), fingerprint(raw))
