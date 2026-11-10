"""Shared JSON, fingerprint, and regex-flag handling for specification compilers."""

import hashlib
import json
from pathlib import Path
import re

from .model import ConfigurationError, require_python314


FLAGS = {name: getattr(re, name) for name in
         ("ASCII", "IGNORECASE", "MULTILINE", "DOTALL", "VERBOSE")}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError("duplicate JSON key", field=key)
        result[key] = value
    return result


def _constant(value):
    raise ConfigurationError(f"non-JSON constant {value}")


def loads_json(text, *, source="<specification>"):
    """Decode strict JSON without imposing a compiler-specific schema."""
    require_python314()
    try:
        return json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
    except json.JSONDecodeError as error:
        raise ConfigurationError(error.msg, source=source, offset=error.pos,
                                 line=error.lineno, column=error.colno) from error
    except ConfigurationError as error:
        error.source = source
        raise


def load_json(path):
    require_python314()
    try:
        text = Path(path).read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as error:
        raise ConfigurationError(str(error), source=str(path)) from error
    return loads_json(text, source=str(path))


def canonical_json_bytes(value):
    """Encode a validated specification, preserving array order and exact text."""
    require_python314()
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("ascii")
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"cannot encode specification as JSON: {error}") from error


def fingerprint(value):
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def compile_flags(names):
    require_python314()
    if not isinstance(names, list):
        raise ConfigurationError("must be an array of flag names", field="flags")
    seen = set()
    mask = re.NOFLAG
    for name in names:
        if not isinstance(name, str) or name not in FLAGS or name in seen:
            raise ConfigurationError("unknown or duplicate regex flag", field="flags")
        seen.add(name)
        mask |= FLAGS[name]
    return mask
