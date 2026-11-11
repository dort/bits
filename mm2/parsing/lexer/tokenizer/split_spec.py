"""Strict split specifications and compiled finite-context matchers."""

from dataclasses import dataclass
import re

from .config import compile_flags, fingerprint, load_json, loads_json
from .model import ConfigurationError, require_python314
from .split_regex import MAX_MATCH_CHARS, compile_pattern


@dataclass(frozen=True, slots=True)
class CompiledSplitSpec:
    mode: str
    literal: str | None
    pattern: re.Pattern | None
    width: int
    retain: str
    preamble: str
    empty_units: str
    max_unit_chars: int
    fingerprint: str


def loads_split_spec(text, *, source="<split specification>"):
    try:
        return compile_split_spec(loads_json(text, source=source))
    except ConfigurationError as error:
        error.source = source
        raise


def load_split_spec(path):
    try:
        return compile_split_spec(load_json(path))
    except ConfigurationError as error:
        error.source = str(path)
        raise


def compile_split_spec(raw):
    require_python314()
    if not isinstance(raw, dict):
        raise ConfigurationError("split specification must be a JSON object")
    if ("separator" in raw) == ("boundary" in raw):
        raise ConfigurationError("require exactly one of separator and boundary")
    mode = "separator" if "separator" in raw else "boundary"
    required = {"version", mode, "max_unit_chars"}
    allowed = required | {"empty_units", "retain" if mode == "separator" else "preamble"}
    if not required <= raw.keys() or raw.keys() - allowed:
        raise ConfigurationError(f"expected {', '.join(sorted(required))}; unknown or missing split field")
    if type(raw["version"]) is not int or raw["version"] != 1:
        raise ConfigurationError("must be the JSON integer 1", field="version")
    limit = raw["max_unit_chars"]
    if type(limit) is not int or limit < 1:
        raise ConfigurationError("must be a positive integer", field="max_unit_chars")
    policies = {}
    for name, default, choices in [("retain", "end", ("end", "gap")),
                                   ("preamble", "unit", ("unit", "reject")),
                                   ("empty_units", "keep", ("keep", "drop"))]:
        value = raw.get(name, default)
        if not isinstance(value, str) or value not in choices:
            raise ConfigurationError(f"must be one of {', '.join(choices)}", field=name)
        policies[name] = value
    matcher = raw[mode]
    if not isinstance(matcher, dict) or ("literal" in matcher) == ("pattern" in matcher):
        raise ConfigurationError("matcher requires exactly one of literal and pattern", field=mode)
    field = "literal" if "literal" in matcher else "pattern"
    allowed = {"literal"} if field == "literal" else {"pattern", "max_length", "flags"}
    if matcher.keys() - allowed:
        raise ConfigurationError("unknown or inapplicable matcher field", field=mode)
    value = matcher[field]
    if not isinstance(value, str) or not value:
        raise ConfigurationError("must be a nonempty string", field=field)
    if field == "literal":
        if len(value) > MAX_MATCH_CHARS:
            raise ConfigurationError(f"literal exceeds {MAX_MATCH_CHARS} characters", field=field)
        literal, pattern, width = value, None, len(value)
    else:
        declared = matcher.get("max_length")
        if type(declared) is not int or not 1 <= declared <= MAX_MATCH_CHARS:
            raise ConfigurationError(f"must be an integer from 1 to {MAX_MATCH_CHARS}", field="max_length")
        pattern, width = compile_pattern(value, compile_flags(matcher.get("flags", [])), declared)
        literal = None
    return CompiledSplitSpec(mode, literal, pattern, width, **policies,
                             max_unit_chars=limit, fingerprint=fingerprint(raw))
