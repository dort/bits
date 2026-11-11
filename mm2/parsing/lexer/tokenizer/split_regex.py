"""Qualify a finite-context regex subset using CPython 3.14's syntax tree.

Only this module depends on re._parser. Reject unknown operations before regex
compilation; a consumed-width calculation alone cannot exclude lookaround.
The subset bounds required context, not backtracking time for trusted specs.
"""

import re
from re import _constants as ops, _parser
import sys

from .model import ConfigurationError, require_python314


MAX_MATCH_CHARS = 65536
CATEGORIES = {ops.CATEGORY_DIGIT, ops.CATEGORY_NOT_DIGIT, ops.CATEGORY_SPACE,
              ops.CATEGORY_NOT_SPACE, ops.CATEGORY_WORD, ops.CATEGORY_NOT_WORD}


def _width(nodes, *, root=False):
    minimum = maximum = 0
    for index, (operation, value) in enumerate(nodes):
        if operation in (ops.LITERAL, ops.NOT_LITERAL, ops.ANY):
            low = high = 1
        elif operation == ops.IN:
            for inner, item in value:
                if inner not in (ops.NEGATE, ops.LITERAL, ops.RANGE, ops.CATEGORY):
                    raise ConfigurationError(f"unsupported character-class operation {inner}", field="pattern")
                if inner == ops.CATEGORY and item not in CATEGORIES:
                    raise ConfigurationError(f"unsupported character category {item}", field="pattern")
            low = high = 1
        elif operation == ops.SUBPATTERN:
            low, high = _width(value[3])
        elif operation == ops.BRANCH:
            widths = [_width(branch) for branch in value[1]]
            low = min(pair[0] for pair in widths)
            high = max(pair[1] for pair in widths)
        elif operation in (ops.MAX_REPEAT, ops.MIN_REPEAT):
            lower, upper, child = value
            if upper == ops.MAXREPEAT:
                raise ConfigurationError("unbounded repeats are not allowed in split patterns", field="pattern")
            child_low, child_high = _width(child)
            low, high = lower * child_low, upper * child_high
        elif operation == ops.AT and value == ops.AT_BEGINNING and root and index == 0:
            low = high = 0
        else:
            raise ConfigurationError(
                f"unsupported split-pattern operation {operation}; only a single leading ^ anchor is allowed",
                field="pattern")
        minimum += low
        maximum += high
        if maximum > MAX_MATCH_CHARS:
            raise ConfigurationError(f"pattern width exceeds {MAX_MATCH_CHARS} characters", field="pattern")
    return minimum, maximum


def compile_pattern(pattern, flags, max_length):
    require_python314()
    if sys.implementation.name != "cpython":
        raise ConfigurationError("split regex validation requires CPython 3.14", field="pattern")
    try:
        minimum, maximum = _width(_parser.parse(pattern, flags), root=True)
        if minimum == 0:
            raise ConfigurationError("split pattern can consume zero characters", field="pattern")
        if maximum > max_length:
            raise ConfigurationError(f"computed width {maximum} exceeds declared max_length {max_length}",
                                     field="max_length")
        return re.compile(pattern, flags), maximum
    except (re.PatternError, ValueError, OverflowError, RecursionError) as error:
        raise ConfigurationError(str(error), field="pattern",
                                 pattern_offset=getattr(error, "pos", None)) from error
