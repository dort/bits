"""Strict declarative specification loading; no executable configuration."""

from dataclasses import dataclass
import re

from .config import compile_flags, fingerprint, load_json, loads_json
from .model import ConfigurationError, require_python314, validate_identifier


@dataclass(frozen=True, slots=True)
class Rule:
    name: str
    kind: str | None
    literal: str | None
    pattern: re.Pattern | None


@dataclass(frozen=True, slots=True)
class CompiledSpec:
    rules: tuple[Rule, ...]
    kinds: tuple[str, ...]
    fingerprint: str


def loads_spec(text, *, source="<specification>"):
    try:
        return compile_spec(loads_json(text, source=source))
    except ConfigurationError as error:
        error.source = source
        raise


def load_spec(path):
    try:
        return compile_spec(load_json(path))
    except ConfigurationError as error:
        error.source = str(path)
        raise


def compile_spec(raw):
    require_python314()
    if not isinstance(raw, dict):
        raise ConfigurationError("specification must be a JSON object")
    if set(raw) != {"version", "rules"}:
        raise ConfigurationError("expected exactly the fields version and rules")
    if type(raw["version"]) is not int or raw["version"] != 1:
        raise ConfigurationError("must be the JSON integer 1", field="version")
    if not isinstance(raw["rules"], list) or not raw["rules"]:
        raise ConfigurationError("must be a nonempty array", field="rules")
    rules = []
    names = set()
    for index, entry in enumerate(raw["rules"]):
        try:
            rule = _compile_rule(entry)
            if rule.name in names:
                raise ConfigurationError("duplicate rule name", field="name")
        except ConfigurationError as error:
            name = entry.get("name", f"#{index}") if isinstance(entry, dict) else f"#{index}"
            error.rule = name
            raise
        names.add(rule.name)
        rules.append(rule)
    return CompiledSpec(tuple(rules), tuple(sorted({r.kind for r in rules if r.kind})),
                        fingerprint(raw))


def _compile_rule(entry):
    if not isinstance(entry, dict):
        raise ConfigurationError("each rule must be an object")
    unknown = set(entry) - {"name", "literal", "pattern", "kind", "skip", "flags"}
    if unknown:
        raise ConfigurationError("unknown rule field", field=next(iter(unknown)))
    name = validate_identifier(entry.get("name"), "name")
    if ("literal" in entry) == ("pattern" in entry):
        raise ConfigurationError("require exactly one of literal and pattern")
    if ("kind" in entry) == ("skip" in entry):
        raise ConfigurationError("require exactly one of kind and skip")
    if "kind" in entry:
        kind = validate_identifier(entry["kind"], "kind", terminal=True)
    else:
        if entry["skip"] is not True:
            raise ConfigurationError("must be true", field="skip")
        kind = None
    field = "literal" if "literal" in entry else "pattern"
    value = entry[field]
    if not isinstance(value, str) or not value:
        raise ConfigurationError("must be a nonempty string", field=field)
    if field == "literal":
        if "flags" in entry:
            raise ConfigurationError("literal rules do not accept flags", field="flags")
        return Rule(name, kind, value, None)
    mask = compile_flags(entry.get("flags", []))
    try:
        pattern = re.compile(value, flags=mask)
    except (re.PatternError, ValueError, OverflowError) as error:
        raise ConfigurationError(str(error), field="pattern",
                                 pattern_offset=getattr(error, "pos", None)) from error
    if pattern.match("") is not None:
        raise ConfigurationError("pattern matches empty input", field="pattern")
    return Rule(name, kind, None, pattern)
