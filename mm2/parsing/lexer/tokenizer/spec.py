"""Strict declarative specification loading; no executable configuration."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .model import ConfigurationError, require_python314, validate_identifier


FLAGS = {name: getattr(re, name) for name in
         ("ASCII", "IGNORECASE", "MULTILINE", "DOTALL", "VERBOSE")}


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


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError("duplicate JSON key", field=key)
        result[key] = value
    return result


def _constant(value):
    raise ConfigurationError(f"non-JSON constant {value}")


def loads_spec(text, *, source="<specification>"):
    require_python314()
    try:
        raw = json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
        return compile_spec(raw)
    except json.JSONDecodeError as error:
        raise ConfigurationError(error.msg, source=source, offset=error.pos,
                                 line=error.lineno, column=error.colno) from error
    except ConfigurationError as error:
        error.source = source
        raise


def load_spec(path):
    require_python314()
    try:
        text = Path(path).read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as error:
        raise ConfigurationError(str(error), source=str(path)) from error
    return loads_spec(text, source=str(path))


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
    canonical = json.dumps(raw, ensure_ascii=True, sort_keys=True,
                           separators=(",", ":"), allow_nan=False).encode("ascii")
    return CompiledSpec(tuple(rules), tuple(sorted({r.kind for r in rules if r.kind})),
                        hashlib.sha256(canonical).hexdigest())


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
    flags = entry.get("flags", [])
    if not isinstance(flags, list):
        raise ConfigurationError("must be an array of flag names", field="flags")
    seen = set()
    mask = re.NOFLAG
    for flag in flags:
        if not isinstance(flag, str) or flag not in FLAGS or flag in seen:
            raise ConfigurationError("unknown or duplicate regex flag", field="flags")
        seen.add(flag)
        mask |= FLAGS[flag]
    try:
        pattern = re.compile(value, flags=mask)
    except (re.PatternError, ValueError, OverflowError) as error:
        raise ConfigurationError(str(error), field="pattern",
                                 pattern_offset=getattr(error, "pos", None)) from error
    if pattern.match("") is not None:
        raise ConfigurationError("pattern matches empty input", field="pattern")
    return Rule(name, kind, None, pattern)
